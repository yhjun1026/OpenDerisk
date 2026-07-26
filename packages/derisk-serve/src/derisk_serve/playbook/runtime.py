"""Playbook runtime — executes a Task by driving the workspace Agent in the task's
conversation session, then materializes deliverables and deliveries.

MVP scope:
- Assemble playbook declaration + workspace/task context
- Send the initial user query via app_chat_v3 (async background chat)
- Poll conversation status until COMPLETE / FAILED
- Create Artifact(s) from the final output
- Create Delivery record(s) from declaration and attempt to send them
- Transition task status: running -> delivered / awaiting_human / failed
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks

from derisk.core.interface.message import HumanMessage
from derisk_serve.agent.agents.controller import multi_agents
from derisk_serve.playbook.service.service import (
    PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService,
)
from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
from derisk_serve.workspace.service.service import (
    WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3.0
MAX_POLL_MINUTES = 30


async def run_task(
    system_app,
    task_id: int,
    user_code: Optional[str] = None,
    sys_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a task through its bound playbook.

    Args:
        system_app: SystemApp to look up services
        task_id: task id to execute
        user_code: optional user code for the agent run
        sys_code: optional system code

    Returns:
        dict with task_id, status, artifact_ids, delivery_ids
    """
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME, TaskService,
    )
    from derisk_serve.artifact.service.service import (
        ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService,
    )
    from derisk_serve.delivery.service.service import (
        DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService,
    )
    from derisk_serve.intervention.service.service import (
        INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService,
    )
    from derisk_serve.artifact.api.schemas import ArtifactRequest
    from derisk_serve.delivery.api.schemas import DeliveryRequest
    from derisk_serve.intervention.api.schemas import InterventionRequest

    task_service: TaskService = system_app.get_component(
        TASK_SERVICE_COMPONENT_NAME, TaskService,
    )
    playbook_service: PlaybookService = system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService,
    )
    workspace_service: WorkspaceService = system_app.get_component(
        WORKSPACE_SERVICE_COMPONENT_NAME, WorkspaceService,
    )
    artifact_service: ArtifactService = system_app.get_component(
        ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService,
    )
    delivery_service: DeliveryService = system_app.get_component(
        DELIVERY_SERVICE_COMPONENT_NAME, DeliveryService,
    )
    intervention_service: InterventionService = system_app.get_component(
        INTERVENTION_SERVICE_COMPONENT_NAME, InterventionService,
    )

    task = task_service.get_by_id(task_id)
    if not task:
        raise ValueError(f"task {task_id} not found")
    if not task.playbook_id:
        raise ValueError(f"task {task_id} has no playbook")
    playbook = playbook_service.get_by_id(task.playbook_id)
    if not playbook:
        raise ValueError(f"playbook {task.playbook_id} not found")
    workspace = workspace_service.get_by_id(task.workspace_id)
    if not workspace:
        raise ValueError(f"workspace {task.workspace_id} not found")

    declaration = playbook.declaration or {}
    app_code = workspace.default_agent_app_code or "chat_normal"

    # Build the initial user query from playbook + task
    user_query = _build_user_query(playbook, task, workspace, declaration)

    # Ensure task is running (idempotent when caller already transitioned it)
    if task.status != "running":
        try:
            task_service.start(task_id)
        except Exception as e:
            logger.warning(f"task start skipped or failed: {e}")

    # Assemble scene resources for the workbench path. Unlike the HTTP
    # chat_completions endpoint (which wires SceneResourceAssembler in its
    # pre-processing layer), run_task calls app_chat_v3 directly, so it must
    # assemble here and forward via ext_info["dynamic_resources"]. The
    # forwarding path: app_chat_v3(**ext_info) -> async_chat.chat(**ext_info)
    # -> aggregation_chat(**ext_info), where ext_info["dynamic_resources"] is
    # consumed by AgentChat (preserved/extended, never overwritten).
    scene_resources = SceneResourceAssembler.assemble(
        system_app=system_app,
        workspace_id=task.workspace_id,
        task_id=task.id,
        conv_uid=task.conv_session_id,
    )

    # Launch agent in the task's conversation session
    logger.info(
        f"[playbook runtime] starting task={task_id} conv={task.conv_session_id} "
        f"app={app_code} playbook={playbook.id}"
    )
    _, agent_conv_id = await multi_agents.app_chat_v3(
        conv_uid=task.conv_session_id,
        gpts_name=app_code,
        user_query=HumanMessage(content=user_query),
        background_tasks=BackgroundTasks(),
        user_code=user_code or str(task.created_by_user_id or "system"),
        sys_code=sys_code,
        workspace_id=task.workspace_id,
        task_id=task.id,
        dynamic_resources=scene_resources,
    )

    if not agent_conv_id:
        task_service.transition(task_id, "failed")
        return {"task_id": task_id, "status": "failed", "error": "agent did not return conv id"}

    # Poll until the agent run finishes
    final_state = await _poll_chat_completion(agent_conv_id)
    logger.info(f"[playbook runtime] task={task_id} final_state={final_state}")

    # 任务可能在运行期间被用户终止(terminate → closed):跳过状态流转与交付物物化
    current = task_service.get_by_id(task_id)
    if not current or current.status != "running":
        logger.info(
            f"[playbook runtime] task={task_id} no longer running "
            f"(status={getattr(current, 'status', None)}), skip finalize"
        )
        return {"task_id": task_id, "status": getattr(current, "status", "deleted")}

    if final_state.get("state") == "FAILED":
        task_service.transition(task_id, "failed")
        return {"task_id": task_id, "status": "failed"}

    vis_final = final_state.get("vis_final") or ""
    # 交付物/通知内容是给人看的最终答复文本;vis_final 是场景空间 VIS 渲染协议帧,
    # 只用于 SSE 推送,不应作为交付物内容持久化(否则前端只能展示协议 JSON)。
    deliverable_content = final_state.get("user_answer") or vis_final

    # 产出(Output) = 最终答复文本(final_message) + 运行期间 Agent 标记的交付
    # 文件(file);交付(Delivery)是纯代码后处理,只由 playbook 声明驱动。
    from derisk_serve.workspace.event_bus import emit_workspace_event

    deliverable_files = await _collect_deliverable_files(
        agent_conv_id, task.conv_session_id
    )

    artifact_ids: List[int] = []

    def _create_artifact(**kwargs) -> int:
        artifact = artifact_service.create(ArtifactRequest(
            task_id=task.id,
            workspace_id=task.workspace_id,
            created_by_agent=app_code,
            **kwargs,
        ))
        artifact_ids.append(artifact.id)
        emit_workspace_event(task.workspace_id, "artifact_produced", {
            "artifact_id": artifact.id,
            "title": kwargs.get("title"),
            "type": kwargs.get("type"),
            "task_id": task.id,
            "workspace_id": task.workspace_id,
        })
        return artifact.id

    # 1) 最终答复:最终发送给 Human 的 message 内容
    final_message_artifact_id: Optional[int] = None
    if deliverable_content:
        final_message_artifact_id = _create_artifact(
            type="final_message",
            title=f"{playbook.name} — 最终答复",
            content_text=str(deliverable_content)[:16000],
            provenance={
                "playbook_id": playbook.id,
                "playbook_name": playbook.name,
                "agent_conv_id": agent_conv_id,
            },
        )

    # 2) 交付文件:Agent 运行期间通过 deliver_file / create_file 标记的文件,
    # 只存文件引用 URL,不拷贝内容
    for f in deliverable_files:
        file_url = f.get("download_url") or f.get("preview_url") or f.get("oss_url")
        _create_artifact(
            type="file",
            title=f.get("file_name") or "unnamed",
            content_ref=file_url,
            provenance={
                "playbook_id": playbook.id,
                "playbook_name": playbook.name,
                "agent_conv_id": agent_conv_id,
                "source": "deliverable_file",
                "file_id": f.get("file_id"),
                "mime_type": f.get("mime_type"),
                "file_size": f.get("file_size"),
                "object_path": f.get("object_path"),
                "description": f.get("description"),
            },
        )

    # 投递消息 = 最终答复文本 + 交付文件链接(邮件/IM 里可直接打开)
    delivery_message = str(deliverable_content)[:8000]
    file_links = [
        (f.get("file_name") or "file", f.get("download_url") or f.get("preview_url"))
        for f in deliverable_files
    ]
    file_links = [(n, u) for n, u in file_links if u]
    if file_links:
        links_md = "\n".join(f"- [{n}]({u})" for n, u in file_links)
        delivery_message = f"{delivery_message}\n\n交付文件:\n{links_md}"

    # Create deliveries from deliverable declarations
    delivery_ids: List[int] = []
    deliverables = declaration.get("deliverables") or []
    for d in deliverables:
        for delivery_decl in d.get("delivery") or []:
            if delivery_decl.get("category") != "notify":
                continue
            delivery = delivery_service.create(DeliveryRequest(
                artifact_id=final_message_artifact_id,
                task_id=task.id,
                workspace_id=task.workspace_id,
                category="notify",
                channel=delivery_decl.get("channel", "in_app"),
                target=delivery_decl.get("target", ""),
                title=f"[{playbook.name}] {d.get('type', 'report')} delivered",
                message=delivery_message,
                format=delivery_decl.get("format", "message_card"),
                require_intervention=delivery_decl.get("require_intervention", "none"),
            ))
            delivery_ids.append(delivery.id)
            # Attempt immediate send; failures are recorded on the record
            try:
                await delivery_service.send(delivery.id)
            except Exception as e:
                logger.warning(f"delivery send failed for {delivery.id}: {e}")
            emit_workspace_event(task.workspace_id, "delivery_sent", {
                "delivery_id": delivery.id,
                "artifact_id": delivery.artifact_id,
                "task_id": task.id,
                "workspace_id": task.workspace_id,
                "channel": delivery_decl.get("channel", "in_app"),
            })

    # If any delivery requires review, raise an intervention and stop at awaiting_human
    requires_review = any(
        d.get("require_intervention") == "review"
        for dlv in deliverables
        for d in dlv.get("delivery") or []
    )
    if requires_review:
        try:
            intervention = intervention_service.create(InterventionRequest(
                task_id=task.id,
                workspace_id=task.workspace_id,
                type="review",
                requested_by="system",
                question={
                    "playbook_id": playbook.id,
                    "playbook_name": playbook.name,
                    "reason": "delivery requires human review before close",
                },
                context={"agent_conv_id": agent_conv_id, "artifact_ids": artifact_ids},
            ))
            emit_workspace_event(task.workspace_id, "intervention_triggered", {
                "intervention_id": intervention.id,
                "task_id": task.id,
                "workspace_id": task.workspace_id,
                "tool": "delivery_review",
                "requested_by": "system",
            })
        except Exception as e:
            logger.warning(f"failed to create review intervention: {e}")
        task_service.transition(task_id, "awaiting_human")
        return {
            "task_id": task_id,
            "status": "awaiting_human",
            "agent_conv_id": agent_conv_id,
            "artifact_ids": artifact_ids,
            "delivery_ids": delivery_ids,
        }

    # Normal path: mark delivered
    task_service.transition(task_id, "delivered")
    return {
        "task_id": task_id,
        "status": "delivered",
        "agent_conv_id": agent_conv_id,
        "artifact_ids": artifact_ids,
        "delivery_ids": delivery_ids,
    }


