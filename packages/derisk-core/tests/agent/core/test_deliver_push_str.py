"""_deliver_push str stream_msg 透传单测.

验证修复：str stream_msg（如 d-todo-list 围栏）直接透传到 channel，不走 converter
（GptVisConverter.agent_stream_message 对 str 调 .get() 抛 AttributeError 被吞）。
dict stream_msg 仍走 converter（不回归）。
"""
from unittest.mock import AsyncMock, MagicMock

from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory


def _make_mem():
    mem = GptsMemory.__new__(GptsMemory)
    mem.vis_messages = AsyncMock(return_value="view_from_converter")
    return mem


def _make_cache():
    cache = MagicMock()
    cache.channel.put_nowait = MagicMock()
    cache.senders = {}
    cache.start_push = False
    return cache


async def test_str_stream_msg_passthrough():
    mem = _make_mem()
    cache = _make_cache()
    fence = "```d-todo-list\n" '{"items":[]}' "\n```"

    await mem._deliver_push("conv1", cache, stream_msg=fence, incr_type="all")

    # str 透传：channel 收到原 fence，不走 converter
    cache.channel.put_nowait.assert_called_once_with(fence)
    mem.vis_messages.assert_not_called()


async def test_dict_stream_msg_uses_converter():
    mem = _make_mem()
    cache = _make_cache()

    await mem._deliver_push(
        "conv1", cache, stream_msg={"content": "hi", "sender": "a", "model": "m"}
    )

    # dict 仍走 converter（不回归）
    mem.vis_messages.assert_called_once()
    cache.channel.put_nowait.assert_called_once_with("view_from_converter")
