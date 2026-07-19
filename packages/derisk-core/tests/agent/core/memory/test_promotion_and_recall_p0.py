"""P0 fixes: promotion closed loop (store really updated) and RecallTracker
SQLite persistence (no cold start after restart)."""

from derisk.storage.memory.base import MemoryEntry
from derisk.storage.memory.promotion import MemoryPromotionEngine
from derisk.storage.memory.recall_tracker import RecallTracker


def _entry(mid: str, score: float = 0.9) -> MemoryEntry:
    return MemoryEntry(id=mid, content=f"content-{mid}", wing="w", room="r", score=score)


class _RecordingStore:
    """Minimal store double: records aupdate_memory calls."""

    def __init__(self):
        self.updates = []

    async def aupdate_memory(self, memory_id, content=None, metadata=None):
        self.updates.append(
            {"memory_id": memory_id, "content": content, "metadata": metadata}
        )
        return True


class _FailingStore:
    async def aupdate_memory(self, memory_id, content=None, metadata=None):
        raise RuntimeError("store down")


class TestPromotionSweep:
    async def _make_engine(self, tracker, threshold=0.1):
        return MemoryPromotionEngine(
            recall_tracker=tracker, promotion_threshold=threshold
        )

    async def test_sweep_updates_store_metadata(self):
        tracker = RecallTracker()
        for _ in range(6):
            await tracker.record("query-a", [_entry("m1")], space_id="s1")
        store = _RecordingStore()
        engine = await self._make_engine(tracker)

        result = await engine.run_promotion_sweep(space_id="s1", store=store)

        assert len(result.promoted) == 1
        assert result.promoted[0].memory_id == "m1"
        assert store.updates, "promotion must really write to the store"
        update = store.updates[0]
        assert update["memory_id"] == "m1"
        assert update["metadata"]["promoted"] is True
        assert "promotion_score" in update["metadata"]

    async def test_sweep_below_threshold_writes_nothing(self):
        tracker = RecallTracker()
        await tracker.record("query-a", [_entry("m1")], space_id="s1")
        store = _RecordingStore()
        engine = MemoryPromotionEngine(
            recall_tracker=tracker, promotion_threshold=0.999
        )
        result = await engine.run_promotion_sweep(space_id="s1", store=store)
        assert result.promoted == []
        assert store.updates == []

    async def test_store_failure_does_not_crash_sweep(self):
        tracker = RecallTracker()
        for _ in range(6):
            await tracker.record("query-a", [_entry("m1")], space_id="s1")
        engine = MemoryPromotionEngine(
            recall_tracker=tracker, promotion_threshold=0.1
        )
        result = await engine.run_promotion_sweep(
            space_id="s1", store=_FailingStore()
        )
        assert result.promoted == []


class TestRecallTrackerPersistence:
    async def test_stats_survive_restart(self, tmp_path):
        db = str(tmp_path / "recall.db")
        tracker = RecallTracker(db_path=db)
        for i in range(3):
            await tracker.record(f"query-{i}", [_entry("m1"), _entry("m2")], "s1")
        await tracker.record("query-0", [_entry("m1")], "s1")

        # Simulate restart: fresh instance over the same db file.
        reloaded = RecallTracker(db_path=db)
        stats = await reloaded.get_recall_stats("s1")
        assert set(stats.keys()) == {"m1", "m2"}
        assert stats["m1"].recall_count == 4
        assert stats["m2"].recall_count == 3
        assert stats["m1"].unique_queries == 3

        candidates = await reloaded.get_top_candidates("s1")
        assert candidates
        assert candidates[0]["memory_id"] == "m1"

    async def test_unique_queries_tracked(self):
        tracker = RecallTracker()
        await tracker.record("same", [_entry("m1")], "s1")
        await tracker.record("same", [_entry("m1")], "s1")
        await tracker.record("different", [_entry("m1")], "s1")
        stats = await tracker.get_recall_stats("s1")
        assert stats["m1"].recall_count == 3
        assert stats["m1"].unique_queries == 2

    async def test_clear_removes_persisted_rows(self, tmp_path):
        db = str(tmp_path / "recall.db")
        tracker = RecallTracker(db_path=db)
        await tracker.record("q", [_entry("m1")], "s1")
        await tracker.clear("s1")
        reloaded = RecallTracker(db_path=db)
        assert await reloaded.get_recall_stats("s1") == {}

    async def test_in_memory_default_unchanged(self):
        tracker = RecallTracker()
        await tracker.record("q", [_entry("m1")], "s1")
        stats = await tracker.get_recall_stats("s1")
        assert stats["m1"].recall_count == 1
