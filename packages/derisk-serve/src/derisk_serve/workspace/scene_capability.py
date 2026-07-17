"""WorkspaceSceneCapability — workspace_scene 自管理资源能力(RFC-006 SSR Task 3)。

把 Task 2 的 ``WorkspaceSceneResource.declare``(纯函数,产 SYSTEM + TOOLS
Contribution)包成自管理 ``Capability`` 对象,供 ``CapabilityFactoryRegistry``
在构造期(``agent_chat.build_agent_by_gpts``)从配置态 ``AgentResource`` 重建。
Agent 持有稳定 ``Capability`` 对象,而非每轮临时翻转 config。

设计取舍(对齐 DBCapability/MemoryCapability 既有约定):
- **继承** ``derisk.core.interface.resource.capability.Capability``(ABC,需实现
  declare/prepare/execute/release)。本能力的工具走 Route A builtin(场景空间
  管理 tools 暂由 react_master 装配,见 build_scene_management_tools),故
  ``execute`` 留占位 NotImplementedError;真实 live state 无(services 由
  system_app.resolve),``prepare``/``release`` no-op。
- **declare 委托** ``WorkspaceSceneResource.declare(config)``(复用 Task 2 纯函数,
  保持 SYSTEM 框架 + TOOLS 槽 Contribution)。
- **requires 空列表**:不依赖共享底座(如 sandbox),与 MemoryCapability 一致。
- **value 规范化** 在 factory 内自管:``CapabilityFactoryRegistry._normalize_value``
  的通用回退对 JSON string 形 value 会包成 ``{"db_name": <raw>, "value": <raw>}``
  (workspace_scene 未在 ResourceManager 注册 parameter_cls,故走回退)。factory
  需兼容三种入参:dict / JSON string / ``{"value": <json_str>, ...}`` 信封。

注册:type_key="workspace_scene",由 ``derisk_serve.agent.capabilities.workspace_scene``
子包的 ``register_capability_to(registry)`` 桥接(CapabilityFactoryRegistry.discover
扫 derisk_serve.agent.capabilities.* 子包)。
"""
from __future__ import annotations

import json
import logging
from typing import Any, List

from derisk.core.interface.resource.bundle import Contribution
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

from derisk_serve.workspace.scene_resource import (
    WorkspaceSceneConfig,
    WorkspaceSceneResource,
)

logger = logging.getLogger(__name__)


class WorkspaceSceneCapability(Capability):
    """场景空间自管理能力:declare 委托 WorkspaceSceneResource.declare。

    capability_id="workspace_scene";executor_id 同。无 live state(services
    由 system_app.resolve,非本对象持有),prepare/release 为 no-op。
    """

    capability_id = "workspace_scene"

    def __init__(self, config: WorkspaceSceneConfig, system_app: Any = None) -> None:
        self._config: WorkspaceSceneConfig = config
        self._system_app = system_app
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: Any, system_app: Any = None) -> "WorkspaceSceneCapability":
        """从 AgentResource.value 还原 Capability(无 I/O)。

        value 兼容三种形态:
        - dict:直接取字段(workspace_id/conv_uid/workspace_name)
        - JSON string:先 json.loads
        - ``{"db_name": <json_str>, "value": <json_str>, ...}`` 信封
          (_normalize_value 通用回退会把 JSON string 包成此形态):从 "value"
          或 "db_name" 取出 JSON string 再解析
        """
        data = _coerce_scene_value(value)
        if data is None:
            raise ValueError(
                f"workspace_scene factory: cannot coerce value to scene config: {value!r}"
            )
        config = WorkspaceSceneConfig(
            workspace_id=int(data.get("workspace_id")),
            conv_uid=data.get("conv_uid") or "",
            workspace_name=data.get("workspace_name") or "",
        )
        return cls(config, system_app=system_app)

    # ----------------------------- 输入投影(委托纯函数) ------------------- #
    def declare(self, config: WorkspaceSceneConfig | None = None) -> List[Contribution]:
        return WorkspaceSceneResource.declare(config or self._config)

    def requires(self, config: Any = None) -> List[str]:
        # 不依赖共享底座(sandbox),无 live executor 依赖。
        return []

    # ----------------------------- 生命周期(无 live state,no-op) -------- #
    async def prepare(self) -> None:
        # 服务由 system_app.resolve,本对象不持有连接;幂等置 READY。
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # 场景空间管理工具走 Route A builtin(react_master 装配),本 execute 未接。
        raise NotImplementedError(
            "WorkspaceSceneCapability.execute 未接 —— 场景空间管理工具暂走 Route A builtin"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED


def _coerce_scene_value(value: Any) -> dict | None:
    """把 AgentResource.value 规范化为 dict(含 workspace_id/conv_uid/workspace_name)。

    处理顺序:
    1. dict → 检查是否信封(``value``/``db_name`` 字段是 JSON string);
       若是信封则解包,否则直接用。
    2. str → json.loads。
    3. 有 to_dict() → 调用。
    其它 → None。
    """
    if value is None:
        return None
    if isinstance(value, dict):
        # 信封检查:_normalize_value 回退会把 JSON string 包成
        # {"db_name": <raw>, "name": ..., "value": <raw>} 形态。
        for key in ("value", "db_name"):
            inner = value.get(key)
            if isinstance(inner, str):
                try:
                    parsed = json.loads(inner)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    return parsed
        # 直接是 payload dict(workspace_id 等字段在顶层)
        if any(k in value for k in ("workspace_id", "conv_uid", "workspace_name")):
            return value
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"workspace_scene factory: JSON decode failed: {e}")
            return None
        return parsed if isinstance(parsed, dict) else None
    if hasattr(value, "to_dict"):
        try:
            d = value.to_dict()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"workspace_scene factory: to_dict() failed: {e}")
            return None
        return d if isinstance(d, dict) else None
    return None


def workspace_scene_factory(value: Any, system_app: Any = None) -> Capability | None:
    """build_pack 调:type_key="workspace_scene" 的 factory。

    value 是 ``AgentResource.value``(经 ``_normalize_value`` 规范化后的 dict
    或原始 string)。还原 ``WorkspaceSceneCapability``。返回 None 表示无法
    解析(被 build_pack 跳过,不阻塞其它资源)。
    """
    try:
        return WorkspaceSceneCapability.from_config(value, system_app=system_app)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"workspace_scene factory: failed to build from value {value!r}: {e}; skipping"
        )
        return None
