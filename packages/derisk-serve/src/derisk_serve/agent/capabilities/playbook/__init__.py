"""playbook capability —— 剧本资源能力自管目录(RFC-006 SSR Task 4)。

serve 层 capability 目录,供 ``CapabilityFactoryRegistry.discover()`` 扫描发现。

实际实现在 ``derisk_serve.playbook.resource.playbook_capability``
(PlaybookConfig / PlaybookResource 在 playbook/resource/ 模块);本子包仅做
注册桥接——暴露 ``register_capability_to(registry)`` 把 ``playbook_factory``
注册到 ``CapabilityFactoryRegistry._factories["playbook"]``,供构造期
``build_pack`` 从 ``AgentResource(type="playbook")`` 还原 Capability。

注:本目录的 ``resource.py`` 是 RFC-005 历史遗留的 PlaybookResource 副本,
本任务不动它;Task 4 的 capability 实现统一在 ``derisk_serve.playbook.resource``
模块,本 __init__ 仅做注册桥接。
"""

# 实现住在 playbook 模块(playbook_resource.py + playbook_capability.py)。
from derisk_serve.playbook.resource.playbook_capability import (  # noqa: F401
    PlaybookCapability,
    playbook_factory,
)

__all__ = ["PlaybookCapability", "playbook_factory"]

# RFC-006 SSR Task 4:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "playbook"


def register(registry) -> None:
    """CapabilityRegistry(声明侧)占位:playbook 走 factory 路径,
    声明侧无需注册实例。"""
    pass


def register_capability_to(registry) -> None:
    """注册 playbook_factory 到 CapabilityFactoryRegistry(构造期产 CapabilityPack)。

    被 ``CapabilityFactoryRegistry.discover()`` 扫 derisk_serve.agent.capabilities
    子包时调用。
    """
    registry.register(CAPABILITY_TYPE_KEY, playbook_factory)
