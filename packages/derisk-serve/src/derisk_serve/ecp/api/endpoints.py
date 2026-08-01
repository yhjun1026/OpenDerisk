"""ECP API endpoints.

Mounted under /api/v1/serve/ecp. Covers the confirmation inbox, object
catalog browsing, version history, confirmer management and proposal
generation (DB asset path).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..api.schemas import (
    AssetRefRegisterRequest,
    AssetRefVO,
    CatalogEntryVO,
    ConfirmRequest,
    ConfirmerCreateRequest,
    ConfirmerVO,
    DeprecateRequest,
    GenerateProposalsRequest,
    GenerateProposalsVO,
    GraphVO,
    OpLogVO,
    ProposeRequest,
    ReadinessVO,
    RejectRequest,
    SemanticObjectListVO,
    SemanticObjectVO,
    SpaceInfoVO,
    WorkspaceConfigUpdateRequest,
    WorkspaceConfigVO,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service

logger = logging.getLogger(__name__)

router = APIRouter()

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance."""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


# ------------------------------------------------------------------ proposals
@router.post("/objects/propose", response_model=Result[SemanticObjectVO])
async def propose_object(
    request: ProposeRequest,
    service: Service = Depends(get_service),
) -> Result[SemanticObjectVO]:
    """Create a proposal (write rule 1: always lands in proposed)."""
    try:
        vo = service.propose(
            object_id=request.id,
            obj_type=request.obj_type,
            payload=request.payload,
            workspace_id=request.workspace_id,
            confidence=request.confidence,
            evidence=request.evidence,
            created_by=request.created_by,
            source=request.source,
        )
        return Result.succ(vo)
    except ValueError as e:
        return Result.failed(msg=str(e))


@router.post("/proposals/generate", response_model=Result[GenerateProposalsVO])
async def generate_proposals(
    request: GenerateProposalsRequest,
    service: Service = Depends(get_service),
) -> Result[GenerateProposalsVO]:
    """Generate semantic proposals -- workspace-level (agent) or per-datasource (batch).

    If the workspace has a ``proposal_agent_id`` configured (ECP settings), run
    that BAIZE proposal Agent over **all registered assets** of the workspace
    (assets passed as dynamic resources -> DBCapability injects db info + table
    list; Agent explores each via get_table_spec / sample_distinct_values /
    propose_semantic in its ReAct loop). Otherwise fall back to the batch
    proposer (``DbSemanticsProposer``) for a single datasource. All proposals
    land in ``proposed`` (confirmation gate unchanged).
    """
    try:
        cfg = service.get_workspace_config(request.workspace_id)
        agent_id = getattr(cfg, "proposal_agent_id", None) if cfg else None
    except Exception:  # noqa: BLE001
        agent_id = None

    if agent_id:
        from ..service.proposal_runner import run_proposal_agent

        result = await run_proposal_agent(
            system_app=service._system_app,
            app_code=agent_id,
            workspace_id=request.workspace_id,
            domain_hint=request.domain_hint,
        )
        return Result.succ(result)

    # Batch fallback: requires a datasource_id (per-asset).
    if not request.datasource_id:
        return Result.failed(
            msg="未配置提案 Agent 时需指定 datasource_id(单资产批处理);"
            "或在 ECP 设置配置提案 Agent 后做工作空间级生成"
        )

    from ..service.propose import DbSemanticsProposer

    proposer = DbSemanticsProposer(service)
    result = await proposer.generate(
        datasource_id=request.datasource_id,
        workspace_id=request.workspace_id,
        table_names=request.table_names,
        max_tables=request.max_tables,
        domain_hint=request.domain_hint,
    )
    return Result.succ(result)


# -------------------------------------------------------------------- inbox
@router.get("/inbox", response_model=Result[SemanticObjectListVO])
async def inbox(
    workspace_id: Optional[str] = Query(default=None),
    obj_type: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    service: Service = Depends(get_service),
) -> Result[SemanticObjectListVO]:
    """Confirmation inbox: latest proposed versions."""
    return Result.succ(
        service.inbox(
            workspace_id=workspace_id, obj_type=obj_type,
            page=page, page_size=page_size,
        )
    )


