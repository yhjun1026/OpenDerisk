"""Tests for AIWrapper.create usage recording (the capture hook in finally)."""

import asyncio

from derisk.agent.util.llm.llm_client import AIWrapper
from derisk.agent.util.llm.usage_recorder import (
    LLMUsageRecord,
    clear_llm_usage_recorders,
    register_llm_usage_recorder,
)
from derisk.core.interface.llm import ModelOutput


class _MockProvider:
    """Minimal provider returning a fixed usage."""

    def __init__(self, *, stream: bool):
        self._stream = stream

    async def generate(self, request):
        return ModelOutput(
            error_code=0,
            text="hello",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    async def generate_stream(self, request):
        yield ModelOutput(error_code=0, text="hel", incremental=True)
        yield ModelOutput(error_code=0, text="lo", incremental=True)
        # usage-only terminator (mirrors provider fix)
        yield ModelOutput(
            error_code=0,
            text="",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )


def _run(coro):
    return asyncio.run(coro)


def _make_wrapper(stream: bool) -> AIWrapper:
    ai = AIWrapper()
    ai._provider = _MockProvider(stream=stream)
    return ai


def _capture():
    captured: list[LLMUsageRecord] = []

    async def cap(rec: LLMUsageRecord):
        captured.append(rec)

    clear_llm_usage_recorders()
    register_llm_usage_recorder(cap)
    return captured


def test_non_stream_records_usage():
    ai = _make_wrapper(stream=False)
    captured = _capture()

    async def run():
        async for _ in ai.create(
            messages=[{"role": "user", "content": "hi"}],
            llm_model="fake-model",
            stream_out=False,
        ):
            pass

    _run(run())

    assert len(captured) == 1, captured
    r = captured[0]
    assert r.prompt_tokens == 10
    assert r.completion_tokens == 5
    assert r.total_tokens == 15
    assert r.model_name == "fake-model"
    assert r.stream is False
    assert r.error_code == 0
    assert r.latency_ms >= 0


def test_stream_records_usage_from_terminator():
    ai = _make_wrapper(stream=True)
    captured = _capture()

    async def run():
        async for _ in ai.create(
            messages=[{"role": "user", "content": "hi"}],
            llm_model="fake-model",
            stream_out=True,
        ):
            pass

    _run(run())

    assert len(captured) == 1, captured
    r = captured[0]
    assert r.prompt_tokens == 10
    assert r.completion_tokens == 5
    assert r.total_tokens == 15
    assert r.stream is True
    assert r.error_code == 0
    # first token time should be captured during streaming
    assert r.first_token_ms is not None


def test_error_path_still_records():
    class _ErrProvider:
        async def generate(self, request):
            return ModelOutput(error_code=1, text="boom")

        async def generate_stream(self, request):
            yield ModelOutput(error_code=1, text="boom")

    ai = AIWrapper()
    ai._provider = _ErrProvider()
    captured = _capture()

    async def run():
        try:
            async for _ in ai.create(
                messages=[{"role": "user", "content": "hi"}],
                llm_model="fake-model",
                stream_out=False,
            ):
                pass
        except Exception:
            pass

    _run(run())

    assert len(captured) == 1, captured
    assert captured[0].error_code == 1
