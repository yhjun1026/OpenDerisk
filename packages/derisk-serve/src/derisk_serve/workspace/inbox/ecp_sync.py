"""ECP 待审批提案 → 空间待办 的读时惰性对账。

关联定义(双来源,去重合并):
1. 派生:每个场景空间天然关联专属 ECP 工作区 ``ecp_<workspace_code>``
   (见 workspace/ecp_derive.py;场景 agent 运行时装配器自动注入该绑定)。
2. 显式:空间默认 Agent(default_agent_app_code)的 resources 里绑了
   type="ecp" 资源(value 含 ECP workspace_id)——覆盖用户换绑自定义 app
   或显式绑定 default 共享库的场景。

对账语义镜像 ECP 确认收件箱("对象最新版本为 proposed 即待审批",
SemanticObjectDao.list_latest):
  - 补:待审批提案 × 空间全体成员,缺失则补一条 shared 待办
    (已 done 的不重建——同一提案不骚扰;新提案版本 source_id 不同会产生新待办)
  - 消:活跃 ecp_proposal 待办的 source_id 不在期望集中则批量消除
    (覆盖确认/驳回/被新版本取代/关联被移除)

全程 best-effort:单步失败 log.warning 不中断,ECP 侧不可用时 inbox 照常工作。
"""
import json
import logging
from typing import Dict, List, Tuple

from ..models.models import (
    WorkspaceEntity,
    WorkspaceDao,
    WorkspaceMemberDao,
)
from .models import (
    SOURCE_ECP_PROPOSAL,
    STATUS_DOING,
    STATUS_UNREAD,
    VIS_SHARED,
    InboxItemDao,
)

logger = logging.getLogger(__name__)

# 单次对账拉取的提案上限(超出部分记日志,下轮再补)
_PROPOSAL_PAGE_SIZE = 500