@router.post(
    "/objects/{object_id}/versions/{version}/confirm",
    response_model=Result[SemanticObjectVO],
)
async def confirm_object(
    object_id: str,
    version: int,
    request: ConfirmRequest,
    service: Service = Depends(get_service),
) -> Result[SemanticObjectVO]:
    """Confirm a proposed version (optionally with an edited payload)."""
    try:
        vo = service.confirm(
            object_id=object_id,
            version=version,
            user_id=request.user_id,
            workspace_id=request.workspace_id,
            edited_payload=request.edited_payload,
        )
        return Result.succ(vo)
    except (ValueError, PermissionError) as e:
        return Result.failed(msg=str(e))


@router.post(
    "/objects/{object_id}/versions/{version}/reject",
    response_model=Result[SemanticObjectVO],
)
async def reject_object(
    object_id: str,
    version: int,
    request: RejectRequest,
    service: Service = Depends(get_service),
) -> Result[SemanticObjectVO]:
    """Reject a proposed version."""
    try:
        vo = service.reject(
            object_id=object_id,
            version=version,
            user_id=request.user_id,
            workspace_id=request.workspace_id,
            reason=request.reason,
        )
        return Result.succ(vo)
    except (ValueError, PermissionError) as e:
        return Result.failed(msg=str(e))


@router.post("/objects/{object_id}/deprecate", response_model=Result[SemanticObjectVO])
async def deprecate_object(
    object_id: str,
    request: DeprecateRequest,
    service: Service = Depends(get_service),
) -> Result[SemanticObjectVO]:
    """Deprecate the confirmed version of an object."""
    try:
        vo = service.deprecate(
            object_id=object_id,
            user_id=request.user_id,
            workspace_id=request.workspace_id,
            reason=request.reason,
        )
        return Result.succ(vo)
    except (ValueError, PermissionError) as e:
        return Result.failed(msg=str(e))


