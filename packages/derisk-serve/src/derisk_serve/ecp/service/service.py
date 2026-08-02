"""ECP semantic object service: enforces the write rules of the protocol.

Write rules (docs/ECP.md 3.4), enforced here at a single point:
1. LLM writes are always `proposed`.
2. proposed -> confirmed is restricted to the confirmer list (empty list =
   open bootstrap).
3. Modification = new version + supersedes; no version is mutable or deletable.
4. Queries consume confirmed only (list_catalog); proposed consumption must be
   flagged by callers.
5. Cross-entity queries without a confirmed relation are rejected (enforced in
   the executor, P1).
"""

import logging
from typing import Any, List, Optional

from derisk.component import SystemApp
from derisk_serve.core import BaseService

from ..api.schemas import (
    AssetRefVO,
    CatalogEntryVO,
    ConfirmerVO,
    GraphLinkVO,
    GraphNodeVO,
    GraphVO,
    OpLogVO,
    ReadinessCheckVO,
    ReadinessVO,
    SemanticObjectListVO,
    SemanticObjectVO,
    SpaceInfoVO,
    WorkspaceConfigVO,
)
from ..config import (
    DEFAULT_WORKSPACE_ID,
    OBJECT_TYPES,
    SERVE_SERVICE_COMPONENT_NAME,
    STATUS_DEPRECATED,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    ServeConfig,
)
from ..models.models import (
    AssetRefDao,
    ConfirmerDao,
    EcpSemanticObjectEntity,
    OpLogDao,
    ResolutionCacheDao,
    SemanticEdgeDao,
    SemanticObjectDao,
    WorkspaceConfigDao,
)

logger = logging.getLogger(__name__)


def _normalize_sql_pattern(sql: str, max_len: int = 200) -> str:
    """SQL 归一化为聚类模式键:小写、去字符串/数字字面值、压缩空白、截断。"""
    import re

    s = (sql or "").lower()
    s = re.sub(r"'[^']*'", "?", s)  # 字符串字面值
    s = re.sub(r"\b\d+(\.\d+)?\b", "?", s)  # 数字字面值
    s = re.sub(r"\s*([=<>(),;])\s*", r"\1", s)  # 操作符周围空白(Store = 1 vs Store=1)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len]


def cluster_fallbacks(entries: List[Any]) -> List[dict]:
    """把 op_log fallback 条目按归一化模式聚类(频次降序,全量)。

    kind 分流(db/doc,ECP-unstructured P0):
    - db 条目(detail.sql):按归一化 SQL 模式聚类
    - doc 条目(detail.question):按归一化问题模式聚类
    Service.miss_report 与 get_miss_report 工具共用的聚类核心;截断由调用方做。
    """
    from .resolver import normalize_question

    clusters: dict = {}
    for e in entries:
        detail = e.detail or {}
        if detail.get("kind") == "doc" or "question" in detail:
            kind = "doc"
            pattern = normalize_question(detail.get("question") or "")
            example = detail.get("question") or ""
        else:
            kind = "db"
            pattern = _normalize_sql_pattern(detail.get("sql") or "")
            example = detail.get("sql") or ""
        key = (kind, detail.get("datasource_id"), pattern)
        c = clusters.setdefault(
            key,
            {
                "kind": kind,
                "datasource_id": detail.get("datasource_id"),
                "spaces": detail.get("spaces"),
                "pattern": pattern,
                "count": 0,
                "example_sql": example,
                "reasonings": [],
                "last_seen": e.ts,
            },
        )
        c["count"] += 1
        reasoning = detail.get("reasoning")
        if reasoning and reasoning not in c["reasonings"]:
            c["reasonings"].append(reasoning)
    return sorted(clusters.values(), key=lambda x: -x["count"])