async def _collect_deliverable_files(
    agent_conv_id: Optional[str], fallback_conv_id: Optional[str],
) -> List[Dict[str, Any]]:
    """收集任务运行期间被标记为交付物(deliverable)的文件。

    主路径:DB 文件元数据存储(沙箱模式下 deliver_file 经 GptsMemory 持久化);
    兜底:解析 gpts messages 的 action_report[].output_files(本地模式
    deliver_file 用内存元数据存储,运行结束即丢,只能从消息记录里捞)。
    """
    files: Dict[str, Dict[str, Any]] = {}

    try:
        from derisk_serve.agent.agents.derisks_memory import (
            MetaDerisksFileMetadataStorage,
        )

        storage = MetaDerisksFileMetadataStorage()
        conv_ids = {c for c in (agent_conv_id, fallback_conv_id) if c}
        for conv_id in conv_ids:
            for f in await storage.list_files(conv_id, file_type="deliverable"):
                if f.file_id in files:
                    continue
                files[f.file_id] = {
                    "file_id": f.file_id,
                    "file_name": f.file_name,
                    "mime_type": f.mime_type,
                    "file_size": f.file_size,
                    "download_url": f.download_url,
                    "preview_url": f.preview_url,
                    "oss_url": f.oss_url,
                    "object_path": (f.metadata or {}).get("object_path"),
                    "description": (f.metadata or {}).get("description"),
                }
    except Exception as e:
        logger.warning(f"[playbook runtime] deliverable DB query failed: {e}")

    if files:
        return list(files.values())

    # 兜底:从消息 action_report 提取(与 vis converter 同一数据源)
    try:
        from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao

        conv_id = agent_conv_id or fallback_conv_id
        if not conv_id:
            return []
        messages = await GptsMessagesDao().get_by_conv_id(conv_id)
        for msg in messages:
            for action_out in msg.action_report or []:
                if isinstance(action_out, dict):
                    output_files = action_out.get("output_files") or []
                else:
                    output_files = getattr(action_out, "output_files", None) or []
                for fi in output_files:
                    if not isinstance(fi, dict):
                        continue
                    if fi.get("file_type") != "deliverable":
                        continue
                    fid = fi.get("file_id")
                    if fid and fid not in files:
                        files[fid] = fi
    except Exception as e:
        logger.warning(
            f"[playbook runtime] deliverable message fallback failed: {e}"
        )

    return list(files.values())