# --------------------------------------------------------------------- reads
@router.get("/objects", response_model=Result[SemanticObjectListVO])
async def list_objects(
    workspace_id: Optional[str] = Query(default=None),
    obj_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    service: Service = Depends(get_service),
) -> Result[SemanticObjectListVO]:
    """Browse latest versions of semantic objects."""
    return Result.succ(
        service.list_objects(
            workspace_id=workspace_id,
            obj_type=obj_type,
            status=status,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/objects/{object_id}", response_model=Result[SemanticObjectVO])
async def get_object(
    object_id: str,
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[SemanticObjectVO]:
    vo = service.get_object(object_id, workspace_id=workspace_id)
    if not vo:
        return Result.failed(msg=f"Object {object_id} not found")
    return Result.succ(vo)


@router.get(
    "/objects/{object_id}/versions", response_model=Result[List[SemanticObjectVO]]
)
async def version_history(
    object_id: str,
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[SemanticObjectVO]]:
    return Result.succ(service.version_history(object_id, workspace_id=workspace_id))


@router.get("/catalog", response_model=Result[List[CatalogEntryVO]])
async def catalog(
    workspace_id: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[CatalogEntryVO]]:
    """Confirmed-only catalog (write rule 4) for prompt injection / search."""
    return Result.succ(service.catalog(workspace_id=workspace_id, keyword=keyword))


# --------------------------------------------------------------------- admin
@router.get("/admin/contract_check", response_model=Result[dict])
async def contract_check(
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[dict]:
    """扫描 confirmed 对象的 payload 契约合规性(只读)。

    不合规对象会让 execute_metric_query 门禁拒绝(PAYLOAD_INVALID)——
    "已确认但不可执行"问题的体检入口。
    """
    return Result.succ(service.contract_check(workspace_id=workspace_id))


@router.post("/admin/normalize", response_model=Result[dict])
async def normalize_confirmed(
    workspace_id: Optional[str] = Query(default=None),
    user_id: str = Query(default="system"),
    service: Service = Depends(get_service),
) -> Result[dict]:
    """一键修复不合规 confirmed 对象(契约归一化,写新版本)。

    走应用自己的 DAO/版本化写入(create_confirmed_version),不外部直改库——
    规避外部写 WAL 竞态导致的数据回退。normalize 无法补的(如缺 entity
    引用)列入 skipped,需人工编辑后走 confirm 流程。
    """
    return Result.succ(
        service.normalize_confirmed(workspace_id=workspace_id, user_id=user_id)
    )


@router.get("/admin/miss_report", response_model=Result[dict])
async def miss_report(
    workspace_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    service: Service = Depends(get_service),
) -> Result[dict]:
    """miss 聚类报告:execute_raw_sql 兜底记录按归一化 SQL 模式分组计数。

    "大家在裸查什么"的可见化——高频 miss 是语义目录最需要覆盖的真实问题,
    也是 learn_from_misses 的输入(召回飞轮的学习侧)。
    """
    return Result.succ(service.miss_report(workspace_id=workspace_id, limit=limit))


@router.post("/admin/learn_from_misses", response_model=Result[GenerateProposalsVO])
async def learn_from_misses(
    workspace_id: Optional[str] = Query(default=None),
    top: int = Query(default=10, ge=1, le=50),
    service: Service = Depends(get_service),
) -> Result[GenerateProposalsVO]:
    """从 miss 学习:高频未覆盖问题喂给提案 agent,生成的提案进收件箱。

    闭环:fallback miss(op_log)→ 聚类 → 提案 agent(带 miss 上下文)→
    提案进收件箱 → 人工 confirm → 目录覆盖增长 → 后续同类问题走可信路径。
    需要工作空间已配置 proposal_agent_id(ECP 设置)。
    """
    ws = workspace_id or None
    try:
        cfg = service.get_workspace_config(ws)
        agent_id = getattr(cfg, "proposal_agent_id", None) if cfg else None
    except Exception:  # noqa: BLE001
        agent_id = None
    if not agent_id:
        return Result.failed(
            msg="工作空间未配置提案 Agent(proposal_agent_id),"
            "请先在 ECP 设置中配置后再从 miss 学习"
        )

    report = service.miss_report(workspace_id=ws, limit=top)
    if not report["clusters"]:
        return Result.failed(msg="暂无 fallback miss 记录,无需学习")
    miss_context = Service.build_miss_context(report["clusters"], max_items=top)

    from ..service.proposal_runner import run_proposal_agent

    result = await run_proposal_agent(
        system_app=service._system_app,
        app_code=agent_id,
        workspace_id=ws,
        domain_hint=miss_context,
    )
    return Result.succ(result)


# ----------------------------------------------------------------- confirmers
@router.get("/confirmers", response_model=Result[List[ConfirmerVO]])
async def list_confirmers(
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[ConfirmerVO]]:
    return Result.succ(service.list_confirmers(workspace_id=workspace_id))


@router.post("/confirmers", response_model=Result[bool])
async def add_confirmer(
    request: ConfirmerCreateRequest,
    service: Service = Depends(get_service),
) -> Result[bool]:
    service.add_confirmer(
        user_id=request.user_id,
        workspace_id=request.workspace_id,
        scope=request.scope,
    )
    return Result.succ(True)


@router.delete("/confirmers/{confirmer_id}", response_model=Result[bool])
async def remove_confirmer(
    confirmer_id: int,
    service: Service = Depends(get_service),
) -> Result[bool]:
    return Result.succ(service.remove_confirmer(confirmer_id))


# -------------------------------------------------------------------- op log
@router.get("/op-log", response_model=Result[List[OpLogVO]])
async def op_log(
    workspace_id: Optional[str] = Query(default=None),
    op: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    service: Service = Depends(get_service),
) -> Result[List[OpLogVO]]:
    return Result.succ(
        service.list_op_log(
            workspace_id=workspace_id, op=op, page=page, page_size=page_size
        )
    )


# -------------------------------------------------------------- asset refs
@router.post("/assets", response_model=Result[AssetRefVO])
async def register_asset(
    request: AssetRefRegisterRequest,
    service: Service = Depends(get_service),
) -> Result[AssetRefVO]:
    """Register an original-asset reference (idempotent)."""
    try:
        return Result.succ(
            service.register_asset(
                kind=request.kind,
                ref_id=request.ref_id,
                workspace_id=request.workspace_id,
                ref_meta=request.ref_meta,
            )
        )
    except Exception as e:  # noqa: BLE001
        return Result.failed(msg=str(e))


@router.get("/assets", response_model=Result[List[AssetRefVO]])
async def list_assets(
    workspace_id: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[AssetRefVO]]:
    return Result.succ(service.list_assets(workspace_id=workspace_id, kind=kind))


@router.get("/readiness", response_model=Result[ReadinessVO])
async def readiness(
    datasource_id: int = Query(...),
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[ReadinessVO]:
    """Check whether a DB asset's material is complete for proposals."""
    return Result.succ(
        service.readiness(datasource_id, workspace_id=workspace_id)
    )


# --------------------------------------------------------------------- graph
@router.get("/graph", response_model=Result[GraphVO])
async def graph(
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[GraphVO]:
    """Semantic graph view (objects as nodes, materialized edges as links)."""
    return Result.succ(service.graph(workspace_id=workspace_id))


# --------------------------------------------------------------------- space
@router.post("/space", response_model=Result[SpaceInfoVO])
async def get_or_create_space(
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[SpaceInfoVO]:
    """Get-or-create the ECP soft-layer knowledge space (ecp-<workspace>)."""
    try:
        return Result.succ(await service.get_or_create_space(workspace_id))
    except Exception as e:  # noqa: BLE001
        return Result.failed(msg=str(e))


# -------------------------------------------------------- workspace config
@router.get("/workspace-config", response_model=Result[WorkspaceConfigVO])
async def get_workspace_config(
    workspace_id: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[WorkspaceConfigVO]:
    """Proposal-agent / domain settings of a workspace."""
    return Result.succ(service.get_workspace_config(workspace_id))


@router.put("/workspace-config", response_model=Result[WorkspaceConfigVO])
async def save_workspace_config(
    request: WorkspaceConfigUpdateRequest,
    service: Service = Depends(get_service),
) -> Result[WorkspaceConfigVO]:
    return Result.succ(
        service.save_workspace_config(
            workspace_id=request.workspace_id,
            proposal_agent_id=request.proposal_agent_id,
        )
    )


# ------------------------------------------------------------- linked resources
@router.get("/linked-resources")
async def get_linked_resources(
    workspace_id: Optional[str] = Query(default=None),
) -> Result[List[dict]]:
    """Return db assets registered in an ECP workspace, for auto-binding.

    When an Agent binds an ECP resource, the frontend calls this endpoint to
    discover which datasources the workspace's proposals were built on, and
    auto-adds them to resource_tool. Returns [{datasource_id, db_name, db_type}].
    """
    from ..config import DEFAULT_WORKSPACE_ID
    from ..models.models import AssetRefDao

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    try:
        assets = AssetRefDao().list(ws) or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp] list linked assets failed: {e}")
        return Result.succ([])

    result = []
    for a in assets:
        if a.kind != "db":
            continue
        try:
            ds_id = int(a.ref_id)
        except (TypeError, ValueError):
            continue
        db_name = (a.ref_meta or {}).get("db_name") or ""
        db_type = (a.ref_meta or {}).get("db_type") or ""
        if not db_name:
            # Fallback: resolve from ConnectConfigDao
            try:
                from derisk_serve.datasource.manages.connect_config_db import (
                    ConnectConfigDao,
                )

                cfg = ConnectConfigDao().get_one({"id": ds_id})
                db_name = getattr(cfg, "db_name", "") or ""
                db_type = getattr(cfg, "db_type", "") or ""
            except Exception:  # noqa: BLE001
                pass
        result.append(
            {"datasource_id": ds_id, "db_name": db_name, "db_type": db_type}
        )
    return Result.succ(result)


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints."""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
