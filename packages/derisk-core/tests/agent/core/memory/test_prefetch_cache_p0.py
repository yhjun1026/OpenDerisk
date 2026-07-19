"""P0 fixes: MemoryPrefetchCache multi-consumer + TTL semantics, and the
tier-0 prefetch hook query (full Q/A pair instead of the bare user prompt).
"""

import asyncio

from derisk.agent.core.memory import hook_dispatcher
from derisk.agent.core.memory.read_pipeline import MemoryPrefetchCache


class TestPrefetchCacheConsumers:
    async def test_legacy_consume_without_key_is_one_shot(self):
        cache = MemoryPrefetchCache()
        cache.set_result("q", "r")
        assert await cache.consume(timeout=0.0) == "r"
        assert await cache.consume(timeout=0.0) is None

    async def test_each_consumer_key_reads_once(self):
        """Same conv, multiple agents: every consumer key gets the result
        exactly once (previously only the first consumer got it)."""
        cache = MemoryPrefetchCache()
        cache.set_result("q", "r")
        assert await cache.consume(timeout=0.0, consumer="agent-a") == "r"
        assert await cache.consume(timeout=0.0, consumer="agent-b") == "r"
        # Same consumer twice -> None
        assert await cache.consume(timeout=0.0, consumer="agent-a") is None

    async def test_set_result_rearms_consumers(self):
        cache = MemoryPrefetchCache()
        cache.set_result("q1", "r1")
        assert await cache.consume(timeout=0.0, consumer="agent-a") == "r1"
        cache.set_result("q2", "r2")
        assert await cache.consume(timeout=0.0, consumer="agent-a") == "r2"

    async def test_expired_result_is_dropped(self):
        cache = MemoryPrefetchCache(ttl_seconds=0.01)
        cache.set_result("q", "r")
        await asyncio.sleep(0.02)
        assert await cache.consume(timeout=0.0, consumer="agent-a") is None
        assert not cache.is_ready

    async def test_not_ready_returns_none(self):
        cache = MemoryPrefetchCache()
        assert await cache.consume(timeout=0.0, consumer="agent-a") is None


class _FakeManager:
    def __init__(self):
        self.last_query = None

    async def retrieve_relevant_memories(self, query, **kwargs):
        self.last_query = query
        return "mem"


class _FakeBundle:
    def __init__(self, manager):
        self.manager = manager
        self.config = type("Cfg", (), {"top_k": 5})()


class TestPrefetchHookQuery:
    async def test_prefetch_uses_full_qa_pair(self, monkeypatch):
        """turn_complete prefetch must query with the completed Q/A pair —
        follow-up questions revolve around both, not just the user prompt."""
        manager = _FakeManager()
        bundle = _FakeBundle(manager)
        conv_id = "conv-prefetch-query"
        hook_dispatcher.register_memory_bundle(conv_id, bundle)

        captured = {}

        async def fake_do_prefetch(conv_id, bundle, query, pipeline_lookup):
            captured["query"] = query

        monkeypatch.setattr(hook_dispatcher, "_do_prefetch", fake_do_prefetch)
        # No pipeline registered -> hook still schedules _do_prefetch; the
        # pipeline lookup happens inside _do_prefetch itself.
        try:
            event = {
                "conv_id": conv_id,
                "user_prompt": "怎么优化索引？",
                "final_answer": "先加复合索引，再 analyze 表。",
                "round": 1,
            }
            result = await hook_dispatcher.memory_prefetch_function(event, {})
            assert result == {"action": "continue"}
            # fire-and-forget task — let it run
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert captured["query"] == "怎么优化索引？\n先加复合索引，再 analyze 表。"
        finally:
            hook_dispatcher.unregister_memory_bundle(conv_id)

    async def test_prefetch_skips_when_interrupted(self):
        conv_id = "conv-prefetch-interrupted"
        hook_dispatcher.register_memory_bundle(conv_id, _FakeBundle(_FakeManager()))
        try:
            event = {
                "conv_id": conv_id,
                "user_prompt": "q",
                "final_answer": "a",
                "success": False,
            }
            result = await hook_dispatcher.memory_prefetch_function(event, {})
            assert result == {"action": "continue"}
        finally:
            hook_dispatcher.unregister_memory_bundle(conv_id)

    async def test_prefetch_falls_back_to_prompt_only(self, monkeypatch):
        """No final_answer (e.g. max-steps interrupt-free edge) -> prompt only."""
        manager = _FakeManager()
        conv_id = "conv-prefetch-prompt-only"
        hook_dispatcher.register_memory_bundle(conv_id, _FakeBundle(manager))

        captured = {}

        async def fake_do_prefetch(conv_id, bundle, query, pipeline_lookup):
            captured["query"] = query

        monkeypatch.setattr(hook_dispatcher, "_do_prefetch", fake_do_prefetch)
        try:
            event = {"conv_id": conv_id, "user_prompt": "只言片语", "round": 2}
            await hook_dispatcher.memory_prefetch_function(event, {})
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert captured["query"] == "只言片语"
        finally:
            hook_dispatcher.unregister_memory_bundle(conv_id)
