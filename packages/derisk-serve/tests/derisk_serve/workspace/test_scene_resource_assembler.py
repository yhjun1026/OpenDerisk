"""SceneResourceAssembler 测试:lobby/workbench 装配 + 边界。

RFC-006 SSR Task 5:对话前按场景模式装配 AgentResource。
- lobby(task_id 为空) -> [WorkspaceSceneResource AgentResource]
- workbench 有 playbook_id -> [PlaybookResource AgentResource(完整 config)]
- workbench 无 playbook_id -> []
- 缺 workspace -> []
- 异常 -> [](装配器永不把异常抛入 chat 路径)
"""
import json
from unittest.mock import MagicMock, patch


def _ws_mock(name="营收空间"):
    """构造 workspace mock,确保 .name 是真实字符串(避开 MagicMock name= 构造陷阱:
    Magicmock(name=...) 设置的是 mock 自身的标识名,而非 .name 属性)。"""
    m = MagicMock()
    m.name = name  # 构造后赋值,使 getattr(ws, "name") 返回字符串
    return m


def _mock_system_app(workspace=None, task=None, playbook=None, missing_ws=False):
    sa = MagicMock()
    def get_component(name, cls=None):
        m = MagicMock()
        if name == "serve_workspace_service":
            m.get_by_id.return_value = None if missing_ws else (workspace or _ws_mock())
        elif name == "serve_task_service":
            m.get_by_id.return_value = task
        elif name == "serve_playbook_service":
            m.get_by_id.return_value = playbook
        return m
    sa.get_component.side_effect = get_component
    return sa


def test_lobby_assembles_workspace_scene_resource():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    sa = _mock_system_app(workspace=_ws_mock("营收空间"))
    out = SceneResourceAssembler.assemble(sa, workspace_id=1, task_id=None, conv_uid="c1")
    assert len(out) == 1
    assert out[0].type == "workspace_scene"
    data = json.loads(out[0].value) if isinstance(out[0].value, str) else out[0].value
    assert data["workspace_id"] == 1
    assert data["conv_uid"] == "c1"
    assert data["workspace_name"] == "营收空间"


def test_workbench_with_playbook_assembles_playbook_resource():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    task = MagicMock(); task.playbook_id = 7
    # 用真实 dict 的 declaration 构造 playbook,使 from_playbook_response -> to_agent_resource
    # 的整条路径产出 JSON 可序列化的 PlaybookConfig(零 I/O 序列化是 Task 4 的要求)。
    pb = MagicMock(); pb.id = 7; pb.name = "营收分析"
    pb.declaration = {"text_content": {"workflow": "step1"}}
    sa = _mock_system_app(task=task, playbook=pb)
    out = SceneResourceAssembler.assemble(sa, workspace_id=1, task_id=99, conv_uid="c1")
    assert len(out) == 1
    assert out[0].type == "playbook"


def test_workbench_materializes_playbook_skills():
    """_assemble_workbench 把剧本 declaration.skills/resources 物化成 agent 工具。

    否则剧本 skill 只在 system prompt 里是名字(剧本技能:...),agent 看到却没真实
    工具可调 -- 这是"还在用默认剧本 mock skill"问题的根因。
    """
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    task = MagicMock(); task.playbook_id = 7
    pb = MagicMock(); pb.id = 7; pb.name = "营收分析"
    pb.declaration = {
        "skills": ["data-analysis", "doc-coauthoring"],
        "context": {"resources": [{"type": "datasource", "ref": "prod_db"}]},
    }
    sa = _mock_system_app(task=task, playbook=pb)
    out = SceneResourceAssembler.assemble(sa, workspace_id=1, task_id=99, conv_uid="c1")
    types = [r.type for r in out]
    assert "playbook" in types                    # 剧本元资源
    assert types.count("skill(derisk)") == 2      # 2 个 skill 物化成工具
    assert "datasource" in types                  # context.resources 物化


def test_workbench_without_playbook_returns_empty():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    task = MagicMock(); task.playbook_id = None
    sa = _mock_system_app(task=task)
    assert SceneResourceAssembler.assemble(sa, 1, 99, "c1") == []


def test_missing_workspace_returns_empty():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    sa = _mock_system_app(missing_ws=True)
    assert SceneResourceAssembler.assemble(sa, 1, None, "c1") == []


def test_exception_returns_empty_never_raises():
    """装配器在 chat 预处理路径,任何异常都必须吞掉返回 []。"""
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    sa = MagicMock()
    sa.get_component.side_effect = RuntimeError("boom")
    assert SceneResourceAssembler.assemble(sa, 1, None, "c1") == []
