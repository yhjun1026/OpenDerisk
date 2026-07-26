"""
SubAgentBoard 可视化组件
用于在主会话顶部固定面板展示 BAIZE 派发的异步子任务实时状态。

设计理念：
- 仿 VisTodoList 的独立面板组件模式（全量重写、状态高亮、完成折叠）
- 卡片列表展示每个子 agent 的 agent_name / task / status
- 待授权状态（awaiting_authorization）单独高亮，提示用户介入
- 前端点击卡片 -> 右面板打开子会话实时流（轮询 queryChatStatus）
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List
from enum import Enum

from pydantic_core._pydantic_core import ValidationError
from derisk._private.pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class SubagentBoardStatus(str, Enum):
    """子任务展示状态枚举（比 core SubAgentStatus 多一个待授权态）。"""
    PENDING = "pending"                  # 已创建未开始
    RUNNING = "running"                  # 运行中
    DONE = "done"                        # 成功完成
    FAILED = "failed"                    # 失败
    AWAITING_AUTHORIZATION = "awaiting_authorization"  # 待用户授权


class SubagentItem(BaseModel):
    """子任务卡片项。"""
    sub_conv_id: str = Field(..., description="子 agent 会话 ID（点击打开子会话用）")
    agent_name: Optional[str] = Field(None, description="子 Agent 名（展示用）")
    task: Optional[str] = Field(None, description="任务指令摘要（展示用）")
    status: SubagentBoardStatus = Field(
        SubagentBoardStatus.RUNNING, description="子任务状态"
    )
    mode: str = Field("async", description="执行模式 sync|async")
    authorization: Optional[str] = Field(
        None, description="待授权问题文本（非空时 status 应为 awaiting_authorization）"
    )

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        if isinstance(v, str):
            try:
                return SubagentBoardStatus(v.lower())
            except ValueError:
                logger.warning(f"Invalid subagent status '{v}', defaulting to RUNNING")
                return SubagentBoardStatus.RUNNING
        return v


class SubagentBoardContent(DrskVisBase):
    """SubagentBoard 内容。"""
    items: List[SubagentItem] = Field(default_factory=list, description="子任务卡片列表")
    total_count: int = Field(0, description="子任务总数", ge=0)
    completed_count: int = Field(0, description="已完成（含失败）数", ge=0)


class SubagentBoard(Vis):
    """SubAgentBoard 可视化组件 - 子任务实时状态面板。"""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """生成 vis 协议所需的参数。"""
        content = kwargs["content"]
        try:
            SubagentBoardContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"SubagentBoard 可视化组件收到了非法的数据内容，可能导致显示失败！{content}，错误: {e}"
            )
            return content
        except Exception as e:
            logger.exception(f"SubagentBoard 组件验证异常: {e}")
            return content

    @classmethod
    def vis_tag(cls):
        """Vis 标签名称。"""
        return "d-subagent-board"
