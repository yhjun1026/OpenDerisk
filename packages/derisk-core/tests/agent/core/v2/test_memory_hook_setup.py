"""memory hook 注册测试。"""
from unittest.mock import AsyncMock, MagicMock
from derisk.agent.core.hook.executors import FunctionRegistry
from derisk.agent.core.v2.memory_hook_setup import register_memory_hooks


def test_register_memory_hooks_adds_4_hooks():
    hook_manager = MagicMock()
    bundle = MagicMock()
    bundle.manager = MagicMock()
    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=bundle,
        reflection_interval=10,
    )
    # append_hooks 应被调用一次，传入 4 个 HookConfig（tier0/1/2/3）
    hook_manager.append_hooks.assert_called_once()
    hooks = hook_manager.append_hooks.call_args[0][0]
    assert len(hooks) == 4


def test_register_skips_if_no_bundle():
    hook_manager = MagicMock()
    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=None,
        reflection_interval=10,
    )
    hook_manager.append_hooks.assert_not_called()


def test_memory_hook_endpoints_have_timeout():
    """熔断：所有 memory hook endpoint 都必须配置有界 timeout。"""
    hook_manager = MagicMock()
    bundle = MagicMock()
    bundle.manager = MagicMock()
    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=bundle,
        reflection_interval=10,
    )
    hooks = hook_manager.append_hooks.call_args[0][0]
    for h in hooks:
        assert h.endpoint.timeout and h.endpoint.timeout > 0


async def test_tier2_reflect_gets_buffered_turns():
    """V2 build_turn_complete_context 不传 extra.turns；tier2 必须由
    tier1 每轮写入的闭包缓冲拿到最近 N 轮问答，否则 reflect 永远 no-op。"""
    hook_manager = MagicMock()
    bundle = MagicMock()
    bundle.manager = MagicMock()
    bundle.manager.write_turn_lightweight = AsyncMock()
    bundle.manager.reflect_on_last_n_turns = AsyncMock()
    bundle.pipeline = None  # tier0 不注册

    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=bundle,
        reflection_interval=2,
    )

    tier1 = FunctionRegistry.get("_v2_memory_tier1_write")
    tier2 = FunctionRegistry.get("_v2_memory_tier2_reflect")
    assert tier1 is not None and tier2 is not None

    # 两轮 turn_complete
    await tier1({"user_prompt": "q1", "final_answer": "a1", "conv_id": "c"}, {})
    await tier1({"user_prompt": "q2", "final_answer": "a2", "conv_id": "c"}, {})
    # 第 2 轮触发 tier2
    await tier2({"conv_id": "c", "round": 2}, {})

    bundle.manager.reflect_on_last_n_turns.assert_called_once()
    kwargs = bundle.manager.reflect_on_last_n_turns.call_args.kwargs
    turns = kwargs["turns"]
    assert turns == [
        {"user": "q1", "assistant": "a1"},
        {"user": "q2", "assistant": "a2"},
    ]
    assert kwargs["n"] == 2


async def test_tier2_prefers_event_extra_turns():
    """event.extra.turns 存在时优先（与 V1 路径对齐）。"""
    hook_manager = MagicMock()
    bundle = MagicMock()
    bundle.manager = MagicMock()
    bundle.manager.write_turn_lightweight = AsyncMock()
    bundle.manager.reflect_on_last_n_turns = AsyncMock()
    bundle.pipeline = None

    register_memory_hooks(
        hook_manager=hook_manager,
        memory_bundle=bundle,
        reflection_interval=2,
    )
    tier2 = FunctionRegistry.get("_v2_memory_tier2_reflect")
    explicit = [{"user": "x", "assistant": "y"}]
    await tier2({"conv_id": "c", "extra": {"turns": explicit}}, {})
    kwargs = bundle.manager.reflect_on_last_n_turns.call_args.kwargs
    assert kwargs["turns"] == explicit
