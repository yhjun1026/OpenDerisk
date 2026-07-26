"""Tests for Service._execute_tool_call: tool dispatch + status + context injection."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from derisk.agent.tools.base import ToolBase, ToolCategory, ToolRiskLevel
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.registry import register_builtin_tools, tool_registry
from derisk.agent.tools.result import ToolResult
from derisk.cron import CronJob, CronPayload, CronSchedule, PayloadKind, ScheduleKind


class _EchoTool(ToolBase):
    """Test-only tool: echoes context identity + resource state."""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="_test_echo",
            display_name="Echo",
            description="test echo",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.LOW,
        )

    def _define_parameters(self):
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, args, context=None):
        uid = getattr(context, "user_id", None) if context else None
        has_db = False
        if context and hasattr(context, "get_resource"):
            has_db = context.get_resource("db_resource") is not None
        return ToolResult.ok(output=f"uid={uid},db={has_db}", tool_name=self.name)


@pytest.fixture(autouse=True)
def _ensure_echo_registered():
    if not tool_registry._initialized:
        register_builtin_tools()
    tool_registry.register(_EchoTool())
    yield
    tool_registry.unregister("_test_echo")


class _StubService:
    """Service stub: _execute_tool_call/_inject_resources don't access self attrs."""

    def __init__(self):
        pass

    # Borrow real methods from Service
    from derisk_serve.cron.service.service import (
        Service as _Svc,
    )

    _execute_tool_call = _Svc._execute_tool_call
    _inject_resources = _Svc._inject_resources


def _make_job(tool_name, tool_args, workspace_id=None, user_id=None):
    return CronJob(
        id="j1",
        name="t",
        schedule=CronSchedule(kind=ScheduleKind.EVERY, every_ms=60000),
        payload=CronPayload(
            kind=PayloadKind.TOOL_CALL,
            tool_name=tool_name,
            tool_args=tool_args,
            workspace_id=workspace_id,
        ),
        created_by_user_id=user_id,
    )


def test_execute_tool_call_success():
    service = _StubService()
    job = _make_job("_test_echo", {"text": "hello"})
    ok = asyncio.run(service._execute_tool_call(job))
    assert ok is True


def test_execute_tool_call_tool_not_found():
    service = _StubService()
    job = _make_job("_nonexistent_tool_xyz", {})
    ok = asyncio.run(service._execute_tool_call(job))
    assert ok is False


def test_execute_tool_call_missing_tool_name():
    service = _StubService()
    job = _make_job(None, {})
    ok = asyncio.run(service._execute_tool_call(job))
    assert ok is False


def test_execute_tool_call_injects_user_id():
    """#4: created_by_user_id is propagated to ToolContext.user_id."""
    service = _StubService()
    job = _make_job("_test_echo", {"text": "hi"}, user_id="user-42")
    ok = asyncio.run(service._execute_tool_call(job))
    assert ok is True
    # _EchoTool output reflects context.user_id


def test_execute_tool_call_injects_resources_when_workspace():
    """#2: _inject_resources is called when payload.workspace_id is set."""
    service = _StubService()
    job = _make_job("_test_echo", {"text": "hi"}, workspace_id=7)
    with patch.object(service, "_inject_resources", new=AsyncMock()) as mock_inject:
        ok = asyncio.run(service._execute_tool_call(job))
    assert ok is True
    mock_inject.assert_called_once()
    # First arg is the ToolContext, second is workspace_id
    assert mock_inject.call_args.args[1] == 7


def test_execute_tool_call_no_inject_when_no_workspace():
    """#2: _inject_resources is NOT called when workspace_id is absent."""
    service = _StubService()
    job = _make_job("_test_echo", {"text": "hi"})
    with patch.object(service, "_inject_resources", new=AsyncMock()) as mock_inject:
        ok = asyncio.run(service._execute_tool_call(job))
    assert ok is True
    mock_inject.assert_not_called()
