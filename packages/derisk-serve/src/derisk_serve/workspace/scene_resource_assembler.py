"""SceneResourceAssembler — 场景空间业务:对话前按 lobby/workbench 装配资源。

agent 代码不感知;由 chat_completions 端点预处理层调用。产出 List[AgentResource],
并进 ext_info["dynamic_resources"],由标准 build_pack 消费。

装配规则:
- lobby(task_id 为空) -> [WorkspaceSceneResource AgentResource]
- workbench 有 playbook_id -> [PlaybookResource AgentResource(完整 config)]
- workbench 无 playbook_id -> []
- 缺 workspace / 缺 task / 缺 playbook -> []
- 任何异常 -> [](装配器永不把异常抛入 chat 路径)
"""
import logging
from typing import List, Optional

from derisk.agent.resource.base import AgentResource
from derisk_serve.playbook.resource.playbook_resource import (
    PlaybookConfig, PlaybookResource,
)
from derisk_serve.workspace.scene_resource import (
    WorkspaceSceneConfig, WorkspaceSceneResource,
)

logger = logging.getLogger(__name__)

# 真实组件名常量(与 workspace/service/service.py:WORKSPACE_SERVICE_COMPONENT_NAME、
# task/service/service.py:TASK_SERVICE_COMPONENT_NAME、
# playbook/service/service.py:PLAYBOOK_SERVICE_COMPONENT_NAME 对齐)。
_WORKSPACE = "serve_workspace_service"
_TASK = "serve_task_service"
_PLAYBOOK = "serve_playbook_service"


class SceneResourceAssembler:
    """场景资源装配器:chat 前预处理,产出 List[AgentResource]。

    永不抛异常:任何装配失败都降级为 [],由调用方(端点预处理)原样写
    ext_info["dynamic_resources"];绝不阻塞对话链路。
    """

    @staticmethod
    def assemble(system_app, workspace_id: int,
                 task_id: Optional[int], conv_uid: str) -> List[AgentResource]:
        try:
            if task_id:
                return SceneResourceAssembler._assemble_workbench(
                    system_app, workspace_id, task_id,
                )
            return SceneResourceAssembler._assemble_lobby(
                system_app, workspace_id, conv_uid,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"SceneResourceAssembler failed: {e}", exc_info=True)
            return []

    @staticmethod
    def _assemble_lobby(system_app, workspace_id, conv_uid):
        # Coerce workspace_name to str defensively; production Workspace.name
        # is already str, so this is a no-op there and protects the JSON
        # serializer in to_agent_resource against unexpected object types.
        ws_service = system_app.get_component(_WORKSPACE, None)
        ws = ws_service.get_by_id(workspace_id) if ws_service else None
        if not ws:
            return []
        config = WorkspaceSceneConfig(
            workspace_id=workspace_id, conv_uid=conv_uid,
            workspace_name=str(getattr(ws, "name", "") or ""),
        )
        return [WorkspaceSceneResource.to_agent_resource(config)]

    @staticmethod
    def _assemble_workbench(system_app, workspace_id, task_id):
        task_service = system_app.get_component(_TASK, None)
        task = task_service.get_by_id(task_id) if task_service else None
        if not task or not task.playbook_id:
            return []
        playbook_service = system_app.get_component(_PLAYBOOK, None)
        pb = playbook_service.get_by_id(task.playbook_id) if playbook_service else None
        if not pb:
            return []
        config = PlaybookConfig.from_playbook_response(pb)
        return [PlaybookResource.to_agent_resource(config)]
