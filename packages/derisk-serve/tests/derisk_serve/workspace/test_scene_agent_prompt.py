from unittest.mock import MagicMock

from derisk_serve.workspace.agent_prompts.scene_agent_prompt import (
    SCENE_AGENT_STATIC_PROMPT,
    render_scene_dynamic_context,
)
from derisk_serve.workspace.agent_tools.context_builder import WorkspaceContextSnapshot


def test_static_prompt_contains_identity():
    assert "场景空间助手" in SCENE_AGENT_STATIC_PROMPT
    assert "当前工作空间的协作者" in SCENE_AGENT_STATIC_PROMPT


def _make_workspace(name: str, workspace_id: int = 1):
    ws = MagicMock(id=workspace_id)
    ws.name = name
    return ws


def test_render_lobby_includes_playbooks_and_active_tasks():
    ws = _make_workspace("Ops空间")
    fake_playbook = MagicMock(id=7, scenario_type="report")
    fake_playbook.name = "报告生成"
    fake_active_task = MagicMock(id=4, status="running")
    fake_active_task.title = "修复告警"
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        playbooks=[fake_playbook],
        active_tasks=[fake_active_task],
        user_id="u1",
        workspace_id=1,
    )
    result = render_scene_dynamic_context(ctx, mode="lobby")
    assert "进行中任务" in result
    assert "修复告警" in result
    assert "get_playbook_detail" in result
    assert "start_task" in result
    assert "list_triggers" in result
    assert "fire_trigger" in result


def test_render_workbench_includes_current_task():
    ws = _make_workspace("Ops空间")
    fake_task = MagicMock(id=5, title="Fix bug", description="desc", status="running")
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        task=fake_task,
        playbook_declaration={"skills": [{"name": "analyze"}]},
        user_id="u1",
        workspace_id=1,
        task_id=5,
    )
    result = render_scene_dynamic_context(ctx, mode="workbench")
    assert "Fix bug" in result
    assert "当前任务详情" in result
    assert "create_playbook" in result
    assert "update_trigger" in result
    assert "list_interventions" in result


def test_render_focus_block_with_meta_and_snippet():
    ws = _make_workspace("Ops空间")
    art = MagicMock(id=42, title="周报", type="report", content_text="正文内容")
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        focused_artifact=art,
    )
    result = render_scene_dynamic_context(ctx, mode="lobby")
    assert "用户当前关注" in result
    assert "周报" in result
    assert "report" in result
    assert "内容摘要" in result
    assert "正文内容" in result


def test_render_focus_block_truncates_long_content():
    ws = _make_workspace("Ops空间")
    art = MagicMock(id=1, title="t", type="report", content_text="x" * 1000)
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        focused_artifact=art,
    )
    result = render_scene_dynamic_context(ctx, mode="lobby")
    assert "…" in result
    assert "x" * 600 not in result


def test_render_focus_block_no_snippet_when_content_empty():
    ws = _make_workspace("Ops空间")
    art = MagicMock(id=1, title="t", type="report", content_text=None)
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
        focused_artifact=art,
    )
    result = render_scene_dynamic_context(ctx, mode="lobby")
    assert "用户当前关注" in result
    assert "内容摘要" not in result


def test_render_no_focus_block_when_absent():
    ws = _make_workspace("Ops空间")
    ctx = WorkspaceContextSnapshot(
        workspace=ws,
        materialized_resources=MagicMock(dynamic_resources=[], extra_agents=[]),
    )
    result = render_scene_dynamic_context(ctx, mode="lobby")
    assert "用户当前关注" not in result