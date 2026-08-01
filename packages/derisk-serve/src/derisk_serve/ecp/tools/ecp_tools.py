"""ECP agent tools (tool surface, ECP v1.2).

The protocol is enforced by the TOOL SURFACE, not by prompts:
- `execute_metric_query` is the ONLY path to ✅ verified numbers (the gate
  lives in service/executor.py, agent-invisible and unbypassable)
- `execute_raw_sql` is the sanctioned fallback — always ⚠️ inferred, always
  op-logged as a miss (lint clustering feedstock)
- trust markers are hardcoded in tool return values, never agent-declared
- user disambiguation reuses derisk-core's builtin AskUserTool

Tools are stateless: workspace_id is an argument (default 'default').
"""

import json
import logging
from typing import Any, Dict, List, Optional

from derisk.agent.tools.decorators import tool
from derisk.agent.tools.base import ToolCategory, ToolRiskLevel
from derisk.agent.resource.tool.base import FunctionTool
from derisk.vis import Vis

from ..config import DEFAULT_WORKSPACE_ID
from ..models.models import OpLogDao, SemanticObjectDao

logger = logging.getLogger(__name__)


def _ws(workspace_id: Optional[str]) -> str:
    return workspace_id or DEFAULT_WORKSPACE_ID


@tool(
    "search_semantics",
    description=(
        "Search CONFIRMED enterprise semantic objects (metrics/entities/"
        "dimensions/relations) by keyword. Always search here first when "
        "answering business-number questions; only use execute_raw_sql if "
        "nothing matches."
    ),
    args={
        "query": {"type": "string", "description": "关键词（名称/别名/id）"},
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.SAFE,
)
async def search_semantics(query: str, workspace_id: Optional[str] = None, **kwargs) -> str:
    ws = _ws(workspace_id)
    entries = SemanticObjectDao().list_catalog(ws, keyword=query)
    results = [
        {
            "id": e.id,
            "type": e.obj_type,
            "name": e.name,
            "aliases": e.aliases,
            "one_line": e.one_line,
        }
        for e in entries
    ]
    # vis 输出:右面板独立渲染(类型徽章+结果卡片);失败回退裸 JSON
    try:
        vis = Vis.of("d-ecp-search")
        if vis:
            return vis.sync_display(
                query=query, workspace_id=ws, total=len(results), results=results
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp] search_semantics vis display failed: {e}")
    return json.dumps(results, ensure_ascii=False)


@tool(
    "get_semantic_object",
    description=(
        "Get the full confirmed payload of a semantic object: caliber "
        "definition, binding, dimension values, grain, version."
    ),
    args={
        "object_id": {"type": "string", "description": "对象 id，如 mtr.net_sales"},
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.SAFE,
)
async def get_semantic_object(object_id: str, workspace_id: Optional[str] = None, **kwargs) -> str:
    vo = SemanticObjectDao().get_confirmed(object_id, _ws(workspace_id))
    if not vo:
        return json.dumps(
            {"error": f"对象 {object_id} 不存在或未确认"}, ensure_ascii=False
        )
    # vis 输出:右面板独立渲染(类型徽章+关键字段+payload折叠);失败回退裸 JSON
    try:
        vis = Vis.of("d-ecp-object")
        if vis:
            return vis.sync_display(
                id=vo.id,
                version=vo.version,
                type=vo.obj_type,
                status=vo.status,
                payload=vo.payload or {},
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp] get_semantic_object vis display failed: {e}")
    return json.dumps(
        {
            "id": vo.id,
            "version": vo.version,
            "type": vo.obj_type,
            "status": vo.status,
            "payload": vo.payload,
        },
        ensure_ascii=False,
    )


@tool(
    "execute_metric_query",
    description=(
        "THE gated ✅ path for business numbers. Execute a CONFIRMED metric "
        "with dimension filters/group-by/time range. All IDs must come from "
        "the confirmed catalog (search_semantics/get_semantic_object). "
        "Returns trust=verified with full lineage."
    ),
    args={
        "metric_id": {"type": "string", "description": "已确认指标 id"},
        "group_by": {
            "type": "array",
            "items": {"type": "string"},
            "description": "分组维度 id 列表",
            "required": False,
        },
        "filters": {
            "type": "array",
            "items": {"type": "object"},
            "description": "筛选：[{dim_id, values: [label], mode: include|exclude}]",
            "required": False,
        },
        "time": {
            "type": "object",
            "description": "时间：{range: 'YYYY-MM-DD~YYYY-MM-DD', column?}",
            "required": False,
        },
        "question": {
            "type": "string",
            "description": "原始用户问题（用于解析缓存回填）",
            "required": False,
        },
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.DATABASE,
    risk_level=ToolRiskLevel.LOW,
)
async def execute_metric_query_tool(
    metric_id: str,
    group_by: Optional[List[str]] = None,
    filters: Optional[List[Dict[str, Any]]] = None,
    time: Optional[Dict[str, Any]] = None,
    question: Optional[str] = None,
    workspace_id: Optional[str] = None,
    **kwargs,
) -> str:
    from ..service.executor import GateError, execute_metric_query
    from ..service.resolver import backfill

    ws = _ws(workspace_id)

    # 飞轮回忆路径(读):question 命中 resolution cache 且 metric 一致 →
    # 直接重放冻结参数(零漂移,标注 cache_hit);缓存过期(GateError)落回正常路径。
    if question:
        from ..service.resolver import lookup, replay

        cached = lookup(question, ws)
        if (
            cached
            and cached.get("tool") == "execute_metric_query"
            and (cached.get("params") or {}).get("metric_id") == metric_id
        ):
            try:
                result = replay(cached)
                try:
                    vis = Vis.of("d-ecp-metric")
                    if vis:
                        return vis.sync_display(
                            trust=result.get("trust", "verified"),
                            metric_id=metric_id,
                            columns=result.get("columns"),
                            rows=result.get("rows"),
                            row_count=result.get("row_count"),
                            sql=result.get("sql"),
                            lineage=result.get("lineage"),
                            cache_hit=True,
                        )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[ecp] recall vis display failed: {e}")
                return json.dumps(result, ensure_ascii=False, default=str)
            except GateError as e:
                logger.info(
                    f"[ecp] recall replay rejected ({e.code}: {e}), "
                    f"fall through to live execution"
                )

    try:
        result = execute_metric_query(
            metric_id=metric_id,
            workspace_id=ws,
            group_by=group_by,
            filters=filters,
            time_range=time,
        )
    except GateError as e:
        # 门禁拒绝也走 vis(trust=none 错误态渲染),失败回退裸 JSON
        try:
            vis = Vis.of("d-ecp-metric")
            if vis:
                return vis.sync_display(
                    trust="none", metric_id=metric_id, error=str(e), code=e.code
                )
        except Exception:  # noqa: BLE001
            pass
        return json.dumps(
            {"error": str(e), "code": e.code, "trust": "none"}, ensure_ascii=False
        )
    # Recall flywheel: successful, uncorrected calls backfill the cache.
    if question:
        backfill(
            question,
            ws,
            {
                "tool": "execute_metric_query",
                "params": {
                    "metric_id": metric_id,
                    "workspace_id": ws,
                    "group_by": group_by,
                    "filters": filters,
                    "time": time,
                },
            },
        )
    # vis 输出:trust 徽章 + 结果表 + 血缘页脚;失败回退裸 JSON
    try:
        vis = Vis.of("d-ecp-metric")
        if vis:
            return vis.sync_display(
                trust=result.get("trust", "verified"),
                metric_id=metric_id,
                columns=result.get("columns"),
                rows=result.get("rows"),
                row_count=result.get("row_count"),
                sql=result.get("sql"),
                lineage=result.get("lineage"),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp] execute_metric_query vis display failed: {e}")
    return json.dumps(result, ensure_ascii=False, default=str)


@tool(
    "execute_raw_sql",
    description=(
        "Exploration path (⚠️ UNVERIFIED but encouraged). Use freely for "
        "open-ended analysis, concepts not yet in the semantic catalog, "
        "distributions/correlations/custom calibers. This is how the "
        "semantic layer learns: your reasoning feeds miss clustering. "
        "You MUST tell the user results are unverified caliber, and "
        "propose_semantic valuable reusable calibers you discovered."
    ),
    args={
        "datasource_id": {"type": "integer", "description": "数据源 id"},
        "sql": {"type": "string", "description": "SELECT 语句（只读）"},
        "reasoning": {
            "type": "string",
            "description": (
                "探索目的 + 发现了什么目录没有的概念（飞轮原料，会被聚类学习）。"
                "示例: '分析各门店温度与销售额相关性；目录缺少温度-销售关联维度'"
            ),
        },
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.DATABASE,
    risk_level=ToolRiskLevel.LOW,
)
async def execute_raw_sql(
    datasource_id: int,
    sql: str,
    reasoning: str,
    workspace_id: Optional[str] = None,
    **kwargs,
) -> str:
    ws = _ws(workspace_id)
    # 只读校验:先剥离注释(-- 行注释 / /* */ 块注释)再取首个关键字,
    # 否则带注释头的合法 SELECT 会被误判为写操作
    import re as _re

    cleaned = _re.sub(r"--.*$", "", sql, flags=_re.MULTILINE)
    cleaned = _re.sub(r"/\*.*?\*/", "", cleaned, flags=_re.DOTALL)
    stripped = cleaned.strip().lstrip("(").strip()
    first = stripped.split(None, 1)[0].upper() if stripped else ""
    if first not in ("SELECT", "WITH", "SHOW", "DESC", "DESCRIBE", "EXPLAIN"):
        return json.dumps(
            {"error": "只允许只读查询（SELECT/WITH/SHOW/DESC/EXPLAIN）", "trust": "none"},
            ensure_ascii=False,
        )
    # The miss is op-logged — lint clustering turns high-frequency misses
    # into new object/alias/dimension proposals (recall flywheel).
    OpLogDao().append(
        "fallback", ws,
        {"datasource_id": datasource_id, "sql": sql[:2000], "reasoning": reasoning},
    )
    # 飞轮全自动:确保该工作空间的每日自动学习任务已注册(幂等,失败静默)
    try:
        from ..service.auto_learn import ensure_auto_learn_cron

        await ensure_auto_learn_cron(ws)
    except Exception:  # noqa: BLE001
        pass
    try:
        from derisk_serve.datasource.manages.connect_config_db import (
            ConnectConfigDao,
        )
        from derisk._private.config import Config

        config = ConnectConfigDao().get_one({"id": datasource_id})
        db_name = getattr(config, "db_name", None)
        if not db_name:
            return json.dumps(
                {"error": f"数据源 {datasource_id} 不存在", "trust": "none"},
                ensure_ascii=False,
            )
        connector = Config().local_db_manager.get_connector(db_name)
        raw = connector.run(sql)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e), "trust": "none"}, ensure_ascii=False)
    columns, rows = [], []
    if raw:
        columns = list(raw[0])
        # Convert to list of lists (consistent with execute_sql format)
        rows = [list(r) for r in raw[1:]]

    # Use d-sql-query VIS component for rendering (same as execute_sql)
    result_data = {
        "sql": sql,
        "db_name": db_name,
        "db_type": getattr(connector, 'db_type', 'unknown'),
        "dialect": getattr(connector, 'dialect', getattr(connector, 'db_type', 'unknown')),
        "columns": columns,
        "rows": rows,
        "total_rows": len(rows),
        "page": 1,
        "total_pages": 1,
        "page_size": len(rows),
        "has_more": False,
        # ECP-specific fields
        "trust": "inferred",
        "warning": "⚠️ 未验证口径：此结果未经语义层确认",
    }

    try:
        vis = Vis.of("d-sql-query")
        return vis.sync_display(**result_data)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[execute_raw_sql] Failed to render d-sql-query: {e}")
        # Fallback to JSON format
        return json.dumps(result_data, ensure_ascii=False, default=str)


@tool(
    "get_miss_report",
    description=(
        "Get clustered UNCOVERED questions (execute_raw_sql fallback log), "
        "grouped by normalized SQL pattern and ranked by frequency. Use this "
        "to learn what users repeatedly need but the catalog cannot answer — "
        "then propose_semantic for the high-frequency, genuinely-missing "
        "concepts (skip anything the catalog or inbox already covers)."
    ),
    args={
        "min_count": {
            "type": "integer",
            "description": "只返回出现次数 >= 此值的聚类，默认 2",
            "required": False,
        },
        "limit": {
            "type": "integer",
            "description": "最多返回聚类数，默认 20",
            "required": False,
        },
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.SAFE,
)
async def get_miss_report(
    min_count: int = 2,
    limit: int = 20,
    workspace_id: Optional[str] = None,
    **kwargs,
) -> str:
    from ..service.service import cluster_fallbacks

    ws = _ws(workspace_id)
    entries = OpLogDao().list(ws, op="fallback", page=1, page_size=500)
    clusters = [
        c for c in cluster_fallbacks(entries) if c["count"] >= max(1, min_count)
    ][:limit]
    return json.dumps(
        {
            "workspace_id": ws,
            "total_fallbacks": len(entries),
            "clusters": clusters,
            "hint": "对照已确认目录与收件箱,只为真正未覆盖且高频的概念用 "
            "propose_semantic 提案;已有概念不要重复提案",
        },
        ensure_ascii=False,
        default=str,
    )


@tool(
    "query_canon",
    description=(
        "THE gated ✅ path for factual questions about managed documents "
        "(policies/definitions/rules). Execute CONFIRMED canon entries "
        "(claim/terminology/policy from search_semantics) and get answers "
        "with citations. Returns trust=verified with full lineage."
    ),
    args={
        "question": {"type": "string", "description": "原始事实型问题"},
        "object_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "已确认条目 id 列表(须来自 search_semantics/get_semantic_object)",
        },
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.SAFE,
)
async def query_canon(
    question: str,
    object_ids: List[str],
    workspace_id: Optional[str] = None,
    **kwargs,
) -> str:
    from ..service.executor import GateError, execute_claim_query

    ws = _ws(workspace_id)
    try:
        result = await execute_claim_query(object_ids, ws)
    except GateError as e:
        return json.dumps(
            {"error": str(e), "code": e.code, "trust": "none"}, ensure_ascii=False
        )
    result["question"] = question
    return json.dumps(result, ensure_ascii=False, default=str)


@tool(
    "explore_docs",
    description=(
        "Document exploration path (⚠️ UNVERIFIED but encouraged). Free "
        "search over ECP-managed knowledge spaces for questions the canon "
        "cannot answer yet. Results are always trust=inferred; the miss is "
        "logged for canon learning. Tell the user the caliber is unverified, "
        "and propose_semantic valuable claims/terms you discover (with "
        "source_quote and anchor)."
    ),
    args={
        "question": {"type": "string", "description": "探索问题"},
        "space": {
            "type": "string",
            "description": "限定知识空间 slug;不填则检索本工作空间全部托管空间",
            "required": False,
        },
        "limit": {
            "type": "integer",
            "description": "返回条数,默认 5",
            "required": False,
        },
        "reasoning": {
            "type": "string",
            "description": "探索目的 + 发现了什么目录没有的概念(飞轮原料)",
        },
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
)
async def explore_docs(
    question: str,
    reasoning: str,
    space: Optional[str] = None,
    limit: int = 5,
    workspace_id: Optional[str] = None,
    **kwargs,
) -> str:
    from ..models.models import AssetRefDao

    ws = _ws(workspace_id)

    # 目标空间:指定 space,或本 ECP workspace 全部登记空间资产(active)
    if space:
        spaces = [space]
    else:
        try:
            spaces = [
                a.ref_id
                for a in AssetRefDao().list(ws, kind="space") or []
                if getattr(a, "status", "active") == "active"
            ]
        except Exception:  # noqa: BLE001
            spaces = []
    if not spaces:
        return json.dumps(
            {"error": f"工作空间 {ws} 无托管知识空间", "trust": "none"},
            ensure_ascii=False,
        )

    # op_log 记 miss(doc 形态,飞轮原料) + 确保自动学习任务存在
    OpLogDao().append(
        "fallback",
        ws,
        {
            "kind": "doc",
            "question": question,
            "spaces": spaces,
            "reasoning": reasoning,
        },
    )
    try:
        from ..service.auto_learn import ensure_auto_learn_cron

        await ensure_auto_learn_cron(ws)
    except Exception:  # noqa: BLE001
        pass

    # 检索各空间 verbat(L0 原文块)
    hits: List[Dict[str, Any]] = []
    try:
        from derisk._private.config import Config

        system_app = Config().SYSTEM_APP
        from derisk_serve.knowledge.config import (
            SERVE_SERVICE_COMPONENT_NAME as KNOWLEDGE_SERVICE,
        )
        from derisk_serve.knowledge.service.service import (
            Service as KnowledgeService,
        )

        ks = system_app.get_component(KNOWLEDGE_SERVICE, KnowledgeService)
        for sp in spaces:
            try:
                vault = await ks.get_vault(sp)
                for h in await vault.verbat_search(question, limit=limit, mode="hybrid"):
                    hits.append(
                        {
                            "space": sp,
                            "verbat_id": h.verbat_id,
                            "score": round(getattr(h, "score", 0) or 0, 3),
                            "snippet": getattr(h, "snippet", ""),
                            "source_file": getattr(h, "source_file", ""),
                        }
                    )
            except Exception as e:  # noqa: BLE001
                logger.info(f"[explore_docs] search space {sp} failed: {e}")
    except Exception as e:  # noqa: BLE001
        return json.dumps(
            {"error": f"知识服务不可用: {e}", "trust": "none"}, ensure_ascii=False
        )

    hits = sorted(hits, key=lambda x: -x["score"])[:limit]
    return json.dumps(
        {
            "hits": hits,
            "spaces_searched": spaces,
            "trust": "inferred",
            "warning": "⚠️ 未验证口径:结果来自临时检索,未经语义层确认",
        },
        ensure_ascii=False,
        default=str,
    )


@tool(
    "get_ecp_catalog",
    description=(
        "Get the FULL confirmed semantic catalog (compact text) plus the "
        "behavior rules for answering business-number questions. Call this "
        "first when entering an ECP-enabled conversation."
    ),
    args={
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.SAFE,
)
async def get_ecp_catalog(workspace_id: Optional[str] = None, **kwargs) -> str:
    from ..service.catalog import BEHAVIOR_GUIDE, build_catalog_text

    catalog = build_catalog_text(_ws(workspace_id))
    if not catalog:
        return "（语义目录为空，暂无已确认对象）\n\n" + BEHAVIOR_GUIDE
    return catalog + "\n\n" + BEHAVIOR_GUIDE


@tool(
    "propose_semantic",
    description=(
        "Propose a NEW semantic object (metric/entity/dimension/relation) "
        "when the catalog lacks a concept. Proposals always land in the "
        "confirmation inbox (status=proposed) and do NOT affect queries "
        "until a human confirms them."
    ),
    args={
        "object_id": {"type": "string", "description": "对象 id（ent./mtr./dim./rel. 前缀）"},
        "obj_type": {"type": "string", "description": "entity | metric | relation | dimension"},
        "payload": {
            "type": "object",
            "description": (
                "类型对应的 payload 定义，确认需满足契约："
                "entity 需 binding{table, datasource_id}；"
                "metric 需 entity(实体id) + expression(如 SUM(列))；"
                "dimension 需 column，values 每项需 codes 列表；"
                "relation 需 from + to"
            ),
        },
        "confidence": {"type": "number", "description": "置信度 0-1", "required": False},
        "workspace_id": {
            "type": "string",
            "description": "工作空间 id，默认 default",
            "required": False,
        },
    },
    category=ToolCategory.SEARCH,
    risk_level=ToolRiskLevel.LOW,
)
async def propose_semantic(
    object_id: str,
    obj_type: str,
    payload: Dict[str, Any],
    confidence: Optional[float] = None,
    workspace_id: Optional[str] = None,
    **kwargs,
) -> str:
    from ..config import OBJECT_TYPES
    from ..service.contracts import validate_payload

    ws = _ws(workspace_id)
    if obj_type not in OBJECT_TYPES:
        return json.dumps(
            {"error": f"obj_type 必须是 {OBJECT_TYPES} 之一"}, ensure_ascii=False
        )
    vo = SemanticObjectDao().create_proposal(
        object_id,
        obj_type,
        payload,
        workspace_id=ws,
        confidence=confidence,
        created_by="llm",
        source="agent:propose_semantic",
    )
    OpLogDao().append(
        "propose", ws,
        {"id": object_id, "version": vo.version, "type": obj_type,
         "source": "agent:propose_semantic"},
    )
    resp = {
        "proposal_id": f"{vo.id}@v{vo.version}",
        "status": vo.status,
        "note": "提案已进入确认收件箱，确认前不影响任何查询",
    }
    # 契约校验提示(非阻塞):确认需过可执行级校验,提前告知缺口供自我纠正
    problems = validate_payload(obj_type, vo.payload or {}, level="executable")
    if problems:
        resp["contract_gaps"] = problems
        resp["note"] = (
            "提案已进入确认收件箱，但确认前需补全: " + "; ".join(problems)
        )
    return json.dumps(resp, ensure_ascii=False)


def build_ecp_agent_tools(workspace_id: Optional[str] = None) -> List[FunctionTool]:
    """Build the 6 ECP agent tools with ``workspace_id`` bound by closure.

    Mirrors ``build_scene_management_tools``: workspace_id is captured so the agent
    never passes it (cannot get it wrong -- catalog injected by ECPCapability and
    tool calls always target the same workspace). Tool metadata mirrors the
    ``@tool`` specs above minus workspace_id. Returns ``FunctionTool`` list for
    TOOLS-slot Contributions (consumed by react_master via ``_tool_to_function``).
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID

    async def _search(query: str) -> str:
        return await search_semantics(query=query, workspace_id=ws)

    async def _get_object(object_id: str) -> str:
        return await get_semantic_object(object_id=object_id, workspace_id=ws)

    async def _exec_metric(
        metric_id: str,
        group_by: Optional[List[str]] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        time: Optional[Dict[str, Any]] = None,
        question: Optional[str] = None,
    ) -> str:
        return await execute_metric_query_tool(
            metric_id=metric_id,
            group_by=group_by,
            filters=filters,
            time=time,
            question=question,
            workspace_id=ws,
        )

    async def _exec_raw(datasource_id: int, sql: str, reasoning: str) -> str:
        return await execute_raw_sql(
            datasource_id=datasource_id,
            sql=sql,
            reasoning=reasoning,
            workspace_id=ws,
        )

    async def _catalog() -> str:
        return await get_ecp_catalog(workspace_id=ws)

    async def _miss_report(min_count: int = 2, limit: int = 20) -> str:
        return await get_miss_report(
            min_count=min_count, limit=limit, workspace_id=ws
        )

    async def _query_canon(question: str, object_ids: List[str]) -> str:
        return await query_canon(
            question=question, object_ids=object_ids, workspace_id=ws
        )

    async def _explore_docs(
        question: str, reasoning: str, space: Optional[str] = None, limit: int = 5
    ) -> str:
        return await explore_docs(
            question=question,
            reasoning=reasoning,
            space=space,
            limit=limit,
            workspace_id=ws,
        )

    async def _propose(
        object_id: str,
        obj_type: str,
        payload: Dict[str, Any],
        confidence: Optional[float] = None,
    ) -> str:
        return await propose_semantic(
            object_id=object_id,
            obj_type=obj_type,
            payload=payload,
            confidence=confidence,
            workspace_id=ws,
        )

    return [
        FunctionTool(
            "search_semantics",
            _search,
            description="搜索已确认的语义对象(指标/实体/维度/关系)。回答业务数字问题前先在此查找。",
            args={"query": {"type": "string", "description": "关键词(名称/别名/id)"}},
        ),
        FunctionTool(
            "get_semantic_object",
            _get_object,
            description="获取语义对象完整定义:口径、绑定、维度值、粒度、版本。",
            args={"object_id": {"type": "string", "description": "对象 id,如 mtr.net_sales"}},
        ),
        FunctionTool(
            "execute_metric_query",
            _exec_metric,
            description=(
                "执行已确认指标的查询(唯一产出 ✅ 可信数字的路径)。"
                "所有 id 须来自已确认目录(search_semantics/get_semantic_object)。"
            ),
            args={
                "metric_id": {"type": "string", "description": "已确认指标 id"},
                "group_by": {
                    "type": "array",
                    "description": "分组维度 id 列表",
                    "required": False,
                },
                "filters": {
                    "type": "array",
                    "description": "筛选:[{dim_id, values:[label], mode:include|exclude}]",
                    "required": False,
                },
                "time": {
                    "type": "object",
                    "description": "时间:{range:'YYYY-MM-DD~YYYY-MM-DD', column?}",
                    "required": False,
                },
                "question": {
                    "type": "string",
                    "description": "原始用户问题(用于解析缓存回填)",
                    "required": False,
                },
            },
        ),
        FunctionTool(
            "execute_raw_sql",
            _exec_raw,
            description=(
                "探索路径(⚠️ 未验证但被鼓励)。开放性分析、目录未覆盖的概念、"
                "分布/相关性/自定义口径时主动使用——这是语义层的学习通道。"
                "须告知用户结果为未验证口径,有价值的可复用口径用 propose_semantic 沉淀。"
            ),
            args={
                "datasource_id": {"type": "integer", "description": "数据源 id"},
                "sql": {"type": "string", "description": "SELECT 语句(只读)"},
                "reasoning": {
                    "type": "string",
                    "description": (
                        "探索目的+发现了什么目录没有的概念(飞轮原料,会被聚类学习)。"
                        "示例:'分析门店温度与销售相关性;目录缺少温度-销售关联维度'"
                    ),
                },
            },
        ),
        FunctionTool(
            "get_ecp_catalog",
            _catalog,
            description="获取完整已确认语义目录(紧凑文本)+ 行为约定。进入 ECP 对话时先调用。",
            args={},
        ),
        FunctionTool(
            "get_miss_report",
            _miss_report,
            description=(
                "获取按频次聚类的未覆盖问题(execute_raw_sql 兜底记录)。"
                "用于学习用户反复需要但目录无法回答的概念,"
                "对高频且确实缺失的用 propose_semantic 提案。"
            ),
            args={
                "min_count": {
                    "type": "integer",
                    "description": "只返回出现次数>=此值的聚类,默认 2",
                    "required": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回聚类数,默认 20",
                    "required": False,
                },
            },
        ),
        FunctionTool(
            "query_canon",
            _query_canon,
            description=(
                "文档事实查询的可信路径(✅)。用已确认条目(claim/terminology/policy)"
                "回答制度/定义/规则类问题,返回带引用的答案。"
                "条目 id 须来自 search_semantics/get_semantic_object。"
            ),
            args={
                "question": {"type": "string", "description": "原始事实型问题"},
                "object_ids": {
                    "type": "array",
                    "description": "已确认条目 id 列表",
                },
            },
        ),
        FunctionTool(
            "explore_docs",
            _explore_docs,
            description=(
                "文档探索路径(⚠️ 未验证但被鼓励)。目录未覆盖时在托管知识空间"
                "自由检索,结果须声明未验证口径;发现的可信口径用 "
                "propose_semantic 提案(带 source_quote 和 anchor)。"
            ),
            args={
                "question": {"type": "string", "description": "探索问题"},
                "reasoning": {
                    "type": "string",
                    "description": "探索目的+发现了什么目录没有的概念(飞轮原料)",
                },
                "space": {
                    "type": "string",
                    "description": "限定知识空间 slug,不填检索全部托管空间",
                    "required": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数,默认 5",
                    "required": False,
                },
            },
        ),
        FunctionTool(
            "propose_semantic",
            _propose,
            description="提案新语义对象(指标/实体/维度/关系)。只进确认收件箱,确认前不影响查询。",
            args={
                "object_id": {
                    "type": "string",
                    "description": "对象 id(ent./mtr./dim./rel. 前缀)",
                },
                "obj_type": {
                    "type": "string",
                    "description": "entity | metric | relation | dimension",
                },
                "payload": {
                    "type": "object",
                    "description": (
                        "类型对应的 payload 定义,确认需满足契约:"
                        "entity 需 binding{table, datasource_id};"
                        "metric 需 entity(实体id) + expression(如 SUM(列));"
                        "dimension 需 column,values 每项需 codes 列表;"
                        "relation 需 from + to"
                    ),
                },
                "confidence": {
                    "type": "number",
                    "description": "置信度 0-1",
                    "required": False,
                },
            },
        ),
    ]