def _build_user_query(
    playbook: Any, task: Any, workspace: Any, declaration: Dict[str, Any],
) -> str:
    """Build the initial user prompt: just the task goal (instruction).

    skills/resources are injected as agent tools via SceneResourceAssembler
    (dynamic_resources); deliverables/distill are playbook-level config rendered
    into the system prompt by render_workspace_context_summary. The user query
    only needs to tell the agent the task goal - 剧本名/workspace/skills 等不必
    重复(已在工具和 system prompt 里),否则任务输入会塞满无关内容。
    """
    lines: List[str] = []
    if task.title:
        lines.append(task.title)
    if task.description:
        lines.append(task.description)
    if not lines:
        # 兜底(不应发生:TaskRequest.title 必填)
        lines.append(f"Execute playbook {playbook.name}")
    return "\n".join(lines)


async def _poll_chat_completion(agent_conv_id: str) -> Dict[str, Any]:
    """Poll query_chat until the agent run reaches a final state."""
    max_attempts = int((MAX_POLL_MINUTES * 60) / POLL_INTERVAL_SECONDS)
    for attempt in range(max_attempts):
        try:
            result = await multi_agents.query_chat(conv_id=agent_conv_id)
            if result is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
            vis_final, user_answer, current_vis_render, is_final, state = result
            if state in ("COMPLETE", "FAILED") or is_final:
                return {
                    "state": state,
                    "is_final": is_final,
                    "vis_final": vis_final,
                    "user_answer": user_answer,
                    "vis_render": current_vis_render,
                }
        except Exception as e:
            logger.warning(f"playbook runtime poll error: {e}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return {"state": "FAILED", "error": "polling timeout"}
