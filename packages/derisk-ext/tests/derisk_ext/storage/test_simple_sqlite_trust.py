"""P2: recall trust score for SimpleSQLiteMemoryStore (hermes
Holographic fact_feedback alignment).

- memories table gains trust_score (idempotent migration, default 1.0)
- memory_feedback: helpful +0.05 / unhelpful -0.10, clamped to [0, 1]
- search_memory: score *= trust_score; entries below 0.3 not returned
"""

import pytest

from derisk_ext.storage.memory.simple_sqlite_store import (
    SimpleSQLiteMemoryConfig,
    SimpleSQLiteMemoryStore,
)


@pytest.fixture()
def store(tmp_path):
    config = SimpleSQLiteMemoryConfig(db_path=str(tmp_path / "mem.db"))
    return SimpleSQLiteMemoryStore(config=config)


class TestSQLiteMemoryFeedback:
    def test_unhelpful_then_helpful(self, store):
        entry = store.write_memory(content="zephyr protocol", wing="w", room="r")
        r = store.memory_feedback(entry.id, helpful=False)
        assert r["previous_trust"] == 1.0
        assert r["trust_score"] == pytest.approx(0.9)
        r = store.memory_feedback(entry.id, helpful=True)
        assert r["trust_score"] == pytest.approx(0.95)

    def test_clamped(self, store):
        entry = store.write_memory(content="zephyr protocol", wing="w", room="r")
        for _ in range(20):
            r = store.memory_feedback(entry.id, helpful=False)
        assert r["trust_score"] == 0.0
        for _ in range(30):
            r = store.memory_feedback(entry.id, helpful=True)
        assert r["trust_score"] == 1.0

    def test_unknown_id_returns_none(self, store):
        assert store.memory_feedback("nope", helpful=True) is None

    def test_async_wrapper(self, store):
        import asyncio

        entry = store.write_memory(content="zephyr protocol", wing="w", room="r")
        r = asyncio.run(store.amemory_feedback(entry.id, helpful=False))
        assert r["trust_score"] == pytest.approx(0.9)


class TestSQLiteRecallTrust:
    def test_score_multiplied_by_trust(self, store):
        entry = store.write_memory(content="zephyr protocol", wing="w", room="r")
        before = store.search_memory("zephyr", wing="w")
        assert len(before) == 1
        store.memory_feedback(entry.id, helpful=False)
        after = store.search_memory("zephyr", wing="w")
        assert after[0].score == pytest.approx(before[0].score * 0.9)
        assert after[0].metadata["trust_score"] == pytest.approx(0.9)

    def test_below_min_trust_not_returned(self, store):
        entry = store.write_memory(content="zephyr protocol", wing="w", room="r")
        assert store.search_memory("zephyr", wing="w")
        for _ in range(8):  # 1.0 - 8 * 0.10 = 0.2 < 0.3
            store.memory_feedback(entry.id, helpful=False)
        assert store.search_memory("zephyr", wing="w") == []


class TestSQLiteMigration:
    def test_idempotent_column_migration(self, tmp_path):
        db = str(tmp_path / "mem.db")
        s1 = SimpleSQLiteMemoryStore(config=SimpleSQLiteMemoryConfig(db_path=db))
        entry = s1.write_memory(content="zephyr", wing="w", room="r")
        s1.memory_feedback(entry.id, helpful=False)
        # Re-opening the same db must not fail on the existing column and
        # must preserve the stored trust value.
        s2 = SimpleSQLiteMemoryStore(config=SimpleSQLiteMemoryConfig(db_path=db))
        r = s2.memory_feedback(entry.id, helpful=False)
        assert r["previous_trust"] == pytest.approx(0.9)
        assert r["trust_score"] == pytest.approx(0.8)
