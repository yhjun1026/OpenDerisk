"""P0 fix: SimpleSQLiteMemoryStore.update_memory / aupdate_memory —
the promotion engine's metadata write must really land in the store."""

import pytest

from derisk_ext.storage.memory.simple_sqlite_store import (
    SimpleSQLiteMemoryConfig,
    SimpleSQLiteMemoryStore,
)


@pytest.fixture()
def store(tmp_path):
    config = SimpleSQLiteMemoryConfig(db_path=str(tmp_path / "mem.db"))
    return SimpleSQLiteMemoryStore(config=config)


class TestUpdateMemory:
    def test_update_metadata_merges(self, store):
        entry = store.write_memory(
            content="hello", wing="w", room="r", metadata={"a": 1}
        )
        ok = store.update_memory(
            entry.id, metadata={"promoted": True, "promotion_score": 0.9}
        )
        assert ok is True

        # Read back via search and verify the merge (old keys kept).
        results = store.search_memory("hello", wing="w")
        assert len(results) == 1
        assert results[0].metadata["a"] == 1
        assert results[0].metadata["promoted"] is True
        assert results[0].metadata["promotion_score"] == 0.9

    def test_update_content(self, store):
        entry = store.write_memory(content="old", wing="w", room="r")
        ok = store.update_memory(entry.id, content="new")
        assert ok is True
        assert store.search_memory("new", wing="w")
        assert not store.search_memory("old", wing="w")

    def test_update_missing_returns_false(self, store):
        assert store.update_memory("no-such-id", metadata={"x": 1}) is False

    @pytest.mark.asyncio
    async def test_aupdate_memory(self, store):
        entry = store.write_memory(content="async", wing="w", room="r")
        ok = await store.aupdate_memory(entry.id, metadata={"promoted": True})
        assert ok is True
        results = store.search_memory("async", wing="w")
        assert results[0].metadata["promoted"] is True
