"""L0 verbat embedding tests (per-space embed_verbats, default off).

Covers the write-path embedding (verbat_add / verbat_append_content /
verbat_deprecate) and the semantic/hybrid verbat_search modes. Uses a
fake embedder + in-memory vector store so no external services are needed.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import ExtractMode, Verbat, new_space_id
from derisk_ext.knowledge.vaultfs import LocalVaultFS


class _FakeEmbedder:
    """Deterministic bag-of-words embedder (8-dim hashing)."""

    def embed_query(self, text: str):
        vec = [0.0] * 8
        for tok in text.lower().split():
            vec[hash(tok) % 8] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class _FakeVectorStore:
    def __init__(self):
        self.vectors = {}

    async def upsert(self, id, embedding, meta):
        self.vectors[id] = (embedding, meta)

    async def query(self, embedding, top_k, filter=None):
        from derisk.knowledge.types import VectorHit

        def cos(a, b):
            return sum(x * y for x, y in zip(a, b))

        scored = sorted(
            self.vectors.items(), key=lambda kv: cos(kv[1][0], embedding), reverse=True
        )
        return [
            VectorHit(id=vid, score=cos(vec, embedding), metadata=meta)
            for vid, (vec, meta) in scored[:top_k]
        ]

    async def delete(self, id):
        self.vectors.pop(id, None)

    async def clear(self):
        self.vectors.clear()


@pytest_asyncio.fixture
async def vault(tmp_path: Path, monkeypatch):
    v = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "embed_space")
    store = _FakeVectorStore()

    async def _fake_make_store():
        return store

    monkeypatch.setattr(v, "_make_vector_store", _fake_make_store)
    monkeypatch.setattr(v, "_build_embedder", lambda model: _FakeEmbedder())
    # Enable L0 embedding (per-space flag) with a model hint so lazy
    # embedder identity provisioning succeeds.
    v.configure_embedder_hint("fake-model", embed_verbats=True)
    await v.initialize()
    v._test_store = store
    yield v
    await v.close()


async def _add(vault, content: str, source_file: str = "note.md"):
    v = Verbat.create(
        space_id=vault.space_id,
        content=content,
        source_file=source_file,
        extract_mode=ExtractMode.UPLOAD,
    )
    return await vault.verbat_add(v)


@pytest.mark.asyncio
async def test_verbat_add_embeds_when_enabled(vault):
    vid = await _add(vault, "quantum entanglement notes")
    assert f"verbat:{vid}" in vault._test_store.vectors
    meta = vault._test_store.vectors[f"verbat:{vid}"][1]
    assert meta["verbat_id"] == vid
    assert meta["extract_mode"] == "upload"


@pytest.mark.asyncio
async def test_verbat_semantic_search(vault):
    await _add(vault, "quantum entanglement superposition")
    await _add(vault, "banana bread recipe", source_file="food.md")
    hits = await vault.verbat_search("quantum physics", mode="semantic")
    assert hits
    assert hits[0].source_file == "note.md"
    # keyword LIKE would NOT match ("quantum physics" not a substring)
    kw = await vault.verbat_search("quantum physics", mode="keyword")
    assert kw == []


@pytest.mark.asyncio
async def test_verbat_hybrid_merges_keyword_and_semantic(vault):
    vid = await _add(vault, "quantum entanglement superposition")
    hits = await vault.verbat_search("quantum entanglement", mode="hybrid")
    assert any(h.verbat_id == vid for h in hits)


@pytest.mark.asyncio
async def test_verbat_deprecate_removes_vector(vault):
    vid = await _add(vault, "doomed content")
    assert f"verbat:{vid}" in vault._test_store.vectors
    await vault.verbat_deprecate(vid)
    assert f"verbat:{vid}" not in vault._test_store.vectors
    hits = await vault.verbat_search("doomed", mode="semantic")
    assert not any(h.verbat_id == vid for h in hits)


@pytest.mark.asyncio
async def test_verbat_append_refreshes_vector(vault):
    vid = await _add(vault, "session start alpha")
    before = vault._test_store.vectors[f"verbat:{vid}"][0]
    await vault.verbat_append_content(vid, "turn two gamma delta")
    after = vault._test_store.vectors[f"verbat:{vid}"][0]
    assert before != after
    hits = await vault.verbat_search("gamma delta", mode="semantic")
    assert any(h.verbat_id == vid for h in hits)


@pytest.mark.asyncio
async def test_embed_verbats_off_by_default(tmp_path: Path):
    """Without embed_verbats, verbat_add writes no vector and the
    semantic/hybrid modes degrade to keyword search."""
    v = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "off_space")
    await v.initialize()
    try:
        assert not v._embed_verbats_enabled
        vid = await _add(v, "plain keyword content")
        # No vector store interaction happens at all with the flag off.
        assert v._vector_store is None
        # semantic mode with flag off → keyword fallback (never raises)
        hits = await v.verbat_search("plain", mode="semantic")
        assert isinstance(hits, list)
        hits = await v.verbat_search("plain", mode="hybrid")
        assert isinstance(hits, list)
    finally:
        await v.close()
