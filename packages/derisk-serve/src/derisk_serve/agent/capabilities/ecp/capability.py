"""ECPCapability -- 企业语义层自管理资源能力(ECP P1「通电」)。

ECP 执行链路(DbBindingExecutor 门禁 / resolver 缓存 / 6 工具)已就绪并 8/8 验证,
本 capability 是把它「通电」到 Agent 的桥梁:

- ``prepare``:预载已确认目录文本(``build_catalog_text``)到 ``self``(declare 必须纯)
- ``declare``:目录摘要 + 行为约定 -> SYSTEM 槽;6 个 ECP 工具(workspace_id 闭包绑定)
  -> TOOLS 槽
- 工具走 Route A builtin(react_master 装配 TOOLS 槽),``execute`` 留 NotImplementedError,
  与 DBCapability/WorkspaceSceneCapability 一致

照 ``WorkspaceSceneCapability``/``DBCapability`` 模式。``capability_id="ecp"``。
Agent 经 ``AgentResource(type="ecp", value={"workspace_id": ...})`` 绑定。
"""

from __future__ import annotations

import logging
from typing import Any, List

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

from derisk_serve.ecp.config import DEFAULT_WORKSPACE_ID

logger = logging.getLogger(__name__)


class ECPCapability(Capability):
    """企业语义层能力:declare 注入已确认目录 + 行为约定 + 6 工具。

    capability_id="ecp";executor_id 同。无 live state(目录文本 prepare 预载),
    prepare 载目录,release no-op。工具走 Route A builtin(react_master 装配)。
    """

    capability_id = "ecp"

    def __init__(
        self, workspace_id: str = DEFAULT_WORKSPACE_ID, system_app: Any = None
    ) -> None:
        self._workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
        self._system_app = system_app
        self._catalog_text: str = ""
        self._managed_assets_text: str = ""
        self._has_managed_db: bool = False
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: Any, system_app: Any = None) -> "ECPCapability":
        """从 ``AgentResource.value`` 构造。value 兼容 dict / JSON string / 裸 string。

        workspace_id 缺省 ``DEFAULT_WORKSPACE_ID``。scene 的 int workspace_id 由
        绑定方 ``str()`` 转换后传入。无 I/O。
        """
        import json

        ws: Any = DEFAULT_WORKSPACE_ID
        if isinstance(value, dict):
            ws = (
                value.get("workspace_id")
                or value.get("workspace")
                or DEFAULT_WORKSPACE_ID
            )
        elif isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    ws = (
                        parsed.get("workspace_id")
                        or parsed.get("workspace")
                        or ws
                    )
                else:
                    ws = parsed
            except (json.JSONDecodeError, TypeError):
                ws = value
        return cls(workspace_id=str(ws), system_app=system_app)

    @property
    def executor_id(self) -> str:
        return self.capability_id

    def requires(self, config: Any = None) -> List[str]:
        # 不依赖共享底座(如 sandbox),与 MemoryCapability/WorkspaceSceneCapability 一致。
        return []

    async def prepare(self) -> None:
        """预载已确认目录文本(供 declare 注入)。I/O 步。

        declare 须纯函数,故目录查询在此完成存 ``self._catalog_text``。目录为空时置空
        (declare 仅注入行为约定,不制造噪音)。失败降级为空目录,不阻塞 Agent 启动。

        同载托管资产清单(asset_gate.build_managed_assets_text):直接绑定被门禁
        移除后,模型需从清单得知 DB 仍可达且统一走 ECP 工具。清单失败独立降级,
        不影响目录。
        """
        try:
            from derisk_serve.ecp.service.catalog import build_catalog_text

            self._catalog_text = build_catalog_text(self._workspace_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[ecp-capability] load catalog for {self._workspace_id} failed: {e}"
            )
            self._catalog_text = ""
        try:
            from derisk_serve.ecp.service.asset_gate import (
                build_managed_assets_text,
                managed_db_datasource_ids,
            )

            self._managed_assets_text = build_managed_assets_text(self._workspace_id)
            self._has_managed_db = bool(
                managed_db_datasource_ids({self._workspace_id})
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[ecp-capability] load managed assets for {self._workspace_id} failed: {e}"
            )
            self._managed_assets_text = ""
            self._has_managed_db = False
        self._status = ExecutorStatus.READY

    def declare(self, config: Any = None) -> List[Contribution]:
        """注入目录摘要 + 行为约定(SYSTEM)+ 6 工具(TOOLS)。

        纯函数:目录文本已由 prepare 预载;工具对象构造无 I/O。
        """
        from derisk_serve.ecp.service.catalog import BEHAVIOR_GUIDE
        from derisk_serve.ecp.tools.ecp_tools import build_ecp_agent_tools

        contribs: List[Contribution] = []

        # SYSTEM: 目录摘要(若有)+ 托管资产清单(若有)+ 行为约定
        system_parts = []
        if self._catalog_text:
            system_parts.append(self._catalog_text)
        if self._managed_assets_text:
            system_parts.append(self._managed_assets_text)
        system_parts.append(BEHAVIOR_GUIDE)
        contribs.append(
            Contribution(
                capability_id=f"{self.capability_id}:system",
                slot=Slot.SYSTEM,
                content="\n\n".join(system_parts),
                lifetime=Lifetime.SESSION,
                cache_scope=CacheScope.USER,
                order=30,
            )
        )

        # TOOLS: 6 个 ECP 工具(workspace_id 闭包绑定,agent 无需传 workspace_id)
        for tool in build_ecp_agent_tools(self._workspace_id):
            contribs.append(
                Contribution(
                    capability_id=f"{self.capability_id}:tool:{tool.name}",
                    slot=Slot.TOOLS,
                    content=tool,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.NONE,
                    order=30,
                )
            )

        # TOOLS: 托管 db 资产的降级连带注入——只读 schema 工具(get_table_spec/
        # list_tables)。ECP 托管的资源以降级形态出现:结构可查(供 execute_raw_sql
        # 兜底与提案理解物理表),数据查询只走 ECP 工具;execute_sql 不连带,
        # 若经直接绑定注入则由 asset_gate 硬门禁拦截。只绑 ECP 也能读 schema。
        if self._has_managed_db:
            for tool in _load_db_schema_tools():
                contribs.append(
                    Contribution(
                        capability_id=f"{self.capability_id}:tool:{tool.name}",
                        slot=Slot.TOOLS,
                        content=tool,
                        lifetime=Lifetime.CONFIG_STATIC,
                        cache_scope=CacheScope.NONE,
                        order=31,
                    )
                )
        return contribs

    async def execute(self, call: ExecutorCall) -> Any:
        # ECP 工具走 Route A builtin(react_master 装配 TOOLS 槽),不走 Route B。
        raise NotImplementedError(
            "ECPCapability.execute 不走 Route B -- ECP 工具走 builtin Route A"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED


def _load_db_schema_tools() -> List[Any]:
    """取只读 schema 工具(get_table_spec/list_tables)供托管资产降级连带注入。

    复用 tool_registry 中已注册的 DB 工具(与 _inject_database_tools 同源),
    执行期经 ConnectConfigDao/local_db_manager 解析连接,不依赖 agent 侧绑定
    DBCapability。注册表缺失/未导入时返回空(不阻塞 declare)。
    """
    from derisk.agent.tools.registry import tool_registry

    try:
        import derisk_serve.agent.capabilities.db.tools._db_tools_impl  # noqa: F401
    except ImportError:
        return []
    tools: List[Any] = []
    for name in ("get_table_spec", "list_tables"):
        t = tool_registry.get(name)
        if t is not None:
            tools.append(t)
    return tools


def ecp_factory(value: Any, system_app: Any = None) -> Capability | None:
    """build_pack 调:type_key="ecp" 的 factory。

    value 是 ``AgentResource.value``(经 ``_normalize_value`` 规范化后的 dict 或原始
    string)。还原 ``ECPCapability``。返回 None 表示无法解析(被 build_pack 跳过,
    不阻塞其它资源)。
    """
    try:
        return ECPCapability.from_config(value, system_app=system_app)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"ecp factory: failed to build from value {value!r}: {e}; skipping"
        )
        return None
