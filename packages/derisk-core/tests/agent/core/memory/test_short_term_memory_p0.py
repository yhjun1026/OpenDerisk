"""P0 fixes: ShortTermMemory.transfer_to_long_term eviction order,
ShortTermMemory.list minimal implementation, and importance-score scale
unification (raw 1-10 from the scorer, single weight multiplication in
Memory.score_memory_importance).
"""

from derisk.agent.core.memory.agent_memory import AgentMemory, AgentMemoryFragment
from derisk.agent.core.memory.base import ImportanceScorer, ShortTermMemory
from derisk.agent.core.memory.llm import BaseLLMCaller


def _frag(obs: str, **kwargs) -> AgentMemoryFragment:
    return AgentMemoryFragment(observation=obs, **kwargs)


class TestTransferToLongTerm:
    async def test_oldest_fragments_are_evicted(self):
        """Overflow must transfer the OLDEST fragments, not the newest."""
        mem = ShortTermMemory(buffer_size=3)
        evicted = []
        for i in range(5):
            discarded = await mem.write(_frag(f"obs-{i}"))
            if discarded:
                evicted.extend(
                    f.raw_observation for f in discarded.discarded_memory_fragments
                )

        assert evicted == ["obs-0", "obs-1"]
        remaining = [f.raw_observation for f in mem.short_term_memories]
        assert remaining == ["obs-2", "obs-3", "obs-4"]

    async def test_no_overflow_returns_none(self):
        mem = ShortTermMemory(buffer_size=5)
        discarded = await mem.write(_frag("obs-0"))
        assert discarded is None


class TestShortTermMemoryList:
    async def test_list_all(self):
        mem = ShortTermMemory(buffer_size=5)
        await mem.write(_frag("a", session_id="s1", agent_id="ag1"))
        await mem.write(_frag("b", session_id="s2", agent_id="ag2"))
        assert len(mem.list()) == 2

    async def test_list_filters_by_ids(self):
        mem = ShortTermMemory(buffer_size=5)
        await mem.write(
            _frag("a", session_id="s1", agent_id="ag1", message_id="m1")
        )
        await mem.write(
            _frag("b", session_id="s2", agent_id="ag2", message_id="m2")
        )
        assert [f.raw_observation for f in mem.list(session_id="s1")] == ["a"]
        assert [f.raw_observation for f in mem.list(agent_id="ag2")] == ["b"]
        assert [f.raw_observation for f in mem.list(message_id="m1")] == ["a"]
        assert mem.list(session_id="nope") == []

    async def test_agent_memory_list_delegates(self):
        """AgentMemory.list previously raised AttributeError (no list on
        Memory ABC / ShortTermMemory)."""
        agent_mem = AgentMemory()
        await agent_mem.write(_frag("hello", session_id="s1"))
        result = agent_mem.list(session_id="s1")
        assert [f.raw_observation for f in result] == ["hello"]


class _FakeScorer(ImportanceScorer):
    async def score_importance(self, memory_fragment, llm_client=None) -> float:
        return 8.0  # raw 1-10 scale


class TestImportanceScale:
    def test_parse_number_returns_raw_score(self):
        """_parse_number must not apply importance_weight — scaling happens
        exactly once in Memory.score_memory_importance."""
        assert BaseLLMCaller._parse_number("8") == 8.0
        assert BaseLLMCaller._parse_number("Rating: 7") == 7.0
        assert BaseLLMCaller._parse_number("no number") == 0.0

    async def test_scorer_path_multiplies_weight_once(self):
        mem = ShortTermMemory(buffer_size=5)
        mem.initialize(importance_scorer=_FakeScorer())
        scores = await mem.score_memory_importance([_frag("x")])
        assert scores == [8.0 * mem.importance_weight]

    async def test_no_scorer_default_same_scale(self):
        """Default (no scorer) = 5 * weight — same (raw * weight) scale as
        the LLM-scored path."""
        mem = ShortTermMemory(buffer_size=5)
        mem.initialize(importance_scorer=None)
        scores = await mem.score_memory_importance([_frag("x"), _frag("y")])
        assert scores == [5 * mem.importance_weight] * 2