def _extract_ecp_workspace_ids(resources_json: str) -> List[str]:
    """从 app detail 的 resources JSON 里取 ecp 资源的 workspace_id。

    value 可能是 dict 或 JSON 字符串(参考 EcpResourceParameters.from_dict
    的兼容处理)。
    """
    ws_ids: List[str] = []
    try:
        items = json.loads(resources_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return ws_ids
    if not isinstance(items, list):
        return ws_ids
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "ecp":
            continue
        value = item.get("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                value = {}
        if isinstance(value, dict):
            ws = value.get("workspace_id")
            if ws:
                ws_ids.append(str(ws))
    return ws_ids


def resolve_ecp_workspaces(workspace_id: int) -> List[str]:
    """解析空间关联的 ECP 工作区 id 列表(派生优先 + 显式绑定,去重)。

    无空间记录返回 [];有空间但无显式绑定时至少返回派生工作区。
    """
    from ..ecp_derive import derived_ecp_workspace_id

    session = WorkspaceDao().get_raw_session()
    try:
        ws = (
            session.query(WorkspaceEntity)
            .filter(WorkspaceEntity.id == workspace_id)
            .first()
        )
        if not ws:
            return []
        # 派生工作区必在首位:场景 agent 运行时装配器自动绑定,提案必落于此
        ws_ids: List[str] = [derived_ecp_workspace_id(ws.workspace_code)]
        app_code = ws.default_agent_app_code
    finally:
        session.close()

    if not app_code:
        return ws_ids

    from derisk_serve.building.app.models.models_details import (
        AppDetailServeDao,
        AppDetailServeEntity,
    )

    # 一个 app 可能多行 detail(team 模式),全部扫描
    session = AppDetailServeDao().get_raw_session()
    try:
        rows = (
            session.query(AppDetailServeEntity)
            .filter(AppDetailServeEntity.app_code == app_code)
            .all()
        )
        for row in rows:
            for ws_id in _extract_ecp_workspace_ids(row.resources):
                if ws_id not in ws_ids:
                    ws_ids.append(ws_id)
        return ws_ids
    finally:
        session.close()


def _desired_proposals(ecp_ws_list: List[str]) -> Dict[str, Tuple[str, str]]:
    """期望待办集:source_id -> (title, summary)。"""
    from derisk_serve.ecp.config import STATUS_PROPOSED
    from derisk_serve.ecp.models.models import SemanticObjectDao

    desired: Dict[str, Tuple[str, str]] = {}
    dao = SemanticObjectDao()
    for ecp_ws in ecp_ws_list:
        try:
            result = dao.list_latest(
                workspace_id=ecp_ws,
                status=STATUS_PROPOSED,
                page=1,
                page_size=_PROPOSAL_PAGE_SIZE,
            )
        except Exception as e:
            logger.warning(
                f"[ecp_sync] list proposals failed (ecp_ws={ecp_ws}): {e}"
            )
            continue
        if result.total_count > len(result.items):
            logger.warning(
                f"[ecp_sync] proposals truncated: ecp_ws={ecp_ws} "
                f"total={result.total_count} fetched={len(result.items)}"
            )
        for item in result.items:
            source_id = f"{ecp_ws}:{item.id}@v{item.version}"
            title = f"ECP 提案待确认:{item.name or item.id}"
            summary = (
                f"类型 {item.obj_type} | ECP 工作区 {ecp_ws} | "
                f"版本 v{item.version} | 来源 {item.created_by}"
            )
            desired[source_id] = (title, summary)
    return desired


def _member_user_ids(workspace_id: int) -> List[int]:
    """空间全体成员 user_id,兜底补 owner。"""
    user_ids: List[int] = []
    for m in WorkspaceMemberDao().list_by_workspace(workspace_id):
        if m.user_id not in user_ids:
            user_ids.append(m.user_id)
    session = WorkspaceDao().get_raw_session()
    try:
        ws = (
            session.query(WorkspaceEntity)
            .filter(WorkspaceEntity.id == workspace_id)
            .first()
        )
        if ws and ws.owner_user_id is not None and ws.owner_user_id not in user_ids:
            user_ids.append(ws.owner_user_id)
    finally:
        session.close()
    return user_ids


def sync_ecp_proposals(workspace_id: int) -> dict:
    """对账一次,返回 {"created": n, "resolved": n} 统计。异常不抛出。"""
    stats = {"created": 0, "resolved": 0}
    try:
        ecp_ws_list = resolve_ecp_workspaces(workspace_id)
        desired = _desired_proposals(ecp_ws_list)
        user_ids = _member_user_ids(workspace_id)
        dao = InboxItemDao()
        existing = dao.list_by_workspace_source(workspace_id, SOURCE_ECP_PROPOSAL)

        # 补:(source_id, user_id) 任意状态已存在则跳过(手动 done 不重建)
        existing_keys = {(e.source_id, e.user_id) for e in existing}
        for source_id, (title, summary) in desired.items():
            for uid in user_ids:
                if (source_id, uid) in existing_keys:
                    continue
                try:
                    dao.create_item(
                        workspace_id=workspace_id,
                        user_id=uid,
                        source_type=SOURCE_ECP_PROPOSAL,
                        source_id=source_id,
                        title=title,
                        summary=summary,
                        visibility=VIS_SHARED,
                    )
                    stats["created"] += 1
                except Exception as e:
                    logger.warning(
                        f"[ecp_sync] create item failed "
                        f"(ws={workspace_id}, source={source_id}, user={uid}): {e}"
                    )

        # 消:活跃待办的 source_id 不在期望集 → 按 source_id 批量消除
        stale_source_ids = {
            e.source_id
            for e in existing
            if e.inbox_status in (STATUS_UNREAD, STATUS_DOING)
            and e.source_id not in desired
        }
        for source_id in stale_source_ids:
            try:
                dao.resolve_by_source(SOURCE_ECP_PROPOSAL, source_id)
                stats["resolved"] += 1
            except Exception as e:
                logger.warning(
                    f"[ecp_sync] resolve failed (source={source_id}): {e}"
                )
    except Exception as e:
        logger.warning(f"[ecp_sync] sync failed (ws={workspace_id}): {e}")
    return stats
