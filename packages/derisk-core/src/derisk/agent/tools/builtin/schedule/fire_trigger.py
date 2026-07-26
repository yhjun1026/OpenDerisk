"""
FireTrigger Tool - 触发器触发工具

触发一个 TriggerSource，执行其绑定的 playbook + instruction（创建 Task 并 detached 运行）。
等价于 cron 的 triggerFire payload 执行体（TriggerService.fire）。
"""

import logging
from typing import Any, Dict, Optional

from ...base import ToolBase, ToolCategory, ToolRiskLevel
from ...metadata import ToolMetadata
from ...result import ToolResult

logger = logging.getLogger(__name__)


class FireTriggerTool(ToolBase):
    """触发器触发工具 - 触发一个 TriggerSource 执行其剧本。"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="fire_trigger",
            display_name="Fire Trigger",
            description="""Fire a TriggerSource to run its bound playbook + instruction.

This creates a Task from the trigger's configured playbook and instruction,
then runs it (detached). Equivalent to the cron 'triggerFire' payload path.

Use this when you want to launch a full playbook (with artifact/delivery/task
lifecycle) rather than just sending a single message to an Agent.
""",
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.MEDIUM,
            requires_permission=True,
            tags=["trigger", "playbook", "task"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "trigger_id": {
                    "type": "integer",
                    "description": "The TriggerSource ID to fire.",
                },
                "workspace_id": {
                    "type": "integer",
                    "description": "Workspace ID that owns the trigger (context passthrough).",
                },
            },
            "required": ["trigger_id", "workspace_id"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[Any] = None
    ) -> ToolResult:
        """触发一个 TriggerSource。"""
        try:
            trigger_id = args.get("trigger_id")
            workspace_id = args.get("workspace_id")
            if trigger_id is None or workspace_id is None:
                return ToolResult.fail(
                    error="Missing required parameters: trigger_id or workspace_id",
                    tool_name=self.name,
                )

            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            if not system_app:
                return ToolResult.fail(
                    error="SystemApp not initialized", tool_name=self.name
                )

            from derisk_serve.trigger.api.schemas import TriggerFireRequest
            from derisk_serve.trigger.service.service import (
                TRIGGER_SERVICE_COMPONENT_NAME,
                TriggerService,
            )

            trigger_service: TriggerService = system_app.get_component(
                TRIGGER_SERVICE_COMPONENT_NAME, TriggerService,
            )
            trigger_service.fire(
                TriggerFireRequest(
                    workspace_id=workspace_id,
                    trigger_id=trigger_id,
                    payload={},
                )
            )

            logger.info(f"[FireTriggerTool] Fired trigger {trigger_id}")
            return ToolResult.ok(
                output=f"Trigger {trigger_id} fired (workspace={workspace_id}).",
                tool_name=self.name,
                metadata={
                    "trigger_id": trigger_id,
                    "workspace_id": workspace_id,
                },
            )
        except Exception as e:
            logger.error(f"[FireTriggerTool] Failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)
