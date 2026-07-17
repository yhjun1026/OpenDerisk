"""PlaybookCapability — playbook 自管理资源能力(RFC-006 SSR Task 4)。

镜像 Task 3(``workspace_scene``)的成熟模式:把既有 ``PlaybookResource.declare``
(纯函数,产 SYSTEM + TOOLS Contribution)包成自管理 ``Capability`` 对象,供
``CapabilityFactoryRegistry`` 在构造期(``agent_chat.build_agent_by_gpts``)从
配置态 ``AgentResource(type="playbook")`` 重建。Agent 持有稳定 ``Capability`` 对象
,而非每轮临时翻转 config。

设计取舍(对齐 ``WorkspaceSceneCapability`` / ``Capability`` ABC 约定):
- **继承** ``derisk.core.interface.resource.capability.Capability``(ABC,需实现
  declare/prepare/execute/release)。本能力的工具走 Route A builtin(剧本内置工具
  ``get_playbook_info`` 等由 ``build_playbook_tools`` 装配进 react_master),故
  ``execute`` 留占位 NotImplementedError;真实 live state 无(services 由
  system_app.resolve),``prepare``/``release`` no-op。
- **declare 委托** ``PlaybookResource.declare(config)``(复用既有纯函数,保持
  SYSTEM 框架 + TOOLS 槽 Contribution)。**不重实现** declare。
- **requires 空列表**:不依赖共享底座(如 sandbox),与 workspace_scene 一致。
- **value 规范化** 在 factory 内自管:``CapabilityFactoryRegistry._normalize_value``
  的通用回退对 JSON string 形 value 会包成 ``{"db_name": <raw>, "value": <raw>}``
  (playbook 未在 ResourceManager 注册 parameter_cls,故走回退)。factory 需兼容三种
  入参:dict / JSON string / ``{"value": <json_str>, ...}`` 信封。

序列化策略(关键取舍,见 brief):
- **to_agent_resource 序列化完整 PlaybookConfig**(playbook_id / playbook_name /
  text_content / skills / resources / deliverables / distill)进 ``AgentResource.value``。
  factory 反序列化时**零 I/O**(无需 DB refetch)。理由:
  (1) Task 5(assembler)本来就用 ``PlaybookConfig.from_playbook_response``
      预载入完整 config 后再调 ``to_agent_resource``,config 已在内存;
  (2) 完整序列化使 factory 无状态、可缓存、可跨进程(playbook_id+name 的 refetch 路径
      需 factory 持有 system_app+DB,破坏"从 config 直接还原"的对等);
  (3) PlaybookConfig 字段全是 JSON-native(dict/list/str/int),序列化路径简单,
      无复杂引用;体积可控(declaration DSL 本就是 JSON)。
  **不在 factory 内做 DB refetch**(对齐 brief 推荐的清洁选项):refetch 责任归于
  assembler(Task 5)在 ``to_agent_resource`` 之前用 ``from_playbook_response`` 预载入。
  若 value 仅含 playbook_id(降级/历史路径),factory 重建一个**最小 config**(空
  declaration)——``declare`` 仍可产出 SYSTEM(剧本书)+ TOOLS(内置工具)Contribution,
  子资源槽缺;assembler 正常路径不会触发此降级。

注册:type_key="playbook",由 ``derisk_serve.agent.capabilities.playbook`` 子包的
``register_capability_to(registry)`` 桥接(CapabilityFactoryRegistry.discover 扫
derisk_serve.agent.capabilities.* 子包)。
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

from derisk_serve.playbook.resource.playbook_resource import (
    PlaybookConfig,
    PlaybookResource,
    PlaybookTextContent,
)

logger = logging.getLogger(__name__)


class PlaybookCapability(Capability):
    """剧本自管理能力:declare 委托 PlaybookResource.declare。

    capability_id="playbook";executor_id 同。无 live state(services
    由 system_app.resolve,非本对象持有),prepare/release 为 no-op。
    """

    capability_id = "playbook"

    def __init__(
        self, config: PlaybookConfig, system_app: Any = None
    ) -> None:
        self._config: PlaybookConfig = config
        self._system_app = system_app
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(
        cls, value: Any, system_app: Any = None
    ) -> "PlaybookCapability":
        """从 AgentResource.value 还原 Capability。

        value 兼容三种形态:
        - dict:直接取字段(playbook_id/playbook_name/text_content/...)
        - JSON string:先 json.loads
        - ``{"db_name": <json_str>, "value": <json_str>, ...}`` 信封
          (_normalize_value 通用回退会把 JSON string 包成此形态):从 "value"
          或 "db_name" 取出 JSON string 再解析

        序列化策略:value 含完整 config(零 I/O)：直接反序列化 text_content/
        skills/resources/deliverables/distill。不在 factory 内做 DB refetch
        (refetch 责任归于 assembler 预载入)。value 仅含 playbook_id 时重建
        最小 config(空 declaration),declare 仍产 SYSTEM + TOOLS Contribution。
        """
        data = _coerce_playbook_value(value)
        if data is None:
            raise ValueError(
                f"playbook factory: cannot coerce value to playbook config: {value!r}"
            )
        config = _build_playbook_config(data)
        if config is None:
            raise ValueError(
                f"playbook factory: missing playbook_id in value: {value!r}"
            )
        return cls(config, system_app=system_app)

    # ----------------------------- 输入投影(委托纯函数) ------------------- #
    def declare(self, config: PlaybookConfig | None = None) -> List[Contribution]:
        return PlaybookResource.declare(config or self._config)

    def requires(self, config: Any = None) -> List[str]:
        # 不依赖共享底座(sandbox),无 live executor 依赖。
        return []

    # ----------------------------- 生命周期(无 live state,no-op) -------- #
    async def prepare(self) -> None:
        # 服务由 system_app.resolve,本对象不持有连接;幂等置 READY。
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # 剧本内置工具走 Route A builtin(react_master 装配),本 execute 未接。
        raise NotImplementedError(
            "PlaybookCapability.execute 未接 —— 剧本内置工具暂走 Route A builtin"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED


def _coerce_playbook_value(value: Any) -> dict | None:
    """把 AgentResource.value 规范化为 dict(含 playbook_id 等)。

    处理顺序(对齐 scene_capability._coerce_scene_value):
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
        # 直接是 payload dict(playbook_id 等字段在顶层)
        if any(
            k in value
            for k in ("playbook_id", "playbook_name", "text_content", "skills")
        ):
            return value
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"playbook factory: JSON decode failed: {e}")
            return None
        return parsed if isinstance(parsed, dict) else None
    if hasattr(value, "to_dict"):
        try:
            d = value.to_dict()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"playbook factory: to_dict() failed: {e}")
            return None
        return d if isinstance(d, dict) else None
    return None


