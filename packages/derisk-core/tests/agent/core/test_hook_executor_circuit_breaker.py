"""P0 fix: memory hook circuit breaker — FUNCTION/AGENT hook executors
enforce endpoint.timeout and isolate exceptions so a hung/crashed memory
hook can never break the main conversation."""

import asyncio

from derisk.agent.core.hook.executors import (
    AgentHookExecutor,
    FunctionHookExecutor,
    FunctionRegistry,
)
from derisk.agent.core.hook.schema import (
    BlockingPolicy,
    HookEndpointConfig,
    HookEvent,
    HookKind,
)


def _event() -> HookEvent:
    return HookEvent(hook_event_name="turn_complete", conv_id="c1")


class TestFunctionHookCircuitBreaker:
    async def test_timeout_returns_continue(self):
        async def slow_fn(event, runtime):
            await asyncio.sleep(5)
            return {"action": "continue"}

        FunctionRegistry.register("_test_slow_hook", slow_fn)
        try:
            endpoint = HookEndpointConfig(
                kind=HookKind.FUNCTION,
                function_name="_test_slow_hook",
                timeout=1,
            )
            decision = await FunctionHookExecutor().execute(
                _event(), endpoint, {}
            )
            assert decision.action == BlockingPolicy.CONTINUE
        finally:
            FunctionRegistry.unregister("_test_slow_hook")

    async def test_exception_returns_continue(self):
        async def boom_fn(event, runtime):
            raise RuntimeError("memory backend on fire")

        FunctionRegistry.register("_test_boom_hook", boom_fn)
        try:
            endpoint = HookEndpointConfig(
                kind=HookKind.FUNCTION,
                function_name="_test_boom_hook",
                timeout=8,
            )
            decision = await FunctionHookExecutor().execute(
                _event(), endpoint, {}
            )
            assert decision.action == BlockingPolicy.CONTINUE
        finally:
            FunctionRegistry.unregister("_test_boom_hook")

    async def test_normal_function_still_runs(self):
        seen = {}

        async def ok_fn(event, runtime):
            seen["called"] = True
            return {"action": "continue"}

        FunctionRegistry.register("_test_ok_hook", ok_fn)
        try:
            endpoint = HookEndpointConfig(
                kind=HookKind.FUNCTION,
                function_name="_test_ok_hook",
                timeout=8,
            )
            decision = await FunctionHookExecutor().execute(
                _event(), endpoint, {}
            )
            assert decision.action == BlockingPolicy.CONTINUE
            assert seen.get("called")
        finally:
            FunctionRegistry.unregister("_test_ok_hook")


class TestAgentHookCircuitBreaker:
    async def test_dispatcher_timeout_returns_continue(self):
        async def slow_dispatcher(**kwargs):
            await asyncio.sleep(5)
            return {"action": "continue"}

        endpoint = HookEndpointConfig(
            kind=HookKind.AGENT, agent_name="MemoryReflectAgent", timeout=1
        )
        decision = await AgentHookExecutor().execute(
            _event(), endpoint, {"agent_dispatcher": slow_dispatcher}
        )
        assert decision.action == BlockingPolicy.CONTINUE

    async def test_dispatcher_exception_returns_continue(self):
        async def boom_dispatcher(**kwargs):
            raise RuntimeError("agent exploded")

        endpoint = HookEndpointConfig(
            kind=HookKind.AGENT, agent_name="MemoryReflectAgent", timeout=8
        )
        decision = await AgentHookExecutor().execute(
            _event(), endpoint, {"agent_dispatcher": boom_dispatcher}
        )
        assert decision.action == BlockingPolicy.CONTINUE
