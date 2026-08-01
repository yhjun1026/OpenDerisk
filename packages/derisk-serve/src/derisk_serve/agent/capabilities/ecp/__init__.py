"""ecp capability -- 企业语义层能力自管目录(ECP P1「通电」)。

serve 层 capability 目录,供 ``CapabilityFactoryRegistry.discover()`` 扫描发现。
实现住在 ``derisk_serve.agent.capabilities.ecp.capability``;本子包仅做注册桥接--
暴露 ``register_capability_to(registry)`` 把 ``ecp_factory`` 注册到
``CapabilityFactoryRegistry._factories["ecp"]``,供构造期 ``build_pack`` 从
``AgentResource(type="ecp")`` 还原 ``ECPCapability``。
"""

from derisk_serve.agent.capabilities.ecp.capability import (  # noqa: F401
    ECPCapability,
    ecp_factory,
)

__all__ = ["ECPCapability", "ecp_factory"]

# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "ecp"


def register(registry) -> None:
    """CapabilityRegistry(声明侧)占位:ecp 走 factory 路径,声明侧无需注册实例。"""
    pass


def register_capability_to(registry) -> None:
    """注册 ecp_factory 到 CapabilityFactoryRegistry(构造期产 Capability)。

    被 ``CapabilityFactoryRegistry.discover()`` 扫 derisk_serve.agent.capabilities
    子包时调用。
    """
    registry.register(CAPABILITY_TYPE_KEY, ecp_factory)