class Service(BaseService[EcpSemanticObjectEntity, None, None]):
    """ECP hard semantic layer service."""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(self, system_app: SystemApp, config: ServeConfig):
        self._config = config
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._object_dao = SemanticObjectDao()
        self._cache_dao = ResolutionCacheDao()
        self._edge_dao = SemanticEdgeDao()
        self._confirmer_dao = ConfirmerDao()
        self._oplog_dao = OpLogDao()
        self._asset_dao = AssetRefDao()
        self._ws_config_dao = WorkspaceConfigDao()

    @property
    def config(self) -> ServeConfig:
        return self._config

    @property
    def dao(self) -> SemanticObjectDao:
        """Returns the internal DAO (primary object DAO for BaseService)."""
        return self._object_dao

    @property
    def object_dao(self) -> SemanticObjectDao:
        return self._object_dao

    @property
    def cache_dao(self) -> ResolutionCacheDao:
        return self._cache_dao

    @property
    def edge_dao(self) -> SemanticEdgeDao:
        return self._edge_dao

    @property
    def oplog_dao(self) -> OpLogDao:
        return self._oplog_dao

    @staticmethod
    def _ws(workspace_id: Optional[str]) -> str:
        return workspace_id or DEFAULT_WORKSPACE_ID

    # ---------------------------------------------------------------- proposals
    def propose(
        self,
        object_id: str,
        obj_type: str,
        payload: dict,
        workspace_id: Optional[str] = None,
        confidence: Optional[float] = None,
        evidence: Optional[list] = None,
        created_by: str = "llm",
        source: Optional[str] = None,
    ) -> SemanticObjectVO:
        """Create a proposal. Write rule 1: always lands in `proposed`."""
        if obj_type not in OBJECT_TYPES:
            raise ValueError(
                f"Invalid obj_type '{obj_type}', must be one of {OBJECT_TYPES}"
            )
        ws = self._ws(workspace_id)
        vo = self._object_dao.create_proposal(
            object_id=object_id,
            obj_type=obj_type,
            payload=payload,
            workspace_id=ws,
            confidence=confidence,
            evidence=evidence,
            created_by=created_by,
            source=source,
        )
        # 去重命中时 create_proposal 返回已有 confirmed VO(status=confirmed),
        # 不记 propose oplog(实际未产生新提案)。
        if vo.status == STATUS_PROPOSED:
            self._oplog_dao.append(
                "propose",
                ws,
                {"id": object_id, "version": vo.version, "type": obj_type,
                 "created_by": created_by, "source": source},
            )
        return vo

    # ------------------------------------------------------------------ confirm
    def confirm(
        self,
        object_id: str,
        version: int,
        user_id: str,
        workspace_id: Optional[str] = None,
        edited_payload: Optional[dict] = None,
    ) -> SemanticObjectVO:
        """Confirm a proposal. Write rules 2 & 3.

        With edited_payload: create a new version from the edit and confirm it
        (edit-then-confirm). The confirmed version supersedes older confirmed
        versions and invalidates resolution cache entries referencing the id.

        晋升门禁:confirmed = 可执行状态,确认前必须过 contracts 可执行级校验,
        不合格拒绝并返回问题列表(机器背书人类确认,防止"已确认但不可执行"
        对象入库——execute_metric_query 全线 PAYLOAD_INVALID 的根因)。
        校验前先 normalize:机械形态问题(entity_bindings→entity、code→codes
        等)自愈后以归一化 payload 写新版本确认,不折腾用户手改。
        """
        from .contracts import normalize_payload, validate_payload

        ws = self._ws(workspace_id)
        if not self._confirmer_dao.is_confirmer(ws, user_id):
            raise PermissionError(
                f"User '{user_id}' is not a confirmer of workspace '{ws}'"
            )
        if edited_payload is not None:
            target = self._object_dao.get_version(object_id, version, ws)
            if not target:
                raise ValueError(f"Object {object_id}@v{version} not found")
            normalized = normalize_payload(target.obj_type, edited_payload)
            problems = validate_payload(
                target.obj_type, normalized, level="executable"
            )
            if problems:
                raise ValueError(
                    f"payload 不满足可执行契约: {'; '.join(problems)}"
                )
            vo = self._object_dao.create_confirmed_version(
                object_id=object_id,
                obj_type=target.obj_type,
                payload=normalized,
                workspace_id=ws,
                user_id=user_id,
                supersedes=None,
                evidence=target.evidence,
                source=f"edit_of:{object_id}@v{version}",
            )
        else:
            proposed = self._object_dao.get_version(object_id, version, ws)
            if not proposed:
                raise ValueError(
                    f"Object {object_id}@v{version} not found or not in proposed"
                )
            normalized = normalize_payload(
                proposed.obj_type, proposed.payload or {}
            )
            problems = validate_payload(
                proposed.obj_type, normalized, level="executable"
            )
            if problems:
                raise ValueError(
                    f"对象 {object_id}@v{version} 不满足可执行契约,"
                    f"请编辑补全后再确认: {'; '.join(problems)}"
                )
            if normalized != (proposed.payload or {}):
                # 归一化有改动 → 以归一化 payload 写新版本确认(自愈)
                vo = self._object_dao.create_confirmed_version(
                    object_id=object_id,
                    obj_type=proposed.obj_type,
                    payload=normalized,
                    workspace_id=ws,
                    user_id=user_id,
                    supersedes=None,
                    evidence=proposed.evidence,
                    source=f"normalize_of:{object_id}@v{version}",
                )
            else:
                vo = self._object_dao.confirm_version(object_id, version, ws, user_id)
            if not vo:
                raise ValueError(
                    f"Object {object_id}@v{version} not found or not in proposed"
                )
        invalidated = self._cache_dao.invalidate_referencing(object_id, ws)
        self._oplog_dao.append(
            "confirm",
            ws,
            {"id": object_id, "version": vo.version, "by": user_id,
             "edited": edited_payload is not None,
             "cache_invalidated": invalidated},
        )
        return vo

    def reject(
        self,
        object_id: str,
        version: int,
        user_id: str,
        workspace_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> SemanticObjectVO:
        ws = self._ws(workspace_id)
        if not self._confirmer_dao.is_confirmer(ws, user_id):
            raise PermissionError(
                f"User '{user_id}' is not a confirmer of workspace '{ws}'"
            )
        vo = self._object_dao.update_status(object_id, version, ws, STATUS_REJECTED)
        if not vo:
            raise ValueError(f"Object {object_id}@v{version} not found")
        self._oplog_dao.append(
            "reject", ws,
            {"id": object_id, "version": version, "by": user_id, "reason": reason},
        )
        return vo

    def deprecate(
        self,
        object_id: str,
        user_id: str,
        workspace_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> SemanticObjectVO:
        """Deprecate the confirmed version of an object (manual offlining)."""
        ws = self._ws(workspace_id)
        if not self._confirmer_dao.is_confirmer(ws, user_id):
            raise PermissionError(
                f"User '{user_id}' is not a confirmer of workspace '{ws}'"
            )
        confirmed = self._object_dao.get_confirmed(object_id, ws)
        if not confirmed:
            raise ValueError(f"Object {object_id} has no confirmed version")
        vo = self._object_dao.update_status(
            object_id, confirmed.version, ws, STATUS_DEPRECATED
        )
        invalidated = self._cache_dao.invalidate_referencing(object_id, ws)
        self._oplog_dao.append(
            "deprecate", ws,
            {"id": object_id, "version": confirmed.version, "by": user_id,
             "reason": reason, "cache_invalidated": invalidated},
        )
        return vo

    # ------------------------------------------------------------- admin(契约)
    def contract_check(self, workspace_id: Optional[str] = None) -> dict:
        """扫描 confirmed 对象的契约合规性(只读)。

        返回不合规清单(对象 id + 问题列表),供管理界面/启动 lint 使用。
        """
        from .contracts import validate_payload

        ws = self._ws(workspace_id)
        entries = self._object_dao.list_catalog(ws)
        non_compliant = []
        for e in entries:
            vo = self._object_dao.get_confirmed(e.id, ws)
            if not vo:
                continue
            problems = validate_payload(e.obj_type, vo.payload or {}, level="executable")
            if problems:
                non_compliant.append(
                    {"id": e.id, "obj_type": e.obj_type, "version": vo.version,
                     "problems": problems}
                )
        return {
            "workspace_id": ws,
            "total": len(entries),
            "non_compliant_count": len(non_compliant),
            "non_compliant": non_compliant,
        }

    def normalize_confirmed(
        self, workspace_id: Optional[str] = None, user_id: str = "system"
    ) -> dict:
        """一键修复不合规 confirmed 对象(契约归一化)。

        对每个 normalize 后可消除不合规项的对象,经 create_confirmed_version
        写**新版本**(版本不可变设计的正确姿势;不是 in-place 改 payload)——
        走应用自己的 DAO/连接,规避外部直写 WAL 竞态(2026-08-01 两次迁移
        被重启窗口回退的根治)。normalize 后仍不合规的对象跳过并列出(需人工
        编辑补全,如缺 entity 引用)。
        """
        from .contracts import normalize_payload, validate_payload

        ws = self._ws(workspace_id)
        check = self.contract_check(ws)
        fixed, skipped = [], []
        for item in check["non_compliant"]:
            vo = self._object_dao.get_confirmed(item["id"], ws)
            if not vo:
                continue
            normalized = normalize_payload(vo.obj_type, dict(vo.payload or {}))
            problems = validate_payload(vo.obj_type, normalized, level="executable")
            if problems:
                skipped.append({"id": item["id"], "problems": problems})
                continue
            new_vo = self._object_dao.create_confirmed_version(
                object_id=vo.id,
                obj_type=vo.obj_type,
                payload=normalized,
                workspace_id=ws,
                user_id=user_id,
                supersedes=None,
                evidence=vo.evidence,
                source="admin:normalize_confirmed",
            )
            fixed.append({"id": vo.id, "version": new_vo.version})
        if fixed:
            self._oplog_dao.append(
                "normalize", ws,
                {"fixed": len(fixed), "skipped": len(skipped), "by": user_id},
            )
        return {
            "workspace_id": ws,
            "checked": check["total"],
            "fixed": fixed,
            "skipped": skipped,
        }

    # ------------------------------------------------------- admin(miss 飞轮)
    def miss_report(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 20,
        scan_size: int = 500,
    ) -> dict:
        """聚类 op_log fallback miss(execute_raw_sql 兜底记录)。

        按归一化 SQL 模式分组(忽略字面值/空白差异),按频次排序——
        "大家在裸查什么"的可见化,learn_from_misses 的输入。
        """
        ws = self._ws(workspace_id)
        entries = self._oplog_dao.list(ws, op="fallback", page=1, page_size=scan_size)
        all_clusters = cluster_fallbacks(entries)
        return {
            "workspace_id": ws,
            "total_fallbacks": len(entries),
            "cluster_count": len(all_clusters),
            "clusters": all_clusters[:limit],
        }

    @staticmethod
    def build_miss_context(clusters: List[dict], max_items: int = 10) -> str:
        """把 miss 聚类构建成提案 agent 的领域上下文(问题驱动的提案素材)。"""
        if not clusters:
            return ""
        lines = [
            "【未覆盖的真实问题(miss 聚类,按频次排序)】",
            "以下是用户真实问过、但语义目录无法覆盖而走了 execute_raw_sql 兜底的查询。",
            "请优先为这些高频问题提炼可确认的语义资产(指标/维度/值字典),",
            "使后续同类问题能走 execute_metric_query 可信路径:",
        ]
        for i, c in enumerate(clusters[:max_items], 1):
            kind = c.get("kind", "db")
            if kind == "doc":
                lines.append(
                    f"\n{i}. [出现 {c['count']} 次] 文档问题(空间: "
                    f"{','.join(c.get('spaces') or ['?'])})"
                )
                example = (c.get("example_sql") or "").strip()
                if example:
                    lines.append(f"   问题: {example[:300]}")
            else:
                lines.append(
                    f"\n{i}. [出现 {c['count']} 次] 数据源 #{c.get('datasource_id')}"
                )
                example = (c.get("example_sql") or "").strip()
                if example:
                    lines.append(f"   SQL: {example[:400]}")
            for r in (c.get("reasonings") or [])[:3]:
                lines.append(f"   未命中原因: {r}")
        return "\n".join(lines)

    # -------------------------------------------------------------------- reads
    def inbox(
        self,
        workspace_id: Optional[str] = None,
        obj_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SemanticObjectListVO:
        """Confirmation inbox: latest proposed versions."""
        return self._object_dao.list_latest(
            workspace_id=self._ws(workspace_id),
            obj_type=obj_type,
            status=STATUS_PROPOSED,
            page=page,
            page_size=page_size,
        )

    def list_objects(
        self,
        workspace_id: Optional[str] = None,
        obj_type: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SemanticObjectListVO:
        return self._object_dao.list_latest(
            workspace_id=self._ws(workspace_id),
            obj_type=obj_type,
            status=status,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )

    def get_object(
        self, object_id: str, workspace_id: Optional[str] = None
    ) -> Optional[SemanticObjectVO]:
        """Latest confirmed version; falls back to latest proposed for inbox UI."""
        ws = self._ws(workspace_id)
        vo = self._object_dao.get_confirmed(object_id, ws)
        if vo:
            return vo
        history = self._object_dao.version_history(object_id, ws)
        return history[0] if history else None

    def version_history(
        self, object_id: str, workspace_id: Optional[str] = None
    ) -> List[SemanticObjectVO]:
        return self._object_dao.version_history(object_id, self._ws(workspace_id))

    def catalog(
        self, workspace_id: Optional[str] = None, keyword: Optional[str] = None
    ) -> List[CatalogEntryVO]:
        """Write rule 4: the catalog exposes confirmed objects only."""
        return self._object_dao.list_catalog(self._ws(workspace_id), keyword)

    # ---------------------------------------------------------------- confirmers
    def list_confirmers(self, workspace_id: Optional[str] = None) -> List[ConfirmerVO]:
        return self._confirmer_dao.list(self._ws(workspace_id))

    def add_confirmer(
        self, user_id: str, workspace_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> None:
        ws = self._ws(workspace_id)
        self._confirmer_dao.add(ws, user_id, scope)
        self._oplog_dao.append(
            "confirmer_add", ws, {"user_id": user_id, "scope": scope}
        )

    def remove_confirmer(self, confirmer_id: int) -> bool:
        return self._confirmer_dao.remove(confirmer_id)

    # -------------------------------------------------------------------- op log
    def list_op_log(
        self,
        workspace_id: Optional[str] = None,
        op: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> List[OpLogVO]:
        return self._oplog_dao.list(self._ws(workspace_id), op, page, page_size)

    # -------------------------------------------------------------- asset refs
    @property
    def asset_dao(self) -> AssetRefDao:
        return self._asset_dao

    def register_asset(
        self,
        kind: str,
        ref_id: str,
        workspace_id: Optional[str] = None,
        ref_meta: Optional[dict] = None,
    ) -> AssetRefVO:
        ws = self._ws(workspace_id)
        vo = self._asset_dao.register(kind, ref_id, ws, ref_meta)
        self._oplog_dao.append(
            "asset_register", ws, {"kind": kind, "ref_id": ref_id}
        )
        return vo

    def list_assets(
        self, workspace_id: Optional[str] = None, kind: Optional[str] = None
    ) -> List[AssetRefVO]:
        return self._asset_dao.list(self._ws(workspace_id), kind)

    def readiness(
        self, datasource_id: int, workspace_id: Optional[str] = None
    ) -> ReadinessVO:
        """Check whether a DB asset is ready for proposal generation.

        Assets arrive incrementally (DB configured -> schema learned -> docs
        ingested); proposals must not run on incomplete material.
        """
        from derisk_serve.datasource.manages.connect_config_db import (
            ConnectConfigDao,
        )
        from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

        ws = self._ws(workspace_id)
        checks: List[ReadinessCheckVO] = []

        config = ConnectConfigDao().get_one({"id": datasource_id})
        ds_ok = config is not None
        checks.append(
            ReadinessCheckVO(
                item="datasource_exists",
                ready=ds_ok,
                detail=getattr(config, "db_name", None) if ds_ok else "数据源不存在",
            )
        )

        spec_count = 0
        if ds_ok:
            spec_count = len(TableSpecDao().get_all_by_datasource(datasource_id))
        checks.append(
            ReadinessCheckVO(
                item="schema_learned",
                ready=spec_count > 0,
                detail=f"已学习 {spec_count} 张表"
                if spec_count
                else "尚未完成 Schema 学习，请先在数据源管理中执行学习",
            )
        )

        # Document assets are optional but recommended (industry knowledge
        # feeds proposal quality and confirmation evidence).
        doc_refs = [a for a in self._asset_dao.list(ws) if a.kind in ("document", "space")]
        checks.append(
            ReadinessCheckVO(
                item="documents",
                ready=True,
                detail=f"已登记 {len(doc_refs)} 个文档资产"
                if doc_refs
                else "未登记文档资产（可选；行业口径文档可提升提案质量）",
            )
        )

        ready = all(c.ready for c in checks if c.item != "documents")
        return ReadinessVO(
            kind="db", ref_id=str(datasource_id), ready=ready, checks=checks
        )

    # -------------------------------------------------------------------- graph
    def graph(self, workspace_id: Optional[str] = None) -> GraphVO:
        """Semantic graph view: latest-version objects as nodes, edge table as
        links (the edge table is a materialized projection, P2 maintains it on
        writes; nodes always reflect current objects)."""
        ws = self._ws(workspace_id)
        objects = self._object_dao.list_latest(
            workspace_id=ws, page=1, page_size=1000
        ).items
        nodes = [
            GraphNodeVO(
                id=o.id, obj_type=o.obj_type, name=o.name,
                status=o.status, version=o.version,
            )
            for o in objects
        ]
        links: List[GraphLinkVO] = []
        seen = set()
        with self._edge_dao.session(commit=False) as session:
            from ..models.models import EcpSemanticEdgeEntity

            rows = (
                session.query(EcpSemanticEdgeEntity)
                .filter(EcpSemanticEdgeEntity.workspace_id == ws)
                .all()
            )
            for r in rows:
                key = (r.src, r.edge_type, r.dst)
                if key in seen:
                    continue
                seen.add(key)
                links.append(
                    GraphLinkVO(
                        source=r.src, target=r.dst,
                        edge_type=r.edge_type, status=r.status,
                    )
                )
        return GraphVO(nodes=nodes, links=links)

    # ------------------------------------------------------------- ECP space
    async def get_or_create_space(
        self, workspace_id: Optional[str] = None, owner_id: Optional[str] = None
    ) -> SpaceInfoVO:
        """Get-or-create the ECP soft-layer knowledge space for a workspace.

        The soft layer IS a knowledge space (llm-wiki); ECP only customizes
        its schema.md (P3). Slug convention: ecp-<workspace_id>.
        """
        ws = self._ws(workspace_id)
        slug = f"ecp-{ws}"
        from derisk_serve.knowledge.config import (
            SERVE_SERVICE_COMPONENT_NAME as KNOWLEDGE_SERVICE,
        )
        from derisk_serve.knowledge.service.service import Service as KnowledgeService

        ks = self._system_app.get_component(KNOWLEDGE_SERVICE, KnowledgeService)
        created = False
        try:
            await ks.get_space_config(slug)
        except Exception:  # noqa: BLE001
            await ks.create_space(slug, owner_id=owner_id, space_type="personal")
            created = True
            self._oplog_dao.append("space_create", ws, {"slug": slug})
        self._asset_dao.register("space", slug, ws, ref_meta={"name": slug})
        return SpaceInfoVO(slug=slug, workspace_id=ws, created=created)

    # ------------------------------------------------------ workspace config
    def get_workspace_config(
        self, workspace_id: Optional[str] = None
    ) -> WorkspaceConfigVO:
        return self._ws_config_dao.get(self._ws(workspace_id))

    def save_workspace_config(
        self,
        workspace_id: Optional[str] = None,
        proposal_agent_id: Optional[str] = None,
    ) -> WorkspaceConfigVO:
        ws = self._ws(workspace_id)
        vo = self._ws_config_dao.upsert(ws, proposal_agent_id)
        self._oplog_dao.append(
            "config_update", ws, {"proposal_agent_id": proposal_agent_id}
        )
        return vo
