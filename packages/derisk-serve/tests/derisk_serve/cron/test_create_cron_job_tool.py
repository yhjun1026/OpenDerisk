"""Tests for CreateCronJobTool: build toolCall / agentTurn payloads."""
import asyncio

from derisk.agent.tools.builtin.schedule.create_cron_job import CreateCronJobTool


def _tool():
    return CreateCronJobTool()


def test_build_toolcall_payload():
    args = {
        "name": "daily-call",
        "schedule_kind": "every",
        "every_minutes": 60,
        "payload_kind": "toolCall",
        "tool_name": "call_agent",
        "tool_args": {"agent_id": "data_analyst", "message": "run report"},
    }
    job = asyncio.run(_tool()._build_job_create(args, None))
    assert job is not None
    assert job.payload.kind.value == "toolCall"
    assert job.payload.tool_name == "call_agent"
    assert job.payload.tool_args == {"agent_id": "data_analyst", "message": "run report"}
    assert job.schedule.every_ms == 60 * 60 * 1000


def test_build_agentturn_payload_backward_compat():
    """agentTurn (default) still builds correctly without payload_kind."""
    args = {
        "name": "reminder",
        "schedule_kind": "cron",
        "cron_expr": "0 9 * * *",
        "message": "do the daily check",
    }
    job = asyncio.run(_tool()._build_job_create(args, None))
    assert job is not None
    assert job.payload.kind.value == "agentTurn"
    assert job.payload.message == "do the daily check"
    assert job.payload.tool_name is None
    assert job.schedule.expr == "0 9 * * *"


def test_execute_rejects_toolcall_without_tool_name():
    result = asyncio.run(
        _tool().execute(
            {
                "name": "t",
                "schedule_kind": "every",
                "every_minutes": 60,
                "payload_kind": "toolCall",
            },
            None,
        )
    )
    assert not result.success
    assert "tool_name" in result.error


def test_execute_rejects_agentturn_without_message():
    result = asyncio.run(
        _tool().execute(
            {
                "name": "t",
                "schedule_kind": "every",
                "every_minutes": 60,
                "payload_kind": "agentTurn",
            },
            None,
        )
    )
    assert not result.success
    assert "message" in result.error
