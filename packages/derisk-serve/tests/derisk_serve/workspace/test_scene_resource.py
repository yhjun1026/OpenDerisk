"""WorkspaceSceneResource 资源协议实现测试。"""
from unittest.mock import MagicMock, patch


def test_declare_produces_system_and_tools_contributions():
    from derisk_serve.workspace.scene_resource import (
        WorkspaceSceneConfig, WorkspaceSceneResource,
    )

    config = WorkspaceSceneConfig(workspace_id=1, conv_uid="c1", workspace_name="营收空间")
    with patch("derisk_serve.workspace.scene_resource.build_scene_management_tools") as mtools:
        mtools.return_value = [MagicMock(name="list_tasks"), MagicMock(name="start_task")]
        contribs = WorkspaceSceneResource.declare(config)
    slots = [c.slot for c in contribs]
    # 1 SYSTEM + 2 TOOLS
    from derisk.core.interface.resource.bundle import Slot
    system_count = sum(1 for c in contribs if c.slot == Slot.SYSTEM)
    tools_count = sum(1 for c in contribs if c.slot == Slot.TOOLS)
    assert system_count == 1
    assert tools_count == 2
    sys_contrib = next(c for c in contribs if c.slot == Slot.SYSTEM)
    assert "营收空间" in sys_contrib.content
    assert "list_tasks" in sys_contrib.content  # 工具引导文本含工具名


def test_declare_is_pure_no_io():
    """declare 不查 DB:不传 workspace_name 的真实查询,只用 config。"""
    from derisk_serve.workspace.scene_resource import (
        WorkspaceSceneConfig, WorkspaceSceneResource,
    )
    config = WorkspaceSceneConfig(workspace_id=1, conv_uid="c1", workspace_name="x")
    with patch("derisk_serve.workspace.scene_resource.build_scene_management_tools") as mtools:
        mtools.return_value = []
        WorkspaceSceneResource.declare(config)
    mtools.assert_called_once_with(1, "c1")


def test_build_scene_management_tools_full_set():
    from derisk_serve.workspace.scene_resource import build_scene_management_tools
    tools = build_scene_management_tools(1, "c1")
    names = {t.name for t in tools}
    for must in ("list_tasks", "get_task_info", "list_artifacts", "list_deliveries",
                 "list_assets", "list_playbooks", "get_playbook_detail", "list_interventions",
                 "start_task", "close_task", "create_playbook", "update_playbook",
                 "delete_playbook", "resolve_intervention", "abort_intervention",
                 "publish_asset", "create_delivery", "update_workspace"):
        assert must in names, f"missing {must}"
