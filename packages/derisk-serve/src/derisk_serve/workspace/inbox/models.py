"""InboxItem entity + DAO - 个人待办统一收件箱。

待办 = "需要我干预才能推进"的阻塞事件收件箱项,多源聚合:
  - task(别人转交/指派给我的任务)
  - intervention(agent 请求人介入/确认)
  - ecp_proposal(ECP 提案待确认)
  - manual(用户手动加的待办)

InboxItem 是索引/指针:业务状态回指原实体,这里只管收件箱视角
(未读/处理中/已处理) + 指针 + 收件人。不双写业务状态。

两种可见性:
  - personal:进一个人待办(转交),完成时按 user_id 精确消除
  - shared:进多人待办(Intervention/ECP 提案),一人完成按 source_id 批量消除
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    desc,
)

from derisk.storage.metadata import BaseDao, Model

from ..config import SERVER_APP_TABLE_NAME

INBOX_TABLE_NAME = f"{SERVER_APP_TABLE_NAME}_inbox_item"

# 收件箱状态
STATUS_UNREAD = "unread"
STATUS_DOING = "doing"
STATUS_DONE = "done"
STATUS_ARCHIVED = "archived"

# 可见性
VIS_PERSONAL = "personal"
VIS_SHARED = "shared"

# 来源类型
SOURCE_TASK = "task"
SOURCE_INTERVENTION = "intervention"
SOURCE_ECP_PROPOSAL = "ecp_proposal"
SOURCE_MANUAL = "manual"


class InboxItemEntity(Model):
    __tablename__ = INBOX_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True, comment="收件人(谁的待办)")
    source_type = Column(String(32), nullable=False, comment="task/intervention/ecp_proposal/manual")
    source_id = Column(String(128), nullable=False, index=True, comment="原实体 id(指针)")
    title = Column(String(256), nullable=False)
    summary = Column(Text, nullable=True)
    inbox_status = Column(
        String(32), nullable=False, default=STATUS_UNREAD, index=True,
        comment="unread/doing/done/archived",
    )
    visibility = Column(
        String(16), nullable=False, default=VIS_PERSONAL,
        comment="personal/shared - 决定完成时是否批量消除",
    )
    created_at = Column(DateTime, default=datetime.now)
    resolved_at = Column(DateTime, nullable=True)

    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_inbox_user_status", "user_id", "inbox_status"),
    )


class InboxItemDao(
    BaseDao[
        InboxItemEntity,
        Dict[str, Any],
        Dict[str, Any],
    ]
):
    """DAO for InboxItem - uses raw session, mirrors WorkspaceConversationLinkDao."""

    def from_request(self, request):
        raise NotImplementedError

    def to_request(self, entity):
        raise NotImplementedError

    def to_response(self, entity) -> Dict[str, Any]:
        return {
            "id": entity.id,
            "workspace_id": entity.workspace_id,
            "user_id": entity.user_id,
            "source_type": entity.source_type,
            "source_id": entity.source_id,
            "title": entity.title,
            "summary": entity.summary,
            "inbox_status": entity.inbox_status,
            "visibility": entity.visibility,
            "created_at": entity.created_at.isoformat() if entity.created_at else "",
            "resolved_at": entity.resolved_at.isoformat() if entity.resolved_at else "",
            "gmt_created": entity.gmt_created.isoformat() if entity.gmt_created else "",
            "gmt_modified": entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        }

    def create_item(
        self,
        workspace_id: int,
        user_id: int,
        source_type: str,
        source_id: str,
        title: str,
        summary: Optional[str] = None,
        visibility: str = VIS_PERSONAL,
        status: str = STATUS_UNREAD,
    ) -> InboxItemEntity:
        session = self.get_raw_session()
        try:
            entity = InboxItemEntity(
                workspace_id=workspace_id,
                user_id=user_id,
                source_type=source_type,
                source_id=str(source_id),
                title=title,
                summary=summary,
                inbox_status=status,
                visibility=visibility,
            )
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def resolve_by_source(
        self,
        source_type: str,
        source_id: str,
        user_id: Optional[int] = None,
    ) -> int:
        """标记完成。shared 按 source_id 批量;personal 传 user_id 精确消除。

        返回受影响行数。
        """
        session = self.get_raw_session()
        try:
            q = session.query(InboxItemEntity).filter(
                InboxItemEntity.source_type == source_type,
                InboxItemEntity.source_id == str(source_id),
                InboxItemEntity.inbox_status != STATUS_DONE,
            )
            if user_id is not None:
                q = q.filter(InboxItemEntity.user_id == user_id)
            count = q.update(
                {
                    InboxItemEntity.inbox_status: STATUS_DONE,
                    InboxItemEntity.resolved_at: datetime.now(),
                },
                synchronize_session=False,
            )
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_status(
        self, item_id: int, user_id: int, new_status: str
    ) -> Optional[InboxItemEntity]:
        """用户手动推进待办状态(接手/完成/归档)。仅限自己的待办。"""
        session = self.get_raw_session()
        try:
            entity = (
                session.query(InboxItemEntity)
                .filter(
                    InboxItemEntity.id == item_id,
                    InboxItemEntity.user_id == user_id,
                )
                .first()
            )
            if not entity:
                return None
            entity.inbox_status = new_status
            if new_status == STATUS_DONE:
                entity.resolved_at = datetime.now()
            session.commit()
            session.refresh(entity)
            return entity
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_by_workspace_source(
        self, workspace_id: int, source_type: str
    ) -> List[InboxItemEntity]:
        """某空间某来源的全部待办(任意状态,含 done/archived),供对账 diff。"""
        session = self.get_raw_session()
        try:
            return (
                session.query(InboxItemEntity)
                .filter(
                    InboxItemEntity.workspace_id == workspace_id,
                    InboxItemEntity.source_type == source_type,
                )
                .all()
            )
        finally:
            session.close()

    def list_by_user(
        self,
        workspace_id: int,
        user_id: int,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[InboxItemEntity]:
        session = self.get_raw_session()
        try:
            q = session.query(InboxItemEntity).filter(
                InboxItemEntity.workspace_id == workspace_id,
                InboxItemEntity.user_id == user_id,
            )
            if status:
                q = q.filter(InboxItemEntity.inbox_status == status)
            else:
                # 默认只返回活跃待办(unread/doing);done/archived 是历史,需显式传 status 查
                q = q.filter(
                    InboxItemEntity.inbox_status.in_([STATUS_UNREAD, STATUS_DOING])
                )
            if source_type:
                q = q.filter(InboxItemEntity.source_type == source_type)
            return (
                q.order_by(desc(InboxItemEntity.gmt_modified)).limit(limit).all()
            )
        finally:
            session.close()
