"""Inbox subpackage - 个人待办统一收件箱(多源聚合)。"""
from .models import (
    INBOX_TABLE_NAME,
    SOURCE_ECP_PROPOSAL,
    SOURCE_INTERVENTION,
    SOURCE_MANUAL,
    SOURCE_TASK,
    STATUS_ARCHIVED,
    STATUS_DONE,
    STATUS_DOING,
    STATUS_UNREAD,
    VIS_PERSONAL,
    VIS_SHARED,
    InboxItemDao,
    InboxItemEntity,
)
from .schemas import (
    InboxItemResponse,
    InboxListFilter,
    InboxResolveRequest,
    InboxStatusUpdateRequest,
)
from .service import INBOX_SERVICE_COMPONENT_NAME, InboxService

__all__ = [
    "INBOX_TABLE_NAME",
    "INBOX_SERVICE_COMPONENT_NAME",
    "InboxItemEntity",
    "InboxItemDao",
    "InboxService",
    "InboxItemResponse",
    "InboxListFilter",
    "InboxResolveRequest",
    "InboxStatusUpdateRequest",
    "SOURCE_TASK",
    "SOURCE_INTERVENTION",
    "SOURCE_ECP_PROPOSAL",
    "SOURCE_MANUAL",
    "STATUS_UNREAD",
    "STATUS_DOING",
    "STATUS_DONE",
    "STATUS_ARCHIVED",
    "VIS_PERSONAL",
    "VIS_SHARED",
]
