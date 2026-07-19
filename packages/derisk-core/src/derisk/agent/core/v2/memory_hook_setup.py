"""把 memory tier0/1/2/3 挂到 V2 的 HookManager。

等价 BAIZE memory/hook_dispatcher.default_memory_hooks，但直接注册到 HookManager
（不通过 _BUNDLE_REGISTRY 间接查找）。handler 函数通过闭包捕获 manager/pipeline，
注册到 FunctionRegistry 后由 HookManager 的 FunctionHookExecutor 调用。
"""
from collections import deque
from typing import Any

from derisk.agent.core.hook.executors import FunctionRegistry
from derisk.agent.core.hook.schema import (
    HookConfig,
    HookEndpointConfig,
    HookKind,
    HookTriggerConfig,
    HookTriggerType,
)


def register_memory_hooks(
    *,
    hook_manager: Any,
    memory_bundle: Any,
    reflection_interval: int = 10,
) -> None:
    """把 memory tier0/1/2/3 挂到 HookManager。

    tier0: prefetch（turn_complete，priority=190，每轮）
    tier1: write_turn_lightweight（turn_complete，priority=200，每轮）
    tier2: reflect_on_last_n_turns（turn_complete，priority=210，每 N 轮）
    tier3: curate_session（conversation_complete，priority=220）
    """
    if memory_bundle is None:
        return

    manager = memory_bundle.manager
    pipeline = getattr(memory_bundle, "pipeline", None)

    # tier2 反思的轮次来源：V2 build_turn_complete_context 不传
    # extra.turns，这里由 tier1（每轮必触发）把本轮问答存入闭包缓冲，
    # tier2 触发时取最近 N 轮。maxlen 即反思窗口大小。
    turns_buffer: deque = deque(maxlen=reflection_interval)

    hooks: list = []

    # Tier 0: prefetch — 下一轮预取记忆，fire-and-forget
    if pipeline is not None:
        async def _tier0_prefetch(event: dict, _runtime: dict) -> None:
            try:
                # 轮末预热：用本轮完整问答对作为预取查询（对齐 V1
                # hook_dispatcher.memory_prefetch_function）。
                query = "\n".join(
                    p
                    for p in (
                        event.get("user_prompt") or "",
                        event.get("final_answer") or "",
                    )
                    if p
                )
                if not query:
                    return
                result = await manager.retrieve_relevant_memories(
                    query=query,
                    exclude_rooms=["profile", "preference"],
                )
                cache = pipeline.get_prefetch_cache()
                cache.set_result(event.get("user_prompt", ""), result)
            except Exception:
                pass  # fire-and-forget，不阻塞 turn

        FunctionRegistry.register("_v2_memory_tier0_prefetch", _tier0_prefetch)
        hooks.append(HookConfig(
            name="memory_tier0_prefetch",
            trigger=HookTriggerConfig(
                trigger_type=HookTriggerType.TURN_COMPLETE.value,
                every_n_turns=1,
            ),
            endpoint=HookEndpointConfig(
                kind=HookKind.FUNCTION,
                function_name="_v2_memory_tier0_prefetch",
                blocking=False,
                timeout=8,  # hermes 对齐：记忆 hook 8s 熔断
            ),
            priority=190,
        ))

    # Tier 1: write_turn_lightweight — 每轮轻量写入
    async def _tier1_write(event: dict, _runtime: dict) -> None:
        user_msg = event.get("user_prompt", "")
        ai_msg = event.get("final_answer", "")
        if user_msg or ai_msg:
            turns_buffer.append({"user": user_msg, "assistant": ai_msg})
        await manager.write_turn_lightweight(
            user_message=user_msg,
            agent_response=ai_msg,
            metadata={
                "conv_id": event.get("conv_id"),
                "round": event.get("round"),
                "tier": 1,
            },
        )

    FunctionRegistry.register("_v2_memory_tier1_write", _tier1_write)
    hooks.append(HookConfig(
        name="memory_tier1_turn",
        trigger=HookTriggerConfig(
            trigger_type=HookTriggerType.TURN_COMPLETE.value,
            every_n_turns=1,
        ),
        endpoint=HookEndpointConfig(
            kind=HookKind.FUNCTION,
            function_name="_v2_memory_tier1_write",
            blocking=False,
            timeout=8,
        ),
        priority=200,
    ))

    # Tier 2: reflect_on_last_n_turns — 每 N 轮跨轮反思
    async def _tier2_reflect(event: dict, _runtime: dict) -> None:
        # V1 路径在 base_agent.py 把 turns 放在 event["extra"]["turns"]；
        # V2 由上面的 tier1 闭包缓冲提供最近 N 轮问答。
        extra = event.get("extra") or {}
        turns = extra.get("turns") or list(turns_buffer)
        await manager.reflect_on_last_n_turns(
            n=reflection_interval,
            turns=turns,
        )

    FunctionRegistry.register("_v2_memory_tier2_reflect", _tier2_reflect)
    hooks.append(HookConfig(
        name="memory_tier2_reflect",
        trigger=HookTriggerConfig(
            trigger_type=HookTriggerType.TURN_COMPLETE.value,
            every_n_turns=reflection_interval,
        ),
        endpoint=HookEndpointConfig(
            kind=HookKind.FUNCTION,
            function_name="_v2_memory_tier2_reflect",
            blocking=False,
            timeout=120,  # LLM 反思需要更长窗口，仍有界
        ),
        priority=210,
    ))

    # Tier 3: curate_session — 会话结束 curation
    async def _tier3_curate(event: dict, _runtime: dict) -> None:
        # 同 tier2：从 event.extra 读 conversation_history；
        # V2 build_conversation_complete_context 暂未传该字段，留作后续工作。
        extra = event.get("extra") or {}
        history = extra.get("conversation_history")
        await manager.curate_session(
            conversation_history=history,
        )

    FunctionRegistry.register("_v2_memory_tier3_curate", _tier3_curate)
    hooks.append(HookConfig(
        name="memory_tier3_curate",
        trigger=HookTriggerConfig(
            trigger_type=HookTriggerType.CONVERSATION_COMPLETE.value,
        ),
        endpoint=HookEndpointConfig(
            kind=HookKind.FUNCTION,
            function_name="_v2_memory_tier3_curate",
            blocking=False,
            timeout=120,
        ),
        priority=220,
    ))

    hook_manager.append_hooks(hooks)
