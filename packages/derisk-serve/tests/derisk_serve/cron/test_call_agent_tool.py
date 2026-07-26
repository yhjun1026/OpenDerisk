"""Tests for CallAgentTool: param validation + app_chat_v3 invocation."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from derisk.agent.tools.builtin.schedule.call_agent import CallAgentTool
from derisk.agent.tools.context import ToolContext


def test_call_agent_success_isolated_creates_new_conv():
    tool = CallAgentTool()
    with patch("derisk_serve.agent.agents.controller.multi_agents") as mock_ma:
        mock_ma.app_chat_v3 = AsyncMock(return_value=(None, "agent-conv-1"))
        result = asyncio.run(
            tool.execute({"agent_id": "data_analyst", "message": "run report"}, None)
        )
    assert result.success
    assert "conv_uid" in result.metadata
    # isolated mode -> new uuid (not a fixed session id)
    assert result.metadata["session_mode"] == "isolated"
    call_kwargs = mock_ma.app_chat_v3.call_args.kwargs
    assert call_kwargs["gpts_name"] == "data_analyst"
    assert call_kwargs["user_query"] == "run report"
    assert call_kwargs["stream"] is False


def test_call_agent_shared_reuses_conv_session_id():
    tool = CallAgentTool()
    with patch("derisk_serve.agent.agents.controller.multi_agents") as mock_ma:
        mock_ma.app_chat_v3 = AsyncMock(return_value=(None, "agent-conv-1"))
        result = asyncio.run(
            tool.execute(
                {
                    "agent_id": "x",
                    "message": "follow up",
                    "session_mode": "shared",
                    "conv_session_id": "conv-existing",
                },
                None,
            )
        )
    assert result.success
    assert result.metadata["conv_uid"] == "conv-existing"
    assert mock_ma.app_chat_v3.call_args.kwargs["conv_uid"] == "conv-existing"


def test_call_agent_missing_params_fails():
    tool = CallAgentTool()
    result = asyncio.run(tool.execute({"agent_id": "x"}, None))
    assert not result.success


def test_call_agent_shared_persists_session_id_under_cron_job():
    """#3: SHARED + cron_job_id in context -> persist conv_session_id to job."""
    tool = CallAgentTool()
    ctx = ToolContext()
    ctx.config["cron_job_id"] = "job-1"

    mock_entity = MagicMock()
    mock_entity.conv_session_id = None  # differs from sess-1 -> will update
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = mock_entity
    mock_service = MagicMock()
    mock_service.dao.session.return_value.__enter__.return_value = mock_session
    mock_service.dao.session.return_value.__exit__.return_value = False

    with patch("derisk_serve.agent.agents.controller.multi_agents") as mock_ma:
        mock_ma.app_chat_v3 = AsyncMock(return_value=(None, "agent-conv-1"))
        with patch(
            "derisk_serve.cron.service.service.session_id_by_conv_id",
            return_value="sess-1",
        ):
            with patch("derisk._private.config.Config") as mock_cfg:
                mock_cfg.return_value.SYSTEM_APP.get_component.return_value = mock_service
                result = asyncio.run(
                    tool.execute(
                        {
                            "agent_id": "x",
                            "message": "hi",
                            "session_mode": "shared",
                            "conv_session_id": "old",
                        },
                        ctx,
                    )
                )
    assert result.success
    assert mock_entity.conv_session_id == "sess-1"
    mock_session.commit.assert_called_once()


def test_call_agent_no_persist_without_cron_job_id():
    """#3: no cron_job_id in context (interactive use) -> skip persist."""
    tool = CallAgentTool()
    ctx = ToolContext()  # no cron_job_id
    with patch("derisk_serve.agent.agents.controller.multi_agents") as mock_ma:
        mock_ma.app_chat_v3 = AsyncMock(return_value=(None, "agent-conv-1"))
        with patch("derisk._private.config.Config") as mock_cfg:
            result = asyncio.run(
                tool.execute(
                    {
                        "agent_id": "x",
                        "message": "hi",
                        "session_mode": "shared",
                        "conv_session_id": "conv-x",
                    },
                    ctx,
                )
            )
    assert result.success
    # Persist returns before touching Config when cron_job_id is absent
    mock_cfg.assert_not_called()
