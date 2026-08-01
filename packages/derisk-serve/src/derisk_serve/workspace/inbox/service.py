"""Inbox service: 个人待办统一收件箱,多源聚合 + 事件驱动产生/消除。

各来源在阻塞事件发生时调 create_item;原实体状态变更(任务完成/介入审批/
提案确认)时调 resolve。InboxItem 只管收件箱视角,业务状态回指原实体。
"""
import logging
from typing import List, Optional

from derisk.component import SystemApp
from derisk_serve.core import BaseService

from ..config import ServeConfig
from ..event_bus import emit_workspace_event
from .models import (
    INBOX_TABLE_NAME,
    VIS_PERSONAL,
    VIS_SHARED,
    InboxItemDao,
    InboxItemEntity,
)
from .schemas import InboxItemResponse, InboxListFilter

INBOX_SERVICE_COMPONENT_NAME = "serve_workspace_inbox_service"

logger = logging.getLogger(__name__)


class InboxService(BaseService[InboxItemEntity, dict, dict]):
    """个人待办收件箱服务。"""

    name = INBOX_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[InboxItemDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: InboxItemDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or InboxItemDao()
        self._system_app = system_app

    @property
    def dao(self) -> InboxItemDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def _to_response(self, entity: InboxItemEntity) -> InboxItemResponse:
        return InboxItemResponse(**self._dao.to_response(entity))

    # ---------------- 产生(事件驱动) ----------------
    def create_item(
        self,
        workspace_id: int,
        user_id: int,
        source_type: str,
        source_id,
        title: str,
        summary: Optional[str] = None,
        visibility: str = VIS_PERSONAL,
    ) -> InboxItemResponse:
        """阻塞事件发生时写一条待办。"""
        entity = self._dao.create_item(
            workspace_id=workspace_id,
            user_id=user_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            summary=summary,
            visibility=visibility,
        )
        self._emit(workspace_id, "inbox_created", {
            "user_id": user_id,
            "source_type": source_type,
            "source_id": str(source_id),
            "title": title,
            "visibility": visibility,
        })
        return self._to_response(entity)

    def create_for_users(
        self,
        workspace_id: int,
        user_ids: List[int],
        source_type: str,
        source_id,
        title: str,
        summary: Optional[str] = None,
        visibility: str = VIS_SHARED,
    ) -> List[InboxItemResponse]:
        """共享待办:给每个相关人各写一条(如 ECP 提案给所有 confirmer)。"""
        items = []
        for uid in user_ids:
            try:
                items.append(
                    self.create_item(
                        workspace_id=workspace_id,
                        user_id=uid,
                        source_type=source_type,
                        source_id=source_id,
                        title=title,
                        summary=summary,
                        visibility=visibility,
                    )
                )
            except Exception as e:
                logger.warning(
                    f"create inbox item for user {uid} failed: {e}"
                )
        return items

    # ---------------- 消除(事件驱动) ----------------
    def resolve(
        self,
        workspace_id: int,
        source_type: str,
        source_id,
        user_id: Optional[int] = None,
    ) -> int:
        """原实体完成时标记待办 done。

        shared 待办(不传 user_id)按 source_id 批量消除所有相关人的待办;
        personal 待办传 user_id 精确消除。
        """
        count = self._dao.resolve_by_source(source_type, source_id, user_id)
        self._emit(workspace_id, "inbox_resolved", {
            "source_type": source_type,
            "source_id": str(source_id),
            "user_id": user_id,
            "count": count,
        })
        return count

    # ---------------- 用户手动操作 ----------------
    def update_status(
        self, item_id: int, user_id: int, new_status: str
    ) -> Optional[InboxItemResponse]:
        """用户手动推进自己的待办(接手/完成/归档)。"""
        entity = self._dao.update_status(item_id, user_id, new_status)
        return self._to_response(entity) if entity else None

    def list_inbox(self, f: InboxListFilter) -> List[InboxItemResponse]:
        # 读时惰性对账:关联 ECP 工作区的待审批提案 ↔ 空间共享待办
        try:
            from .ecp_sync import sync_ecp_proposals

            sync_ecp_proposals(f.workspace_id)
        except Exception as e:
            logger.warning(f"ecp proposal sync failed: {e}")
        entities = self._dao.list_by_user(
            f.workspace_id, f.user_id, f.status, f.source_type, f.limit
        )
        return [self._to_response(e) for e in entities]

    # ---------------- 内部 ----------------
    def _emit(self, workspace_id: int, event_type: str, payload: dict) -> None:
        try:
            emit_workspace_event(workspace_id, event_type, payload)
        except Exception as e:
            logger.warning(f"emit workspace event {event_type} failed: {e}")
