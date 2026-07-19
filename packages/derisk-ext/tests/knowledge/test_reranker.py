"""Rerank tests — LLMReranker scoring + hybrid search rerank hook.

Stubs AIWrapper.create (same pattern as derisk-serve's test_llm_usage) so
no real LLM is needed; the BaseVaultFS hook is tested with a fake reranker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import DocHit, new_space_id
from derisk_ext.knowledge.reranker import LLMReranker
from derisk_ext.knowledge.vaultfs import LocalVaultFS


def _hit(doc_id: str, title: str, score: float = 0.0) -> DocHit:
    return DocHit(
        document_id=doc_id,
        path=f"concepts/{doc_id}.md",
        title=title,
        type="concept",
        score=score,
        snippet=f"snippet of {title}",
    )


class _FakeResult:
    def __init__(self, text: str):
        self.content = text
        self.usage = None
        self.error_code = 0


def _patch_aiwrapper(monkeypatch, text: str):
    async def _fake_create(self, **config):
        yield _FakeResult(text)

    from derisk.agent.util.llm.llm_client import AIWrapper

    monkeypatch.setattr(AIWrapper, "create", _fake_create)
    from derisk.agent.util.llm.model_config_cache import ModelConfigCache

    if not ModelConfigCache.has_model("test-model"):
        ModelConfigCache.register_configs(
            {
                "stub/test-model": {
                    "provider": "openai",
                    "model": "test-model",
                    "api_key": "sk-x",
                    "base_url": "http://x",
                    "protocol": "openai",
                }
            }
        )


@pytest.mark.asyncio
async def test_llm_reranker_reorders_by_score(monkeypatch):
    _patch_aiwrapper(monkeypatch, '{"scores": {"1": 2, "2": 9, "3": 5}}')
    reranker = LLMReranker("test-model")
    hits = [_hit("a", "Alpha"), _hit("b", "Beta"), _hit("c", "Gamma")]
    out = await reranker.rerank("query", hits)
    assert [h.document_id for h in out] == ["b", "c", "a"]
    assert out[0].score == 9.0  # LLM score replaces the RRF score


@pytest.mark.asyncio
async def test_llm_reranker_bad_output_keeps_order(monkeypatch):
    _patch_aiwrapper(monkeypatch, "not json at all")
    reranker = LLMReranker("test-model")
    hits = [_hit("a", "Alpha"), _hit("b", "Beta")]
    out = await reranker.rerank("query", hits)
    assert [h.document_id for h in out] == ["a", "b"]


@pytest.mark.asyncio
async def test_llm_reranker_partial_scores(monkeypatch):
    _patch_aiwrapper(monkeypatch, '```json\n{"scores": {"2": 10}}\n```')
    reranker = LLMReranker("test-model")
    hits = [_hit("a", "Alpha"), _hit("b", "Beta"), _hit("c", "Gamma")]
    out = await reranker.rerank("query", hits)
    assert out[0].document_id == "b"
    # Unscored hits keep their relative order at the tail.
    assert [h.document_id for h in out[1:]] == ["a", "c"]


class _ReverseReranker:
    """Fake reranker: reverses the candidate order."""

    async def rerank(self, query, hits):
        return list(reversed(hits))


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    v = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "rerank_space")
    await v.initialize()
    yield v
    await v.close()


async def _mkdoc(vault, name: str, body: str):
    await vault.doc_create(
        path=f"concepts/{name}.md",
        content=f"---\ntype: concept\ntitle: {name}\n---\n\n{body}\n",
    )


@pytest.mark.asyncio
async def test_hybrid_applies_mounted_reranker(vault):
    await _mkdoc(vault, "apple", "apple fruit tree orchard")
    await _mkdoc(vault, "applepie", "apple pie recipe dessert")
    vault.configure_reranker(_ReverseReranker())
    baseline = await vault.doc_search("apple", mode="hybrid", limit=2)
    assert len(baseline) == 2
    # Reverse reranker flips the RRF order.
    vault.configure_reranker(None)
    plain = await vault.doc_search("apple", mode="hybrid", limit=2)
    vault.configure_reranker(_ReverseReranker())
    flipped = await vault.doc_search("apple", mode="hybrid", limit=2)
    assert [h.document_id for h in flipped] == [
        h.document_id for h in reversed(plain)
    ]


@pytest.mark.asyncio
async def test_hybrid_without_reranker_unchanged(vault):
    await _mkdoc(vault, "solo", "unique keyword zanzibar")
    hits = await vault.doc_search("zanzibar", mode="hybrid", limit=5)
    assert [h.title for h in hits] == ["solo"]
