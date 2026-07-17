"""Regression test for SSR C1: runtime.run_task forwards assembled scene
resources to app_chat_v3 as dynamic_resources.

run_task bypasses the HTTP chat_completions endpoint (where
SceneResourceAssembler is wired), so it must assemble scene resources itself
and pass them through to app_chat_v3. This test pins that forwarding by
patching at the boundaries (multi_agents.app_chat_v3 and the services run_task
uses), preventing a C1 regression.
"""
from unittest.mock import MagicMock, patch

import pytest


def _make_task(task_id=11, workspace_id=1, playbook_id=7, conv_session_id="conv-t1"):
    t = MagicMock()
    t.id = task_id
    t.workspace_id = workspace_id
    t.playbook_id = playbook_id
    t.conv_session_id = conv_session_id
    t.title = "任务T1"
    t.description = ""
    t.status = "running"
    t.created_by_user_id = "u1"
    return t


def _make_playbook(playbook_id=7):
    pb = MagicMock()
    pb.id = playbook_id
    pb.name = "营收分析"
    pb.declaration = {}
    return pb


def _make_workspace():
    ws = MagicMock()
    ws.name = "营收空间"
    ws.default_agent_app_code = "chat_normal"
    ws.scenario_type = "data"
    return ws


def _mock_system_app(task=None, playbook=None, workspace=None):
    sa = MagicMock()

    def get_component(name, cls=None):
        m = MagicMock()
        if name == "serve_task_service":
            m.get_by_id.return_value = task
            m.start = MagicMock()
            m.transition = MagicMock()
        elif name == "serve_playbook_service":
            m.get_by_id.return_value = playbook
        elif name == "serve_workspace_service":
            m.get_by_id.return_value = workspace
        # artifact/delivery/intervention services: default MagicMock is fine
        return m

    sa.get_component.side_effect = get_component
    return sa


@pytest.mark.asyncio
async def test_run_task_forwards_dynamic_resources_to_app_chat_v3():
    from derisk_serve.playbook import runtime

    task = _make_task()
    playbook = _make_playbook()
    workspace = _make_workspace()
    system_app = _mock_system_app(task=task, playbook=playbook, workspace=workspace)

    # Sentinel AgentResource that the assembler "assembles" for this workbench
    # task (has playbook_id -> PlaybookResource).
    sentinel = MagicMock(type="playbook", name="sentinel_playbook_resource")

    # Patch app_chat_v3 to capture kwargs and return a conv id quickly so the
    # runtime proceeds past the launch step. We also patch _poll_chat_completion
    # to short-circuit the polling loop.
    captured_kwargs = {}

    async def fake_app_chat_v3(**kwargs):
        captured_kwargs.update(kwargs)
        return None, "agent-conv-1"

    async def fake_poll(_conv_id):
        return {"state": "COMPLETE", "is_final": True, "vis_final": "done", "user_answer": "done"}

    with patch.object(runtime.multi_agents, "app_chat_v3", side_effect=fake_app_chat_v3), \
         patch.object(runtime.SceneResourceAssembler, "assemble", return_value=[sentinel]) as m_assemble, \
         patch.object(runtime, "_poll_chat_completion", side_effect=fake_poll):
        result = await runtime.run_task(
            system_app=system_app, task_id=task.id, user_code="u1", sys_code=None,
        )

    # Assembler was invoked with the workbench shape (workspace_id + task_id + conv_uid)
    m_assemble.assert_called_once()
    _, akwargs = m_assemble.call_args
    assert akwargs["workspace_id"] == task.workspace_id
    assert akwargs["task_id"] == task.id
    assert akwargs["conv_uid"] == task.conv_session_id

    # app_chat_v3 received the assembled resources under dynamic_resources
    assert "dynamic_resources" in captured_kwargs, \
        "run_task must forward dynamic_resources to app_chat_v3 (C1 regression)"
    forwarded = captured_kwargs["dynamic_resources"]
    assert forwarded == [sentinel], \
        f"expected the assembled PlaybookResource to be forwarded, got {forwarded!r}"

    # The runtime completed on the happy path
    assert result["task_id"] == task.id
    assert result["status"] == "delivered"


@pytest.mark.asyncio
async def test_run_task_dynamic_resources_reach_ext_info_not_dropped():
    """Stricter: dynamic_resources is a list (not None/missing), matching how
    aggregation_chat reads ext_info['dynamic_resources'] (line ~178: get/extend).
    A falsy/missing value would silently assemble no resources."""
    from derisk_serve.playbook import runtime

    task = _make_task()
    playbook = _make_playbook()
    workspace = _make_workspace()
    system_app = _mock_system_app(task=task, playbook=playbook, workspace=workspace)

    sentinel = MagicMock(type="playbook")
    captured = {}

    async def fake_app_chat_v3(**kwargs):
        captured.update(kwargs)
        return None, "agent-conv-2"

    async def fake_poll(_conv_id):
        return {"state": "COMPLETE", "is_final": True, "vis_final": "done", "user_answer": "done"}

    with patch.object(runtime.multi_agents, "app_chat_v3", side_effect=fake_app_chat_v3), \
         patch.object(runtime.SceneResourceAssembler, "assemble", return_value=[sentinel]), \
         patch.object(runtime, "_poll_chat_completion", side_effect=fake_poll):
        await runtime.run_task(system_app=system_app, task_id=task.id)

    dr = captured.get("dynamic_resources")
    assert isinstance(dr, list) and len(dr) == 1 and dr[0] is sentinel