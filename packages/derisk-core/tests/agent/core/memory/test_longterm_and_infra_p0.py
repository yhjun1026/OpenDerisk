"""P0 fixes: keyword-only noteworthy extraction, bounded layer4 history
manager cache, and GptsMemory per-instance defaults."""

from cachetools import TTLCache

from derisk.agent.core.memory import layer4_conversation_history as l4
from derisk.agent.core.memory.longterm_manager import (
    LongTermMemoryConfig,
    LongTermMemoryManager,
)


def _manager() -> LongTermMemoryManager:
    return LongTermMemoryManager(config=LongTermMemoryConfig(), memory_stores={})


class TestExtractNoteworthyContent:
    def test_long_content_without_keywords_is_dropped(self):
        """Previously len>500 alone marked content important, dumping whole
        long conversations into long-term memory."""
        m = _manager()
        long_user = "帮我看看这段代码 " + "x" * 600
        long_ai = "好的 " + "y" * 600
        assert m._extract_noteworthy_content(long_user, long_ai) is None

    def test_keyword_hit_is_written(self):
        m = _manager()
        content = m._extract_noteworthy_content(
            "请记住我的偏好：我喜欢简洁的回答，不要太长的解释和客套话",
            "好的，已记住，后续都会保持简洁",
        )
        assert content is not None
        assert "请记住" in content

    def test_short_content_below_min_length_dropped(self):
        m = _manager()
        assert m._extract_noteworthy_content("好", "嗯") is None

    def test_empty_returns_none(self):
        m = _manager()
        assert m._extract_noteworthy_content("", "") is None


class TestLayer4ManagerCache:
    def test_history_managers_is_bounded_ttl_cache(self):
        """The global _history_managers dict had no TTL/eviction (memory
        leak). It must now be a bounded TTLCache."""
        assert isinstance(l4._history_managers, TTLCache)
        assert l4._history_managers.maxsize > 0
        assert l4._history_managers.ttl > 0

    def test_clear_history_manager_cache(self):
        l4._history_managers["s-test"] = object()
        l4.clear_history_manager_cache("s-test")
        assert "s-test" not in l4._history_managers


class TestGptsMemoryDefaults:
    def test_default_dependencies_are_per_instance(self):
        """Mutable default args (DefaultGptsPlansMemory() etc. as parameter
        defaults) were shared across all instances constructed without
        explicit args."""
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory

        m1 = GptsMemory()
        m2 = GptsMemory()
        assert m1.plans_memory is not m2.plans_memory
        assert m1.message_memory is not m2.message_memory
        assert m1._default_vis_converter is not m2._default_vis_converter

    def test_explicit_dependencies_are_honoured(self):
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
        from derisk.agent.core.memory.gpts.default_gpts_memory import (
            DefaultGptsMessageMemory,
            DefaultGptsPlansMemory,
        )

        plans = DefaultGptsPlansMemory()
        messages = DefaultGptsMessageMemory()
        m = GptsMemory(plans_memory=plans, message_memory=messages)
        assert m.plans_memory is plans
        assert m.message_memory is messages
