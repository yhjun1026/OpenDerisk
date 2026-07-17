"""workspace_scene capability —— 场景空间管理能力自管目录(RFC-006 SSR Task 3)。

serve 层 capability 目录,供 ``CapabilityFactoryRegistry.discover()`` 扫描发现。

实际实现在 ``derisk_serve.workspace.scene_capability``( WorkplaceSceneConfig
/ WorkspaceSceneResource 在 workspace/ 模块);本子包仅做注册桥接——暴露
``register_capability_to(registry)`` 把 ``workspace_scene_factory`` 注册到
``CapabilityFactoryRegistry._factories["workspace_scene"]``,供构造期
``build_pack`` 从 ``AgentResource(type="workspace_scene")`` 还原 Capability。
"""

# 实现住在 workspace 模块(scene_resource.py + scene_capability.py)。
from derisk_serve.workspace.scene_capability import (  # noqa: F401
    WorkspaceSceneCapability,
    workspace_scene_factory,
)

__all__ = ["WorkspaceSceneCapability", "workspace_scene_factory"]

# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "workspace_scene"


def register(registry) -> None:
    """CapabilityRegistry(声明侧)占位:workspace_scene 走 factory 路径,
    声明侧无需注册实例。"""
    pass


def register_capability_to(registry) -> None:
    """注册 workspace_scene_factory 到 CapabilityFactoryRegistry(构造期产 CapabilityPack)。

    被 ``CapabilityFactoryRegistry.discover()`` 扫 derisk_serve.agent.capabilities
    子包时调用。
    """
    registry.register(CAPABILITY_TYPE_KEY, workspace_scene_factory)
