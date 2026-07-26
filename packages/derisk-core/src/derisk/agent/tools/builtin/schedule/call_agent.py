"""
CallAgent Tool - 调用 Agent 工具

给指定 Agent 发起一次对话（发一条 message）。
- session_mode='isolated': 每次新建会话
- session_mode='shared': 复用 conv_session_id 指定的会话（需调用方提供）

本工具为 fire-and-forget：发起后立即返回 conv_id，不等 Agent 跑完。
等价于 cron 的 agentTurn payload 执行体（multi_agents.app_chat_v3）。
"""

import logging
import uuid
from typing import Any, Dict, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


class CallAgentTool(ToolBase):
    """调用 Agent 工具 - 给指定 Agent 发起一次对话。"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="call_agent",
            display_name="Call Agent",
            description="""Send a message to an Agent to start or continue a conversation.

This tool initiates an Agent turn by sending a message. It is fire-and-forget:
it returns the conversation ID immediately and does NOT wait for the Agent to finish.

Session modes:
- 'isolated': Create a new conversation each call (default)
- 'shared': Reuse an existing conversation via conv_session_id

Note: In 'shared' mode the caller must provide conv_session_id. This tool does
NOT auto-persist the session id back to a cron job (that is handled by the
agentTurn payload path). If conv_session_id is omitted in shared mode, a new
conversation is created each time (degrades to isolated behavior).

Examples:
1. New task to an Agent: agent_id='data_analyst', message='Run the daily report', session_mode='isolated'
2. Follow up a conversation: agent_id='data_analyst', message='Summarize the findings', session_mode='shared', conv_session_id='conv_xxx'
""",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["agent", "call", "conversation"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The Agent ID (app code) to send the message to.",
                },
                "message": {
                    "type": "string",
                    "description": "The instruction/message to send to the Agent.",
                },
                "session_mode": {
                    "type": "string",
                    "enum": ["isolated", "shared"],
                    "default": "isolated",
                    "description": "'isolated' creates a new conversation each call; 'shared' reuses conv_session_id.",
                },
                "conv_session_id": {
                    "type": "string",
                    "description": "Conversation session ID to reuse in 'shared' mode. Required for shared mode to actually reuse a session.",
                },
            },
            "required": ["agent_id", "message"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """给 Agent 发起一次对话。"""
        try:
            agent_id = args.get("agent_id")
            message = args.get("message")
            if not agent_id or not message:
                return ToolResult.fail(
                    error="Missing required parameters: agent_id or message",
                    tool_name=self.name,
                )

            session_mode = args.get("session_mode", "isolated")
            conv_session_id = args.get("conv_session_id")

            from derisk.cron import SessionMode

            try:
                session_mode_enum = SessionMode(session_mode)
            except ValueError:
                session_mode_enum = SessionMode.ISOLATED

            # Determine conversation ID
            if session_mode_enum == SessionMode.SHARED and conv_session_id:
                conv_uid = conv_session_id
            else:
                conv_uid = str(uuid.uuid4())

            # Import here to avoid circular dependencies
            from derisk_serve.agent.agents.controller import multi_agents

            result, agent_conv_id = await multi_agents.app_chat_v3(
                conv_uid=conv_uid,
                gpts_name=agent_id,
                user_query=message,
                stream=False,
                background_tasks=None,
            )

            # SHARED mode: persist conv_session_id back to the cron job so
            # subsequent runs reuse the same conversation (mirrors the
            # agentTurn payload path in service._execute_agent_turn).
            if session_mode_enum == SessionMode.SHARED and agent_conv_id:
                await self._maybe_persist_session_id(context, agent_conv_id)

            logger.info(
                f"[CallAgentTool] Agent turn initiated: agent={agent_id}, conv_uid={conv_uid}"
            )
            return ToolResult.ok(
                output=f"Agent '{agent_id}' turn initiated (conv_uid={conv_uid}). Running in background.",
                tool_name=self.name,
                metadata={
                    "conv_uid": conv_uid,
                    "agent_conv_id": agent_conv_id,
                    "session_mode": session_mode,
                },
            )
        except Exception as e:
            logger.error(f"[CallAgentTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)

    async def _maybe_persist_session_id(
        self, context: Optional[Any], agent_conv_id: str
    ) -> None:
        """Persist conv_session_id back to the cron job (SHARED mode only).

        Reads cron_job_id from context.config (injected by _execute_tool_call).
        No-op when called outside a cron job context (e.g. interactive Agent use).
        """
        try:
            job_id = None
            if context is not None and hasattr(context, "config"):
                job_id = context.config.get("cron_job_id")
            if not job_id:
                return  # not running under a cron job

            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                return
            from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
            from derisk_serve.cron.models.models import CronJobEntity
            from derisk_serve.cron.service.service import (
                Service,
                session_id_by_conv_id,
            )

            service = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
            conv_session_id = session_id_by_conv_id(agent_conv_id)
            with service.dao.session() as session:
                entity = (
                    session.query(CronJobEntity)
                    .filter(CronJobEntity.id == job_id)
                    .first()
                )
                if entity and entity.conv_session_id != conv_session_id:
                    entity.conv_session_id = conv_session_id
                    session.commit()
                    logger.info(
                        f"[CallAgentTool] Updated conv_session_id for job {job_id} to {conv_session_id}"
                    )
        except Exception as e:
            logger.debug(f"[CallAgentTool] persist session_id skipped: {e}")
