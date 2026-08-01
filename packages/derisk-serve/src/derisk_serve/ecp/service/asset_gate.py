"""ECP 托管资产门禁(上下文保留 + 工具面硬门禁)。

ECP workspace 托管的资产(asset_ref kind=db)若同时被直接绑定到 Agent,
会出现双入口:ECP 语义层(search_semantics/execute_metric_query)与原始资源
直连工具(execute_sql)。实测(对话 12f7b6bc):ECP 目录+行为约定全部注入,
模型仍 execute_sql×9、ECP 工具×0——prompt 软约束打不过工具可用性。

设计(三层):
- 上下文层:datasource 保留注入(基础信息+schema),供 execute_raw_sql 兜底
  和 propose_semantic 提案理解物理结构;只读 schema 工具(get_table_spec/
  list_tables/search_tables)不管控。
- 声明层:``build_managed_assets_text`` 生成托管清单注入 SYSTEM,讲明哪些库
  被托管、直连已禁用、查询统一走 ECP 工具(降级使用纪律)。
- 工具面:``ecp_gate_message`` 供 ``execute_sql`` 在执行前调用——agent 绑定了
  ECP 且目标库被其 workspace 托管时硬拒绝并返回引导文案。这是"降级使用"的
  实际执行点,不依赖模型自觉。

ECP 自身执行链路(``DbBindingExecutor`` 经 ``ConnectConfigDao`` 直连)不走
``execute_sql``,不受门禁影响。全部接口 fail-open:任何异常放行,不阻塞查询。
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set

from ..config import DEFAULT_WORKSPACE_ID
from ..models.models import AssetRefDao

logger = logging.getLogger(__name__)

ASSET_KIND_DB = "db"
_STATUS_ACTIVE = "active"


def _parse_value_dict(value: Any) -> Dict[str, Any]:
    """AgentResource.value 兼容 dict / JSON string,其余返回 {}。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def managed_db_datasource_ids(workspace_ids: Set[str]) -> Set[str]:
    """ECP workspace 托管的 db 资产 ref_id(datasource_id)集合。失败返回空(fail-open)。"""
    managed: Set[str] = set()
    try:
        dao = AssetRefDao()
        for ws in workspace_ids:
            for ref in dao.list(ws, kind=ASSET_KIND_DB) or []:
                if getattr(ref, "status", _STATUS_ACTIVE) == _STATUS_ACTIVE:
                    managed.add(str(ref.ref_id))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp-asset-gate] load managed assets failed: {e}")
    return managed


def _agent_ecp_workspace_ids(agent: Any) -> Set[str]:
    """从 agent 的 capability_pack 提取绑定的 ECP workspace_id 集合。

    只查 capability_pack:旧 ResourcePack 的 ResourceManager 未注册 'ecp' type_key,
    ECP 资源只经 CapabilityPack 路径构建。capability_pack 缺失(构建失败)时返回空,
    门禁随之不生效——此时 ECP 工具也不存在,不应阻断直连 SQL(语义层入口不存在时
    门禁无意义)。
    """
    ws_ids: Set[str] = set()
    cap_pack = getattr(agent, "capability_pack", None)
    for c in getattr(cap_pack, "sub_resources", []) or []:
        if getattr(c, "capability_id", None) == "ecp":
            ws = getattr(c, "_workspace_id", None) or DEFAULT_WORKSPACE_ID
            ws_ids.add(str(ws))
    return ws_ids


def ecp_gate_message(
    agent: Any, datasource_id: Any, db_name: str = ""
) -> Optional[str]:
    """ECP 托管直连门禁:命中返回拒绝+引导文案,未命中返回 None(放行)。

    命中条件(同时满足):
    - agent 的 capability_pack 中绑定了 ECP capability(语义层入口存在)
    - 目标 datasource_id 被该 ECP workspace 托管(asset_ref kind=db, active)

    fail-open:agent/ds_id 缺失、DAO 异常等一律返回 None,不阻塞正常查询。
    """
    try:
        if agent is None or datasource_id is None:
            return None
        ws_ids = _agent_ecp_workspace_ids(agent)
        if not ws_ids:
            return None
        if str(datasource_id) not in managed_db_datasource_ids(ws_ids):
            return None
        label = f"{db_name} (id={datasource_id})" if db_name else f"id={datasource_id}"
        return (
            f"⛔ 数据源 {label} 已由 ECP 语义层托管,直连 SQL 查询已禁用。\n"
            "请改用 ECP 工具:\n"
            "1. search_semantics / get_semantic_object 查找已确认指标\n"
            "2. execute_metric_query 执行指标查询(✅ 可信口径)\n"
            "3. 确无对应指标时,用 execute_raw_sql 执行原生 SQL,"
            "并向用户声明结果为 ⚠️ 未验证口径\n"
            "表结构仍可用 get_table_spec / list_tables 查阅(只读 schema 不受限)。"
        )
    except Exception:  # noqa: BLE001
        return None


