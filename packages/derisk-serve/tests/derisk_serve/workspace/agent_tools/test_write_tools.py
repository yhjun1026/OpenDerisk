"""场景管理写工具测试:剧本写 + 介入审批工具新增。"""
from unittest.mock import MagicMock, patch


def test_build_scene_write_tools_includes_playbook_and_intervention_tools():
    """build_scene_write_tools 产出含 create_playbook/update_playbook/delete_playbook/
    resolve_intervention/abort_intervention + 原有 start_task/close_task 等。"""
    from derisk_serve.workspace.agent_tools.write_tools import build_scene_write_tools
    tools = build_scene_write_tools(
        system_app=MagicMock(), workspace_id=1, user_id="u1",
        conv_uid="c1", task_id=None,
    )
    names = {t.name for t in tools}
    for must in ("start_task", "close_task", "create_playbook", "update_playbook",
                 "delete_playbook", "resolve_intervention", "abort_intervention",
                 "publish_asset", "create_delivery", "update_workspace"):
        assert must in names, f"missing tool {must}; got {names}"


def test_create_playbook_tool_calls_playbook_service_create():
    """create_playbook 工具调 playbook_service.create。"""
    from derisk_serve.workspace.agent_tools.write_tools import build_scene_write_tools
    with patch(
        "derisk_serve.workspace.agent_tools.write_tools.get_playbook_service"
    ) as mks:
        svc = MagicMock(); mks.return_value = svc; svc.create.return_value = MagicMock(id=9)
        tools = {t.name: t for t in build_scene_write_tools(
            MagicMock(), 1, "u1", "c1")}
        tool = tools["create_playbook"]
        # FunctionTool stores the callable in _func (no public .func property)
        res = tool._func(name="p", declaration_dsl="{}", workspace_id=1)
        svc.create.assert_called_once()
        assert res["playbook_id"] == 9
