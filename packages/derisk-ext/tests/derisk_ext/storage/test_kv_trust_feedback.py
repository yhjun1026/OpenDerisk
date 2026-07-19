"""P2: recall trust score for KnowledgeVaultMemoryStore (hermes
Holographic fact_feedback alignment).

- trust_score lives in L1 frontmatter (default 1.0)
- memory_feedback: helpful +0.05 / unhelpful -0.10, clamped to [0, 1]
- recall: score *= trust_score; docs below TRUST_MIN_RECALL (0.3) dropped
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import new_space_id
from derisk_ext.knowledge.vaultfs import LocalVaultFS
from derisk_ext.storage.memory.knowledge_vault_store import (
    KnowledgeVaultMemoryConfig,
    KnowledgeVaultMemoryStore,
)


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    vault = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "space")
    await vault.initialize()
    s = KnowledgeVaultMemoryStore(
        config=KnowledgeVaultMemoryConfig(space_slug="memory-test"),
        vault=vault,
    )
    yield s, vault
    await vault.close()


async def _write_doc(store, path="concepts/m1.md", body="User prefers zephyr diagrams."):
    return await store.write_doc(
        path,
        body,
        {"type": "concept", "title": "m1"},
    )


class TestMemoryFeedback:
    @pytest.mark.asyncio
    async def test_unhelpful_then_helpful(self, store):
        s, vault = store
        await _write_doc(s)
        r = await s.memory_feedback("concepts/m1.md", helpful=False)
        assert r["previous_trust"] == 1.0
        assert r["trust_score"] == pytest.approx(0.9)
        r = await s.memory_feedback("concepts/m1.md", helpful=True)
        assert r["trust_score"] == pytest.approx(0.95)
        doc = await vault.doc_read("concepts/m1.md")
        assert doc.frontmatter["trust_score"] == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_clamped_to_zero_and_one(self, store):
        s, _ = store
        await _write_doc(s)
        for _ in range(20):
            r = await s.memory_feedback("concepts/m1.md", helpful=False)
        assert r["trust_score"] == 0.0
        r = await s.memory_feedback("concepts/m1.md", helpful=True)
        assert r["trust_score"] == pytest.approx(0.05)
        for _ in range(30):
            r = await s.memory_feedback("concepts/m1.md", helpful=True)
        assert r["trust_score"] == 1.0

    @pytest.mark.asyncio
    async def test_feedback_by_doc_id(self, store):
        s, vault = store
        doc_id = await _write_doc(s)
        r = await s.memory_feedback(doc_id, helpful=False)
        assert r["path"] == "concepts/m1.md"
        assert r["trust_score"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_feedback_unknown_id_raises(self, store):
        s, _ = store
        with pytest.raises(ValueError):
            await s.memory_feedback("nonexistent-doc-id", helpful=True)


class TestRecallTrust:
    @pytest.mark.asyncio
    async def test_frontmatter_trust_carried_and_weights_score(self, store):
        s, _ = store
        await s.write_doc(
            "concepts/m1.md",
            "User prefers zephyr diagrams.",
            {"type": "concept", "title": "m1", "trust_score": 0.5},
        )
        entries = await s.asearch_memory("zephyr", top_k=5)
        l1 = [e for e in entries if e.metadata.get("layer") == "L1"]
        assert len(l1) == 1
        assert l1[0].metadata["trust_score"] == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_score_multiplied_by_trust(self, store):
        s, _ = store
        await _write_doc(s)
        before = await s.asearch_memory("zephyr", top_k=5)
        before = [e for e in before if e.metadata.get("layer") == "L1"]
        assert len(before) == 1
        base_score = before[0].score

        await s.memory_feedback("concepts/m1.md", helpful=False)  # trust 0.9
        after = await s.asearch_memory("zephyr", top_k=5)
        after = [e for e in after if e.metadata.get("layer") == "L1"]
        assert len(after) == 1
        assert after[0].score == pytest.approx(base_score * 0.9)

    @pytest.mark.asyncio
    async def test_below_min_trust_not_returned(self, store):
        s, _ = store
        await _write_doc(s)
        before = await s.asearch_memory("zephyr", top_k=5)
        assert any(e.metadata.get("layer") == "L1" for e in before)

        # 1.0 - 8 * 0.10 = 0.2 < 0.3
        for _ in range(8):
            await s.memory_feedback("concepts/m1.md", helpful=False)
        after = await s.asearch_memory("zephyr", top_k=5)
        assert not any(e.metadata.get("layer") == "L1" for e in after)