def _build_playbook_config(data: dict) -> PlaybookConfig | None:
    """从规范化 dict 重建 PlaybookConfig(零 I/O)。

    data 含完整 config(text_content/skills/...)时反序列化全部字段;
    data 仅含 playbook_id(降级)时重建最小 config(空 declaration)。
    返回 None 表示无法构造(缺 playbook_id 或 playbook_id 不可转 int)。

    **不在 factory 内做 DB refetch**:refetch 责任归于 assembler(Task 5)在
    调用 ``to_agent_resource`` 前用 ``PlaybookConfig.from_playbook_response``
    预载入完整 config。factory 保持无状态、可缓存、可跨进程。
    """
    playbook_id = data.get("playbook_id")
    if playbook_id is None:
        return None
    try:
        playbook_id = int(playbook_id)
    except (TypeError, ValueError):
        return None

    text_content = PlaybookTextContent.from_dict(data.get("text_content"))
    skills = data.get("skills") or []
    resources = data.get("resources") or []
    deliverables = data.get("deliverables") or []
    distill = data.get("distill") or {}

    return PlaybookConfig(
        playbook_id=playbook_id,
        playbook_name=data.get("playbook_name", ""),
        text_content=text_content,
        skills=list(skills) if isinstance(skills, list) else [],
        resources=list(resources) if isinstance(resources, list) else [],
        deliverables=list(deliverables) if isinstance(deliverables, list) else [],
        distill=dict(distill) if isinstance(distill, dict) else {},
    )


def playbook_factory(value: Any, system_app: Any = None) -> Capability | None:
    """build_pack 调:type_key="playbook" 的 factory。

    value 是 ``AgentResource.value``(经 ``_normalize_value`` 规范化后的 dict
    或原始 string)。还原 ``PlaybookCapability``。返回 None 表示无法
    解析(被 build_pack 跳过,不阻塞其它资源)。
    """
    try:
        return PlaybookCapability.from_config(value, system_app=system_app)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"playbook factory: failed to build from value {value!r}: {e}; skipping"
        )
        return None
