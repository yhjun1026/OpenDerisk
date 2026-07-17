"""playbook capability factory + to_agent_resource 测试(RFC-006 SSR Task 4)。

镜像 Task 3(workspace_scene)的测试形态:
- discover() 扫 derisk_serve.agent.capabilities.playbook,注册 factory 到 _factories["playbook"]。
- factory 从 dict / JSON string / _normalize_value 信封 还原 PlaybookCapability,
  declare() 产出 SYSTEM + TOOLS Contribution(真实 PlaybookResource.declare 输出)。
- to_agent_resource 序列化完整 PlaybookConfig(零 I/O factory),round-trip 保字段。
- build_pack([AgentResource(type="playbook")]) 产含 playbook capability 的 pack。
"""
import json
from unittest.mock import MagicMock, patch

import pytest


def test_playbook_factory_registered():
    """discover() 扫到 derisk_serve.agent.capabilities.playbook,
    factory 注册到 _factories["playbook"]。"""
    from derisk.agent.capabilities.registry_factory import (
        CapabilityFactoryRegistry,
    )

    reg = CapabilityFactoryRegistry()
    reg.discover()
    assert "playbook" in reg._factories


def test_playbook_factory_builds_capability_from_value_dict():
    """factory 接 dict 形 value(含完整 config 字段)还原 Capability,
    declare() 产 SYSTEM + TOOLS Contribution。"""
    from derisk_serve.playbook.resource.playbook_capability import (
        PlaybookCapability,
        playbook_factory,
    )

    value = {
        "playbook_id": 7,
        "playbook_name": "营收分析",
        "text_content": {"workflow": "step1", "role_definition": "analyst"},
        "skills": ["s1"],
        "resources": [{"type": "datasource", "name": "db1"}],
        "deliverables": [{"type": "report", "title": "月报"}],
        "distill": {"forced": True},
    }
    cap = playbook_factory(value, system_app=MagicMock())
    assert isinstance(cap, PlaybookCapability)
    assert cap.capability_id == "playbook"
    contribs = cap.declare()
    from derisk.core.interface.resource.bundle import Slot

    assert any(c.slot == Slot.SYSTEM for c in contribs)
    assert any(c.slot == Slot.TOOLS for c in contribs)
    sys_contrib = next(c for c in contribs if c.slot == Slot.SYSTEM)
    assert "营收分析" in sys_contrib.content


def test_playbook_factory_builds_capability_from_json_string():
    """factory 接 JSON 字符串形 value(AgentResource.value 历史多为 str)。"""
    from derisk_serve.playbook.resource.playbook_capability import (
        PlaybookCapability,
        playbook_factory,
    )

    value = json.dumps(
        {"playbook_id": 7, "playbook_name": "财管剧本"}
    )
    cap = playbook_factory(value, system_app=MagicMock())
    assert isinstance(cap, PlaybookCapability)
    assert cap._config.playbook_id == 7
    assert cap._config.playbook_name == "财管剧本"


def test_playbook_factory_handles_normalized_envelope():
    """_normalize_value 通用回退把 JSON 字符串包成
    {"db_name": <raw>, "value": <raw>} 信封;factory 从中解包重组 config。"""
    from derisk_serve.playbook.resource.playbook_capability import (
        PlaybookCapability,
        playbook_factory,
    )

    payload = json.dumps(
        {"playbook_id": 3, "playbook_name": "x"}
    )
    envelope = {"db_name": payload, "name": "playbook", "value": payload}
    cap = playbook_factory(envelope, system_app=MagicMock())
    assert isinstance(cap, PlaybookCapability)
    assert cap._config.playbook_id == 3
    assert cap._config.playbook_name == "x"


def test_playbook_factory_returns_none_on_invalid_value():
    """无法解析的 value 返回 None(build_pack 跳过,不阻塞)。"""
    from derisk_serve.playbook.resource.playbook_capability import (
        playbook_factory,
    )

    assert playbook_factory(12345, system_app=MagicMock()) is None
    assert playbook_factory("not-json", system_app=MagicMock()) is None


def test_playbook_to_agent_resource_roundtrip():
    """to_agent_resource 序列化完整 PlaybookConfig,factory 反序列化保字段。"""
    from derisk_serve.playbook.resource.playbook_resource import (
        PlaybookConfig,
        PlaybookResource,
        PlaybookTextContent,
    )
    from derisk_serve.playbook.resource.playbook_capability import (
        PlaybookCapability,
        playbook_factory,
    )

    cfg = PlaybookConfig(
        playbook_id=7,
        playbook_name="营收分析",
        text_content=PlaybookTextContent(
            workflow="w", role_definition="r", goal="g"
        ),
        skills=["s1", "s2"],
        resources=[{"type": "datasource", "name": "db1"}],
        deliverables=[{"type": "report", "title": "月报"}],
        distill={"forced": True},
    )
    ar = PlaybookResource.to_agent_resource(cfg)
    assert ar.type == "playbook"
    data = json.loads(ar.value) if isinstance(ar.value, str) else ar.value
    assert data["playbook_id"] == 7
    assert data["playbook_name"] == "营收分析"
    # 完整 config 字段序列化(零 I/O factory 路径)
    assert data["text_content"]["workflow"] == "w"
    assert data["text_content"]["role_definition"] == "r"
    assert data["skills"] == ["s1", "s2"]
    assert data["deliverables"] == [{"type": "report", "title": "月报"}]
    assert data["distill"] == {"forced": True}

    # round-trip:factory 从 ar 还原,保全部字段(零 I/O)
    cap = playbook_factory(ar.value, system_app=MagicMock())
    assert isinstance(cap, PlaybookCapability)
    assert cap._config.playbook_id == 7
    assert cap._config.playbook_name == "营收分析"
    assert cap._config.text_content.workflow == "w"
    assert cap._config.text_content.role_definition == "r"
    assert cap._config.skills == ["s1", "s2"]
    assert cap._config.deliverables == [{"type": "report", "title": "月报"}]
    assert cap._config.distill == {"forced": True}


def test_build_pack_consumes_playbook_agent_resource():
    """build_pack([AgentResource(type=playbook)]) 产含 playbook cap 的 pack。

    patch get_resource_manager 抛异常以模拟"playbook 未在 ResourceManager 注册"
    的生产路径:_normalize_value 走通用回退,把 JSON string value 包成信封,
    factory 从中解包。"""
    from derisk.agent.capabilities.registry_factory import (
        CapabilityFactoryRegistry,
    )
    from derisk.agent.resource.base import AgentResource
    from derisk_serve.playbook.resource.playbook_resource import (
        PlaybookConfig,
        PlaybookResource,
    )

    reg = CapabilityFactoryRegistry()
    reg.discover()
    ar = PlaybookResource.to_agent_resource(
        PlaybookConfig(playbook_id=7, playbook_name="x")
    )
    with patch(
        "derisk.agent.resource.manage.get_resource_manager",
        side_effect=RuntimeError("no rm in test"),
    ):
        pack = reg.build_pack([ar], system_app=MagicMock())
    assert any(
        getattr(c, "capability_id", "").startswith("playbook")
        for c in (pack.sub_resources or [])
    )
