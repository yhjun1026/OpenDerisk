"""Binding executors: polymorphic execution over asset bindings (ECP v1.2).

`entity.binding.kind` selects a BindingExecutor implementation. The gated
`execute_metric_query` tool is the ONLY path that produces ✅ verified
numbers; it delegates physical execution to the executor registered for the
binding kind. New binding sources (API in P3, Excel later) plug in here
without touching the protocol.

The DB executor assembles SQL deterministically with sqlglot from the frozen
metric expression — the LLM picks catalog IDs, code assembles the SQL.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import sqlglot
from sqlglot import exp

from .contracts import validate_payload

logger = logging.getLogger(__name__)


class GateError(Exception):
    """Deterministic gate rejection (agent-visible, never bypassable)."""

    def __init__(self, message: str, code: str = "GATE_REJECTED"):
        super().__init__(message)
        self.code = code


class BindingExecutor:
    """Interface for executing a confirmed metric against its binding."""

    binding_kind: str = ""

    def validate_binding(self, binding: Dict[str, Any]) -> List[str]:
        """Return a list of binding problems; empty means valid."""
        raise NotImplementedError

    def execute_metric_query(
        self,
        daos,
        metric_id: str,
        workspace_id: str,
        group_by: Optional[List[str]] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        time_range: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class DbBindingExecutor(BindingExecutor):
    """Executes against RDBMS bindings (read-only, sqlglot assembly).

    Gate steps (all deterministic, agent-invisible):
      ① all IDs exist and are confirmed
      ② filter labels ∈ dimension.values → mapped to codes
      ③ group_by dims belong to the metric's entity (grain check)
      ④ cross-entity requires a confirmed relation (write rule 5) — otherwise
        reject AND auto-create a relation proposal
      ⑤ SQL assembled from frozen expression + default/extra filters
      ⑥ assembled SQL must contain every frozen filter string
      ⑦ read-only execution via connector
      ⑧ lineage recorded by the caller
    """

    binding_kind = "db"

    def __init__(self, connector_factory: Optional[Callable[[int], Any]] = None):
        # Injectable for tests; default resolves via CFG.local_db_manager.
        self._connector_factory = connector_factory or self._default_connector

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _default_connector(datasource_id: int):
        from derisk._private.config import Config
        from derisk_serve.datasource.manages.connect_config_db import (
            ConnectConfigDao,
        )

        config = ConnectConfigDao().get_one({"id": datasource_id})
        db_name = getattr(config, "db_name", None)
        if not db_name:
            raise GateError(f"数据源 {datasource_id} 不存在", code="BINDING_INVALID")
        return Config().local_db_manager.get_connector(db_name)

    # ------------------------------------------------------------------- gate
    def execute_metric_query(
        self,
        daos,
        metric_id: str,
        workspace_id: str,
        group_by: Optional[List[str]] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        time_range: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        group_by = group_by or []
        filters = filters or []

        # ① metric + entity must exist and be confirmed
        metric = daos.objects.get_confirmed(metric_id, workspace_id)
        if not metric or metric.obj_type != "metric":
            raise GateError(f"指标 {metric_id} 不存在或未确认", code="NOT_CONFIRMED")
        mp = metric.payload or {}
        # payload 形状校验走 contracts 单一事实来源(与 confirm 晋升门禁同规则)
        problems = validate_payload("metric", mp, level="executable")
        if problems:
            raise GateError(
                f"指标 {metric_id}: {'; '.join(problems)}", code="PAYLOAD_INVALID"
            )
        entity_id = mp.get("entity")
        entity = daos.objects.get_confirmed(entity_id, workspace_id)
        if not entity:
            raise GateError(f"实体 {entity_id} 不存在或未确认", code="NOT_CONFIRMED")
        ep = entity.payload or {}
        binding = ep.get("binding") or {}
        problems = validate_payload("entity", ep, level="executable")
        if problems:
            raise GateError(
                f"实体 {entity_id}: {'; '.join(problems)}",
                code="BINDING_INVALID",
            )

        # ②③ dimensions: resolve filters + group_by
        dim_conditions: List[str] = []
        group_cols: List[str] = []
        involved_entities = {entity_id}
        for dim_id in group_by:
            dim = self._confirmed_dim(daos, dim_id, workspace_id)
            self._check_grain(dim, mp)
            involved_entities.add(dim.payload.get("entity") or entity_id)
            group_cols.append(dim.payload["column"])
        for f in filters:
            dim = self._confirmed_dim(daos, f.get("dim_id") or f.get("dim"), workspace_id)
            involved_entities.add(dim.payload.get("entity") or entity_id)
            dim_conditions.append(self._dim_condition(dim, f))

        # ④ cross-entity requires a confirmed relation (rule 5)
        involved_entities.discard(entity_id)
        for other in involved_entities:
            self._require_relation(daos, entity_id, other, workspace_id)

        # ⑤ assemble SQL deterministically
        sql = self._assemble_sql(mp, ep, binding, group_cols, dim_conditions, time_range)

        # ⑥ frozen filters must be present in the SQL (defense in depth:
        # assembly is deterministic so this should never fail). Compared in
        # sqlglot-normalized form (e.g. '!=' normalizes to '<>').
        sql_norm = sqlglot.parse_one(sql).sql()
        for frag in (ep.get("default_filters") or []) + (mp.get("extra_filters") or []):
            if frag and sqlglot.parse_one(frag).sql() not in sql_norm:
                raise GateError(
                    f"SQL 组装缺少冻结过滤条件: {frag}", code="ASSEMBLY_INVALID"
                )

        # ⑦ read-only execution
        datasource_id = binding.get("datasource_id")
        connector = self._connector_factory(datasource_id)
        raw = connector.run(sql)
        columns, rows = [], []
        if raw:
            columns = list(raw[0])
            rows = [dict(zip(columns, r)) for r in raw[1:]]

        return {
            "rows": rows,
            "columns": columns,
            "row_count": len(rows),
            "trust": "verified",
            "sql": sql,
            "lineage": {
                "metric_id": metric_id,
                "metric_version": metric.version,
                "entity_id": entity_id,
                "entity_version": entity.version,
                "table": binding.get("table"),
                "datasource_id": datasource_id,
                "executed_at": datetime.now().isoformat(),
            },
        }

    # ------------------------------------------------------------------ steps
    @staticmethod
    def _confirmed_dim(daos, dim_id: Optional[str], workspace_id: str):
        if not dim_id:
            raise GateError("维度 id 缺失", code="DIM_INVALID")
        dim = daos.objects.get_confirmed(dim_id, workspace_id)
        if not dim or dim.obj_type != "dimension":
            raise GateError(f"维度 {dim_id} 不存在或未确认", code="NOT_CONFIRMED")
        problems = validate_payload("dimension", dim.payload or {}, level="executable")
        if problems:
            raise GateError(
                f"维度 {dim_id}: {'; '.join(problems)}", code="PAYLOAD_INVALID"
            )
        return dim

    @staticmethod
    def _check_grain(dim, metric_payload: Dict[str, Any]) -> None:
        grain = metric_payload.get("grain") or []
        if not grain:
            return
        col = dim.payload["column"]
        name = (dim.name or "").lower()
        if col not in grain and name not in [g.lower() for g in grain]:
            raise GateError(
                f"维度 {dim.id}（列 {col}）不在指标粒度 {grain} 内",
                code="GRAIN_INVALID",
            )

    @staticmethod
    def _dim_condition(dim, f: Dict[str, Any]) -> str:
        """Map filter labels → codes via the dimension value dictionary."""
        labels = f.get("values") or f.get("values_label") or []
        mode = (f.get("mode") or "include").lower()
        column = dim.payload["column"]
        codes: List[str] = []
        available = []
        for v in dim.payload.get("values") or []:
            available.append(v.get("label"))
            for lbl in labels:
                if lbl == v.get("label") or lbl in (v.get("aliases") or []):
                    codes.extend(str(c) for c in (v.get("codes") or []))
        missing = [
            lbl
            for lbl in labels
            if not any(
                lbl == v.get("label") or lbl in (v.get("aliases") or [])
                for v in dim.payload.get("values") or []
            )
        ]
        if missing:
            raise GateError(
                f"维度值 {missing} 不在 {dim.id} 的值字典 {available} 中",
                code="DIM_VALUE_UNKNOWN",
            )
        if not codes:
            raise GateError(f"维度 {dim.id} 筛选值为空", code="DIM_INVALID")
        quoted = ", ".join(f"'{c}'" for c in sorted(set(codes)))
        op = "NOT IN" if mode == "exclude" else "IN"
        return f"{column} {op} ({quoted})"

    @staticmethod
    def _require_relation(daos, from_id: str, to_id: str, workspace_id: str) -> None:
        """Write rule 5: no confirmed relation → reject + auto-propose one."""
        for rel_id in (f"rel.{from_id.split('.', 1)[-1]}__{to_id.split('.', 1)[-1]}",):
            rel = daos.objects.get_confirmed(rel_id, workspace_id)
            if rel and rel.obj_type == "relation":
                return
        # Fallback: scan confirmed relations by payload endpoints.
        for entry in daos.objects.list_catalog(workspace_id):
            if entry.obj_type != "relation":
                continue
            rel = daos.objects.get_confirmed(entry.id, workspace_id)
            if not rel:
                continue
            rp = rel.payload or {}
            pair = {rp.get("from"), rp.get("to")}
            if pair == {from_id, to_id}:
                return
        # Auto-propose the missing relation, then reject.
        proposal_id = f"rel.{from_id.split('.', 1)[-1]}__{to_id.split('.', 1)[-1]}"
        try:
            daos.objects.create_proposal(
                proposal_id,
                "relation",
                {"from": from_id, "to": to_id, "path": None, "cardinality": None},
                workspace_id=workspace_id,
                created_by="llm",
                source="gate:rule5",
            )
        except Exception:  # noqa: BLE001
            pass
        raise GateError(
            f"跨实体查询需要已确认的 relation（{from_id} → {to_id}）。"
            f"已自动生成 relation 提案 {proposal_id}，请确认后重试。",
            code="RELATION_MISSING",
        )

    # --------------------------------------------------------------- assembly
    def _assemble_sql(
        self,
        mp: Dict[str, Any],
        ep: Dict[str, Any],
        binding: Dict[str, Any],
        group_cols: List[str],
        dim_conditions: List[str],
        time_range: Optional[Dict[str, Any]],
    ) -> str:
        expression = mp.get("expression")
        if not expression:
            raise GateError("指标缺少冻结 expression", code="PAYLOAD_INVALID")
        table = binding["table"]

        select_exprs = [sqlglot.parse_one(c) for c in group_cols]
        select_exprs.append(sqlglot.parse_one(f"{expression} AS value"))

        query = sqlglot.select(*select_exprs).from_(table)

        conditions: List[str] = []
        conditions.extend(ep.get("default_filters") or [])
        conditions.extend(mp.get("extra_filters") or [])
        conditions.extend(dim_conditions)
        time_cond = self._time_condition(ep, time_range)
        if time_cond:
            conditions.append(time_cond)
        for cond in conditions:
            query = query.where(cond)

        if group_cols:
            query = query.group_by(*group_cols)

        return query.sql()

    @staticmethod
    def _time_condition(
        ep: Dict[str, Any], time_range: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        if not time_range:
            return None
        rng = time_range.get("range")
        if not rng or "~" not in str(rng):
            return None
        column = time_range.get("column")
        if not column:
            for name, meta in (ep.get("fields") or {}).items():
                if (meta or {}).get("role") == "time":
                    column = name
                    break
        if not column:
            raise GateError(
                "需要时间筛选但实体未定义 role=time 的字段", code="TIME_COLUMN_MISSING"
            )
        start, end = [s.strip() for s in str(rng).split("~", 1)]
        return f"{column} BETWEEN '{start}' AND '{end}'"


class _ExecutorDaos:
    """Thin DAO bundle passed to executors (keeps executor decoupled from
    the Service component so tools and tests can construct it directly)."""

    def __init__(self):
        from ..models.models import SemanticObjectDao

        self.objects = SemanticObjectDao()


class DocBindingExecutor(BindingExecutor):
    """Executes against document bindings — evidence playback (P0 文档扩展)。

    与 DB 侧"SQL 确定性组装"对称,文档侧是**证据确定性回放**:
      ① claim/terminology/policy 必须 confirmed(同 metric 门禁)
      ② binding 契约校验(contracts 单一事实来源)
      ③ anchor 回放:经 doc_fetcher 取原文,校验冻结 source_quote 为子串
         (找到但不含 → ANCHOR_DRIFT(文档改版信号);基础设施不可用 →
          best-effort 跳过,lineage 记 anchor_verified=None)
      ④ 返回带引用的答案,trust=verified + 血缘
    """

    binding_kind = "doc"
    _DOC_TYPES = ("claim", "terminology", "policy")

    def __init__(self, doc_fetcher: Optional[Callable] = None, **_kwargs):
        # doc_fetcher(space, doc_id) -> Optional[str](原文文本);可注入供测试
        self._doc_fetcher = doc_fetcher or self._default_doc_fetcher

    @staticmethod
    async def _default_doc_fetcher(space: str, doc_id: str) -> Optional[str]:
        """经 KnowledgeService 取 verbat 原文。找不到/服务不可用返回 None。"""
        try:
            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if system_app is None:
                return None
            from derisk_serve.knowledge.config import (
                SERVE_SERVICE_COMPONENT_NAME as KNOWLEDGE_SERVICE,
            )
            from derisk_serve.knowledge.service.service import (
                Service as KnowledgeService,
            )

            ks = system_app.get_component(KNOWLEDGE_SERVICE, KnowledgeService)
            vault = await ks.get_vault(space)
            v = await vault.verbat_get(doc_id)
            if v is None:
                return None
            return getattr(v, "content", None) or getattr(v, "text", None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[doc-executor] fetch {space}:{doc_id} failed: {e}")
            return None

    async def execute_claim_query(
        self, daos, object_ids: List[str], workspace_id: str
    ) -> Dict[str, Any]:
        answers: List[Dict[str, Any]] = []
        for oid in object_ids:
            obj = daos.objects.get_confirmed(oid, workspace_id)
            if not obj or obj.obj_type not in self._DOC_TYPES:
                raise GateError(f"条目 {oid} 不存在或未确认", code="NOT_CONFIRMED")
            p = obj.payload or {}
            problems = validate_payload(obj.obj_type, p, level="executable")
            if problems:
                raise GateError(
                    f"条目 {oid}: {'; '.join(problems)}", code="PAYLOAD_INVALID"
                )
            binding = p.get("binding") or {}
            quote = p.get("source_quote")
            anchor_verified: Optional[bool] = None
            original = await self._doc_fetcher(
                binding.get("space", ""), binding.get("doc_id", "")
            )
            if original is not None:
                if quote and quote not in original:
                    raise GateError(
                        f"条目 {oid} 锚点漂移:原文中未找到冻结摘录"
                        f"(文档可能已改版),请重新确认或更新 anchor",
                        code="ANCHOR_DRIFT",
                    )
                anchor_verified = True
            answers.append(
                {
                    "id": oid,
                    "type": obj.obj_type,
                    "version": obj.version,
                    "text": p.get("text") or p.get("definition") or p.get("rule"),
                    "condition": p.get("condition"),
                    "quote": quote,
                    "citation": {
                        "space": binding.get("space"),
                        "doc_id": binding.get("doc_id"),
                        "anchor": binding.get("anchor"),
                        "anchor_verified": anchor_verified,
                    },
                }
            )
        return {
            "answers": answers,
            "trust": "verified",
            "lineage": {
                "workspace_id": workspace_id,
                "executed_at": datetime.now().isoformat(),
            },
        }


# Executor registry keyed by binding kind.
EXECUTORS: Dict[str, type] = {
    DbBindingExecutor.binding_kind: DbBindingExecutor,
    DocBindingExecutor.binding_kind: DocBindingExecutor,
}


def get_executor(binding_kind: str, **kwargs) -> Optional[BindingExecutor]:
    cls = EXECUTORS.get(binding_kind)
    return cls(**kwargs) if cls else None


async def execute_claim_query(
    object_ids: List[str],
    workspace_id: str,
    doc_fetcher: Optional[Callable] = None,
) -> Dict[str, Any]:
    """The gated ✅ path for document canon (P0 文档扩展)。

    与 execute_metric_query 对称:confirmed 条目 → 契约校验 → anchor 回放
    → 带引用答案(trust=verified + 血缘)。
    """
    daos = _ExecutorDaos()
    executor = DocBindingExecutor(doc_fetcher=doc_fetcher)
    return await executor.execute_claim_query(daos, object_ids, workspace_id)


def execute_metric_query(
    metric_id: str,
    workspace_id: str,
    group_by: Optional[List[str]] = None,
    filters: Optional[List[Dict[str, Any]]] = None,
    time_range: Optional[Dict[str, Any]] = None,
    connector_factory: Optional[Callable[[int], Any]] = None,
) -> Dict[str, Any]:
    """The gated ✅ path. Resolves the metric's binding kind and delegates."""
    daos = _ExecutorDaos()
    metric = daos.objects.get_confirmed(metric_id, workspace_id)
    if not metric:
        raise GateError(f"指标 {metric_id} 不存在或未确认", code="NOT_CONFIRMED")
    entity = daos.objects.get_confirmed(
        (metric.payload or {}).get("entity") or "", workspace_id
    )
    kind = ((entity.payload or {}).get("binding") or {}).get("kind", "db") if entity else "db"
    executor = get_executor(kind, connector_factory=connector_factory)
    if not executor:
        raise GateError(f"不支持的绑定类型 {kind}", code="BINDING_INVALID")
    return executor.execute_metric_query(
        daos, metric_id, workspace_id,
        group_by=group_by, filters=filters, time_range=time_range,
    )
