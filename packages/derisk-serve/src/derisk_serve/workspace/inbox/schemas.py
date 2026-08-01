"""Inbox API schemas."""
from typing import Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class InboxItemResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    source_type: str
    source_id: str
    title: str
    summary: Optional[str] = None
    inbox_status: str
    visibility: str
    created_at: str
    resolved_at: Optional[str] = None
    gmt_created: str
    gmt_modified: str

    model_config = ConfigDict(
        title=f"InboxItemResponse for {SERVE_APP_NAME_HUMP}",
        from_attributes=True,
    )


class InboxListFilter(BaseModel):
    """待办列表过滤 - 按收件人 user_id 拉取个人待办。"""

    workspace_id: int
    user_id: int = Field(..., description="收件人 user id(我)")
    status: Optional[str] = Field(None, description="unread/doing/done/archived")
    source_type: Optional[str] = Field(
        None, description="task/intervention/ecp_proposal/manual"
    )
    limit: int = 100


class InboxResolveRequest(BaseModel):
    """标记待办完成(shared 按 source_id 批量消除)。"""

    source_type: str
    source_id: str
    user_id: Optional[int] = Field(
        None, description="personal 待办精确消除;不传则按 source_id 批量"
    )


class InboxStatusUpdateRequest(BaseModel):
    """用户手动推进待办状态(接手/完成/归档)。"""

    new_status: str = Field(..., description="unread/doing/done/archived")
