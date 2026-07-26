"""Gpts Todos 数据库模型和 DAO.

独立表存储 BAIZE 目标任务 TODO list（claude-code 式 LLM 自维护进度）。
不复用 gpts_kanban 表，避免 todos 字段被 _from_kanban_data 丢弃 + 与 kanban
共用 (conv_id, session_id) 键互相覆盖的问题。
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    select,
)

from derisk.storage.metadata import BaseDao, Model


class GptsTodoEntity(Model):
    """Gpts 任务列表实体."""

    __tablename__ = "gpts_todos"
    __table_args__ = (Index("idx_todos_conv_session", "conv_id", "session_id"),)

    id = Column(Integer, primary_key=True, comment="autoincrement id")
    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation"
    )
    session_id = Column(
        String(255), nullable=False, comment="The session id within conversation"
    )
    agent_id = Column(
        String(255), nullable=False, default="todo", comment="The agent id"
    )
    todos = Column(
        Text(length=2**31 - 1), nullable=True, comment="Todos data (JSON array)"
    )
    created_at = Column(
        DateTime, name="gmt_create", default=datetime.utcnow, comment="create time"
    )
    updated_at = Column(
        DateTime,
        name="gmt_modified",
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time",
    )


class GptsTodoDao(BaseDao):
    """Gpts 任务列表 DAO."""

    async def save_todos_async(
        self, conv_id: str, session_id: str, agent_id: str, todos_data: list
    ) -> int:
        """异步保存或更新任务列表.

        Args:
            conv_id: 会话 ID
            session_id: Session ID
            agent_id: Agent ID
            todos_data: todo 列表（list[dict]）

        Returns:
            记录 ID
        """
        todos_json = json.dumps(todos_data, ensure_ascii=False)
        async with self.a_session(commit=True) as session:
            result = await session.execute(
                select(GptsTodoEntity).where(
                    GptsTodoEntity.conv_id == conv_id,
                    GptsTodoEntity.session_id == session_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.todos = todos_json
                await session.flush()
                return existing.id
            entity = GptsTodoEntity(
                conv_id=conv_id,
                session_id=session_id,
                agent_id=agent_id,
                todos=todos_json,
            )
            session.add(entity)
            await session.flush()
            return entity.id

    async def get_todos_async(
        self, conv_id: str, session_id: str
    ) -> Optional[list]:
        """异步获取任务列表.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            todo 列表（list[dict]）或 None
        """
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsTodoEntity).where(
                    GptsTodoEntity.conv_id == conv_id,
                    GptsTodoEntity.session_id == session_id,
                )
            )
            entity = result.scalar_one_or_none()
            if not entity or not entity.todos:
                return None
            return json.loads(entity.todos)

    async def delete_todos_async(self, conv_id: str, session_id: str) -> bool:
        """异步删除任务列表.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            是否成功
        """
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsTodoEntity.__table__.delete().where(
                    GptsTodoEntity.conv_id == conv_id,
                    GptsTodoEntity.session_id == session_id,
                )
            )
        return True
