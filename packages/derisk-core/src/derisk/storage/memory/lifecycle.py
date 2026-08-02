"""Memory lifecycle hooks for session-level events.

Borrows from Hermes-Agent's MemoryProvider lifecycle hooks:
- on_turn_start: Pre-warm retrieval before each turn
- on_session_end: Final memory extraction at session boundary
- on_session_switch: Reset caches on session rotation
- on_pre_compress: Extract insights before context compression
- on_memory_write: Mirror built-in writes to external providers
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# Keywords that signal content worth preserving before compression.
_IMPORTANCE_KEYWORDS = {
    "decision", "decided", "agreed", "conclusion", "important",
    "remember", "note", "key point", "action item", "deadline",
    "决定", "结论", "重要", "记住", "注意", "关键", "截止",
    "偏好", "喜欢", "不喜欢", "preference", "prefer", "like", "dislike",
}


def _extract_compressible_insights(messages: List[Dict[str, Any]]) -> str:
    """Lightweight heuristic extraction for pre-compression hook.

    Scans messages for high-signal sentences so they are not lost when
    the surrounding context is summarised.  This is intentionally simple;
    tier-2 reflection performs the heavy LLM-based extraction.
    """
    insights: List[str] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "").lower()
        content = msg.get("content") or ""
        if role not in ("user", "assistant", "human", "ai"):
            continue
        if not isinstance(content, str):
            continue
        # Sentence-level scan.
        for sentence in content.replace("?", ".").replace("!", ".").split("."):
            sentence = sentence.strip()
            if not sentence:
                continue
            lowered = sentence.lower()
            if any(kw in lowered for kw in _IMPORTANCE_KEYWORDS):
                insights.append(sentence)
    if not insights:
        return ""
    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for item in insights:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return "\n".join(f"- {item}" for item in unique[:10])


class MemoryLifecycleHooks(ABC):
    """Abstract interface for memory lifecycle events.

    Implementations handle:
    - Session-level event processing
    - Memory synchronization across providers
    - Pre-compression insight extraction
    """

    @abstractmethod
    async def on_turn_start(
        self,
        turn_number: int,
        user_message: str,
        **kwargs,
    ) -> None:
        """Called at the start of each turn.

        Use for:
        - Pre-warming retrieval cache
        - Periodic maintenance
        """
        pass

    @abstractmethod
    async def on_turn_end(
        self,
        turn_number: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Called at the end of each turn.

        Use for:
        - Auto-writing memories
        - Sync to external providers
        """
        pass

    @abstractmethod
    async def on_session_end(
        self,
        conversation_history: List[Dict[str, Any]],
    ) -> None:
        """Called when a session ends.

        Use for:
        - Final memory extraction
        - Summarization
        - Cleanup
        """
        pass

    @abstractmethod
    async def on_session_switch(
        self,
        new_session_id: str,
        parent_session_id: str = "",
        reset: bool = False,
    ) -> None:
        """Called when switching sessions.

        Fires on /resume, /branch, /reset, context compression.

        Args:
            new_session_id: The session being switched to
            parent_session_id: Previous session (for lineage)
            reset: True if this is a genuinely new conversation
        """
        pass

    @abstractmethod
    async def on_pre_compress(
        self,
        messages_to_compress: List[Dict[str, Any]],
    ) -> str:
        """Called before context compression.

        Use to extract insights from messages about to be
        summarized/discarded.

        Returns:
            Text to include in the compression summary
        """
        pass


class DefaultLifecycleHooks(MemoryLifecycleHooks):
    """Default implementation with lightweight, safe handlers.

    The heavy lifting (tier-1/2/3 memory writes, reflection, curation) is
    performed by the LongTermMemoryManager hooks.  These handlers provide
    small, useful defaults:

    - on_pre_compress: preserve high-signal sentences before context compression
    - on_session_end: write a session-close marker when a store is available
    - on_turn_start/end, on_session_switch: logging for observability
    """

    def __init__(self, memory_store: Optional[Any] = None):
        self._memory_store = memory_store

    async def on_turn_start(
        self,
        turn_number: int,
        user_message: str,
        **kwargs,
    ) -> None:
        logger.debug(
            f"[MemoryLifecycle] turn {turn_number} start: "
            f"user_message_len={len(user_message or '')}"
        )

    async def on_turn_end(
        self,
        turn_number: int,
        user_message: str,
        assistant_message: str,
    ) -> None:
        logger.debug(
            f"[MemoryLifecycle] turn {turn_number} end: "
            f"user_len={len(user_message or '')} "
            f"assistant_len={len(assistant_message or '')}"
        )

    async def on_session_end(
        self,
        conversation_history: List[Dict[str, Any]],
    ) -> None:
        logger.info(
            f"[MemoryLifecycle] session end: "
            f"history_messages={len(conversation_history or [])}"
        )
        if self._memory_store is None:
            return
        try:
            # Write a lightweight session-close marker so the memory store
            # records the session boundary independently of tier-3 curation.
            self._memory_store.write_memory(
                content=(
                    f"Session ended with {len(conversation_history or [])} "
                    "messages."
                ),
                wing="lifecycle",
                room="session_close",
                metadata={"event": "session_end"},
            )
        except Exception as e:
            logger.warning(f"[MemoryLifecycle] session_close marker failed: {e}")

    async def on_session_switch(
        self,
        new_session_id: str,
        parent_session_id: str = "",
        reset: bool = False,
    ) -> None:
        logger.info(
            f"[MemoryLifecycle] session switch: new={new_session_id} "
            f"parent={parent_session_id} reset={reset}"
        )

    async def on_pre_compress(
        self,
        messages_to_compress: List[Dict[str, Any]],
    ) -> str:
        insights = _extract_compressible_insights(messages_to_compress)
        if insights:
            logger.debug(
                f"[MemoryLifecycle] pre_compress insights: {len(insights)} chars"
            )
        return insights