def managed_space_slugs(workspace_ids: Set[str]) -> Set[str]:
    """ECP workspace 托管的空间资产 slug 集合(kind=space/document, active)。

    fail-open:异常返回空。
    """
    managed: Set[str] = set()
    try:
        dao = AssetRefDao()
        for ws in workspace_ids:
            for kind in ("space", "document"):
                for ref in dao.list(ws, kind=kind) or []:
                    if getattr(ref, "status", _STATUS_ACTIVE) == _STATUS_ACTIVE:
                        managed.add(str(ref.ref_id))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp-asset-gate] load managed spaces failed: {e}")
    return managed


def ecp_knowledge_gate_message(
    agent: Any, knowledge_ids: Optional[List[str]] = None
) -> Optional[str]:
    """ECP 托管空间知识检索门禁(P0 文档降级):命中返回拒绝+引导文案。

    命中条件(同时满足):
    - agent 的 capability_pack 中绑定了 ECP capability
    - 该 ECP workspace 托管了空间资产(kind=space/document, active)
    - 调用未显式指定 knowledge_ids(泛检索必然命中托管空间;
      显式指定视为有意目标非托管内容,P0 放行——id→space 映射 P1 再细化)

    fail-open:任何异常返回 None,不阻塞检索。
    """
    try:
        if agent is None or knowledge_ids:
            return None
        ws_ids = _agent_ecp_workspace_ids(agent)
        if not ws_ids:
            return None
        if not managed_space_slugs(ws_ids):
            return None
        return (
            "⛔ 该知识空间已由 ECP 语义层托管,泛检索已禁用。\n"
            "请改用 ECP 文档工具:\n"
            "1. 事实型问题(制度/条款/定义):search_semantics 找条目 → "
            "query_canon 带引用回答(✅ 可信口径)\n"
            "2. 目录未覆盖:explore_docs 探索检索(⚠️ 须声明未验证口径,"
            "发现的可信口径用 propose_semantic 提案沉淀)"
        )
    except Exception:  # noqa: BLE001
        return None


def _db_name_for(ref_id: str) -> Optional[str]:
    """best-effort 取数据源名(供托管清单展示);失败返回 None。"""
    try:
        from derisk_serve.datasource.manages.connect_config_db import (
            ConnectConfigDao,
        )

        cfg = ConnectConfigDao().get_one({"id": int(ref_id)})
        return getattr(cfg, "db_name", None) if cfg else None
    except Exception:  # noqa: BLE001
        return None


def build_managed_assets_text(workspace_id: str) -> str:
    """托管资产清单文本(供 ECPCapability 注入 SYSTEM 槽)。

    讲明哪些数据源被托管、降级使用纪律:schema 只读工具开放,数据查询直连
    已禁用(execute_sql 会被拒绝),统一走 ECP 工具。无托管 db 资产 / 失败时
    返回空串(不制造噪音)。
    """
    try:
        refs = [
            r
            for r in AssetRefDao().list(workspace_id, kind=ASSET_KIND_DB) or []
            if getattr(r, "status", _STATUS_ACTIVE) == _STATUS_ACTIVE
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp-asset-gate] build manifest failed: {e}")
        return ""
    if not refs:
        return ""
    lines = ["【ECP 托管资产】(降级使用)"]
    for r in refs:
        name = _db_name_for(r.ref_id)
        label = f"{name} (id={r.ref_id})" if name else f"id={r.ref_id}"
        lines.append(
            f"  数据源 {label}:已纳入语义层管理,直连查询(execute_sql)已禁用。"
        )
    lines.append(
        "  表结构可用 get_table_spec / list_tables 查阅;"
        "数据查询统一走 ECP 工具(execute_metric_query 优先,"
        "execute_raw_sql 兜底须声明 ⚠️ 未验证口径)。"
    )
    return "\n".join(lines)
