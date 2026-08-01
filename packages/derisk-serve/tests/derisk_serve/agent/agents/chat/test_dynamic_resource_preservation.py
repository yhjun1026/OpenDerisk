"""Regression test: 场景装配器预注入的动态资源必须穿过 _inner_chat 重建保留。

背景:ECP 资源未注入问题。SceneResourceAssembler 在 api_v1/playbook runtime
预注入 AgentResource(type="ecp"/"workspace_scene") 到 ext_info["dynamic_resources"]。
_inner_chat 重建动态资源时(chat_in_params + extraTools + 默认绑定库),曾用重建结果
直接覆盖 ext_info["dynamic_resources"],丢掉场景资源 -> build_pack 永远拿不到 ecp ->
ECPCapability 不构建 -> "ECP 资源未注入"。

修复:AgentChat._preserve_scene_resources 把预注入的场景资源前置合并到重建结果,
契约 preserved/extended, never overwritten(见 playbook/runtime.py 注释)。
"""
import json

from derisk.agent.resource.base import AgentResource
from derisk_serve.agent.agents.chat.agent_chat import AgentChat


def _ecp_resource(workspace_id="ecp_ws_abc"):
    return AgentResource(
        type="ecp", name="ecp",
        value=json.dumps({"workspace_id": workspace_id}, ensure_ascii=False),
    )


def _db_resource(name="prod_db"):
    return AgentResource(type="datasource", name=name, value=json.dumps({"datasource": {"name": name}}))


def test_scene_resources_preserved_when_rebuilt_has_db():
    """核心回归:场景 ecp 资源 + 重建的 db 资源共存,ecp 必须保留在前。

    复现原 bug:场景空间绑定了数据源(default_db)时,重建覆盖会丢掉 ecp。
    """
    scene = [_ecp_resource()]
    rebuilt = [_db_resource()]
    out = AgentChat._preserve_scene_resources(scene, rebuilt)
    types = [r.type for r in out]
    assert "ecp" in types, "场景 ecp 资源被重建覆盖丢失(回归)"
    assert "datasource" in types
    assert types[0] == "ecp"  # 场景资源置前


def test_scene_resources_preserved_when_rebuilt_empty():
    """重建为空时场景资源仍保留(无默认绑定库的 lobby 对话)。"""
    scene = [_ecp_resource()]
    out = AgentChat._preserve_scene_resources(scene, [])
    assert [r.type for r in out] == ["ecp"]


def test_scene_resources_preserved_when_rebuilt_none():
    """chat_in_params_to_resource 返回 None 时场景资源仍保留。"""
    scene = [_ecp_resource()]
    out = AgentChat._preserve_scene_resources(scene, None)
    assert [r.type for r in out] == ["ecp"]


def test_no_scene_resources_returns_rebuilt_unchanged():
    """非场景对话(无预注入资源)行为不变:原样返回重建结果。"""
    rebuilt = [_db_resource("a"), _db_resource("b")]
    out = AgentChat._preserve_scene_resources([], rebuilt)
    assert out is rebuilt or [r.name for r in out] == ["a", "b"]


def test_no_scene_resources_and_empty_rebuilt_returns_empty_list():
    """无场景资源且重建为空 -> 返回 [](非场景、无动态资源的普通对话)。"""
    assert AgentChat._preserve_scene_resources([], None) == []
    assert AgentChat._preserve_scene_resources([], []) == []


def test_original_scene_list_not_mutated():
    """合并产出新列表,不就地改动原 ext_info["dynamic_resources"] 引用。"""
    scene = [_ecp_resource()]
    out = AgentChat._preserve_scene_resources(scene, [_db_resource()])
    out.append(_db_resource("extra"))
    assert len(scene) == 1, "原场景资源列表不应被合并结果的反向修改影响"
