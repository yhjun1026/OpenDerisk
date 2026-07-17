"""workspace_scene capability factory 测试:build_pack 能从 AgentResource 还原。

RFC-006 SSR Task 3:注册 type_key="workspace_scene" 的 factory,使
CapabilityFactoryRegistry.build_pack 能从 AgentResource(type=workspace_scene)
重建 WorkspaceSceneResource-backed Capability,其 declare() 产出 SYSTEM + TOOLS
Contribution。
"""
from unittest.mock import MagicMock, patch


def test_workspace_scene_factory_registered():
    """discover() 扫到 derisk_serve.agent.capabilities.workspace_scene,
    factory 注册到 _factories["workspace_scene"]。"""
    from derisk.agent.capabilities.registry_factory import (
        CapabilityFactoryRegistry,
    )

    reg = CapabilityFactoryRegistry()
    reg.discover()
    assert "workspace_scene" in reg._factories


def test_workspace_scene_factory_builds_capability_from_value_dict():
    """factory 接 dict 形 value 还原 Capability,declare 产 SYSTEM Contribution。"""
    from derisk_serve.workspace.scene_capability import (
        WorkspaceSceneCapability,
        workspace_scene_factory,
    )

    value = {"workspace_id": 1, "conv_uid": "c1", "workspace_name": "营收"}
    cap = workspace_scene_factory(value, system_app=MagicMock())
    assert isinstance(cap, WorkspaceSceneCapability)
    assert cap.capability_id == "workspace_scene"
    with patch(
        "derisk_serve.workspace.scene_resource.build_scene_management_tools"
    ) as mtools:
        mtools.return_value = [MagicMock(name="list_tasks")]
        contribs = cap.declare()
    from derisk.core.interface.resource.bundle import Slot

    assert any(c.slot == Slot.SYSTEM for c in contribs)
    assert any(c.slot == Slot.TOOLS for c in contribs)
    sys_contrib = next(c for c in contribs if c.slot == Slot.SYSTEM)
    assert "营收" in sys_contrib.content


def test_workspace_scene_factory_builds_capability_from_json_string():
    """factory 接 JSON 字符串形 value(AgentResource.value 历史多为 str)。"""
    import json

    from derisk_serve.workspace.scene_capability import (
        WorkspaceSceneCapability,
        workspace_scene_factory,
    )

    value = json.dumps(
        {"workspace_id": 7, "conv_uid": "c7", "workspace_name": "财管空间"}
    )
    cap = workspace_scene_factory(value, system_app=MagicMock())
    assert isinstance(cap, WorkspaceSceneCapability)
    # round-trip:还原出的 config 字段保留
    assert cap._config.workspace_id == 7
    assert cap._config.conv_uid == "c7"
    assert cap._config.workspace_name == "财管空间"


def test_workspace_scene_factory_handles_normalized_envelope():
    """_normalize_value 的通用回退可能把 JSON 字符串包成
    {"db_name": <raw>, "value": <raw>} 形态;factory 应能从中取出真实 payload。"""
    import json

    from derisk_serve.workspace.scene_capability import (
        WorkspaceSceneCapability,
        workspace_scene_factory,
    )

    payload = json.dumps(
        {"workspace_id": 3, "conv_uid": "c3", "workspace_name": "x"}
    )
    envelope = {"db_name": payload, "name": "scene", "value": payload}
    cap = workspace_scene_factory(envelope, system_app=MagicMock())
    assert isinstance(cap, WorkspaceSceneCapability)
    assert cap._config.workspace_id == 3
    assert cap._config.conv_uid == "c3"


def test_build_pack_consumes_workspace_scene_agent_resource():
    """build_pack([AgentResource(type=workspace_scene)]) 产含 workspace_scene cap 的 pack。

    patch get_resource_manager 抛异常以模拟"workspace_scene 未在 ResourceManager 注册"
    的生产路径:_normalize_value 走通用回退,把 JSON string value 包成
    {"db_name": <json_str>, "value": <json_str>} 信封,factory 从中解包重组 config。
    (裸 MagicMock 会令 rm._type_to_resources.get() 返回 truthy MagicMock,触发异常的
    parameter_cls 分支,污染 value,故需显式 patch。)
    """
    import json
    from unittest.mock import patch

    from derisk.agent.capabilities.registry_factory import (
        CapabilityFactoryRegistry,
    )
    from derisk.agent.resource.base import AgentResource

    reg = CapabilityFactoryRegistry()
    reg.discover()
    ar = AgentResource(
        type="workspace_scene",
        name="scene",
        value=json.dumps(
            {"workspace_id": 1, "conv_uid": "c1", "workspace_name": "x"}
        ),
    )
    with patch(
        "derisk.agent.resource.manage.get_resource_manager",
        side_effect=RuntimeError("no rm in test"),
    ):
        pack = reg.build_pack([ar], system_app=MagicMock())
    cap_ids = [getattr(c, "capability_id", "?") for c in (pack.sub_resources or [])]
    assert any("workspace_scene" in str(i) for i in cap_ids), cap_ids
