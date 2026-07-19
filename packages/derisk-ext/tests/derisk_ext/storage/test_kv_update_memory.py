"""P0 fix: KnowledgeVaultMemoryStore.aupdate_memory — promotion metadata
is persisted as L2 edges (the vault has no metadata-update primitive)."""

import pytest

from derisk_ext.storage.memory.knowledge_vault_store import (
    KnowledgeVaultMemoryConfig,
    KnowledgeVaultMemoryStore,
)


class _FakeVault:
    space_id = "space-1"

    def __init__(self):
        self.edges = []

    async def edge_add(self, edge):
        self.edges.append(edge)
        return edge.id


@pytest.fixture()
def store():
    vault = _FakeVault()
    return KnowledgeVaultMemoryStore(
        config=KnowledgeVaultMemoryConfig(space_slug="memory-test"),
        vault=vault,
    ), vault


class TestKVUpdateMemory:
    @pytest.mark.asyncio
    async def test_metadata_recorded_as_edges(self, store):
        s, vault = store
        ok = await s.aupdate_memory(
            "m1", metadata={"promoted": True, "promotion_score": 0.83}
        )
        assert ok is True
        subjects = {e.subject for e in vault.edges}
        predicates = {e.predicate for e in vault.edges}
        assert subjects == {"memory:m1"}
        assert predicates == {"promoted", "promotion_score"}

    @pytest.mark.asyncio
    async def test_content_update_unsupported(self, store):
        s, vault = store
        ok = await s.aupdate_memory("m1", content="new body")
        assert ok is False
        assert vault.edges == []

    @pytest.mark.asyncio
    async def test_empty_metadata_is_noop_success(self, store):
        s, vault = store
        assert await s.aupdate_memory("m1") is True
        assert vault.edges == []
