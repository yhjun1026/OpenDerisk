"""Workspace context builder for agent prompt injection.

Builds a focused ``WorkspaceContextSnapshot`` that later tasks can render into
an agent system prompt. It intentionally keeps only the information an agent
needs to behave in a workspace-aware way:

- workspace identity and default app
- materialized resources (tools / sub-agents)
- optional current task
- optional playbook declaration DSL (when a task is bound to a playbook)
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, TYPE_CHECKING

from derisk_serve.workspace.materializer import (
    MaterializedResources,
    materialize_resources,
)
from derisk_serve.workspace.service.service import (
    WORKSPACE_SERVICE_COMPONENT_NAME,
    WorkspaceService,
)

if TYPE_CHECKING:
    from derisk_serve.playbook.resource import PlaybookResource

# Task and playbook services are imported lazily below to avoid pulling in
# heavy endpoint/runtime dependencies (e.g. derisk_app) at module load time.


@dataclass
class WorkspaceContextSnapshot:
    """Lightweight snapshot of the context an agent needs inside a workspace."""

    workspace: Any
    materialized_resources: MaterializedResources
    task: Optional[Any] = None
    playbook_declaration: Optional[dict] = None
    playbook_resource: Optional["PlaybookResource"] = None  # NEW: RFC-005 剧本资源协议
    user_id: Optional[str] = None
    workspace_id: Optional[int] = None
    task_id: Optional[int] = None
    playbooks: List[Any] = field(default_factory=list)
    active_tasks: List[Any] = field(default_factory=list)
    triggers: List[Any] = field(default_factory=list)
    focused_artifact: Optional[Any] = None  # 用户当前关注的交付物(隐式上下文)


def get_workspace_service(system_app) -> WorkspaceService:
    """Resolve the workspace service from ``system_app``."""
    return system_app.get_component(
        WORKSPACE_SERVICE_COMPONENT_NAME,
        WorkspaceService,
    )


def get_task_service(system_app):
    """Resolve the task service from ``system_app``."""
    from derisk_serve.task.service.service import (
        TASK_SERVICE_COMPONENT_NAME,
        TaskService,
    )

    return system_app.get_component(TASK_SERVICE_COMPONENT_NAME, TaskService)


def get_playbook_service(system_app):
    """Resolve the playbook service from ``system_app``."""
    from derisk_serve.playbook.service.service import (
        PLAYBOOK_SERVICE_COMPONENT_NAME,
        PlaybookService,
    )

    return system_app.get_component(
        PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService
    )


def get_artifact_service(system_app):
    """Resolve the artifact service from ``system_app``."""
    from derisk_serve.artifact.service.service import (
        ARTIFACT_SERVICE_COMPONENT_NAME,
        ArtifactService,
    )

    return system_app.get_component(
        ARTIFACT_SERVICE_COMPONENT_NAME, ArtifactService
    )


def get_trigger_service(system_app):
    """Resolve the trigger service from ``system_app``."""
    from derisk_serve.trigger.service.service import (
        TRIGGER_SERVICE_COMPONENT_NAME,
        TriggerService,
    )

    return system_app.get_component(
        TRIGGER_SERVICE_COMPONENT_NAME, TriggerService
    )


def build_workspace_context(
    system_app,
    workspace_id: int,
    user_id: Optional[str] = None,
    task_id: Optional[int] = None,
    focus_artifact_id: Optional[int] = None,
    mode: str = "lobby",
) -> WorkspaceContextSnapshot:
    """Build a workspace context snapshot.

    Args:
        system_app: The running ``SystemApp`` used to look up services.
        workspace_id: Identifier of the workspace to contextualize.
        user_id: Optional user identifier for personalization / auditing.
        task_id: Optional current task identifier. When provided, the task and
            its bound playbook declaration are loaded.
        mode: "lobby" for open workspace chat, "workbench" for task-focused work.
            Stored only for rendering; the snapshot itself is mode-agnostic.

    Returns:
        A ``WorkspaceContextSnapshot`` even when the workspace or task is not
        found, so callers can safely render a degraded summary.
    """
    ws_service = get_workspace_service(system_app)
    workspace = ws_service.get_by_id(workspace_id)

    materialized = materialize_resources(system_app, workspace_id)

    task = None
    playbook_declaration = None
    playbook_resource = None  # NEW: RFC-005 剧本资源

    if task_id is not None:
        task_service = get_task_service(system_app)
        task = task_service.get_by_id(task_id)
        if task and getattr(task, "playbook_id", None):
            pb_service = get_playbook_service(system_app)
            playbook = pb_service.get_by_id(task.playbook_id)
            if playbook and getattr(playbook, "declaration", None):
                playbook_declaration = playbook.declaration

            # NEW: 创建 PlaybookResource（用于 RFC-005 协议注入）
            # 注意：PlaybookResource.declare() 是纯函数，不需要异步
            try:
                from derisk_serve.playbook.resource import (
                    PlaybookConfig,
                    PlaybookResource,
                )
                config = PlaybookConfig.from_playbook_response(playbook)
                playbook_resource = PlaybookResource(config, system_app)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to create PlaybookResource: {e}"
                )

    active_tasks: List[Any] = []
    if mode == "lobby":
        try:
            task_service = get_task_service(system_app)
            from derisk_serve.task.api.schemas import TaskListFilter

            active_tasks = task_service.list_tasks(
                TaskListFilter(workspace_id=workspace_id)
            ) or []
            # Keep only genuinely active tasks (状态枚举见 task/api/schemas.py:
            # draft/pending_trigger/running/awaiting_human/blocked/delivered/
            # closed/archived/failed;delivered/closed/failed 为终态,不属"进行中")
            active_tasks = [
                t
                for t in active_tasks
                if getattr(t, "status", None)
                in {"running", "awaiting_human", "blocked"}
            ]
        except Exception:
            pass

    playbooks: List[Any] = []
    if mode == "lobby":
        try:
            pb_service = get_playbook_service(system_app)
            from derisk_serve.playbook.api.schemas import PlaybookListFilter

            playbooks = pb_service.list_playbooks(
                PlaybookListFilter(workspace_id=workspace_id, is_active=True)
            ) or []
        except Exception:
            pass

    triggers: List[Any] = []
    if mode == "lobby":
        try:
            trigger_service = get_trigger_service(system_app)
            from derisk_serve.trigger.api.schemas import TriggerListFilter

            triggers = trigger_service.list_triggers(
                TriggerListFilter(workspace_id=workspace_id)
            ) or []
        except Exception:
            pass

    # 用户当前关注的交付物(隐式上下文):加载失败降级为 None,不阻断对话
    focused_artifact = None
    if focus_artifact_id is not None:
        try:
            artifact_service = get_artifact_service(system_app)
            focused_artifact = artifact_service.get_by_id(int(focus_artifact_id))
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to load focused artifact {focus_artifact_id}",
                exc_info=True,
            )

    return WorkspaceContextSnapshot(
        workspace=workspace,
        materialized_resources=materialized,
        task=task,
        playbook_declaration=playbook_declaration,
        playbook_resource=playbook_resource,  # NEW
        user_id=user_id,
        workspace_id=workspace_id,
        task_id=task_id,
        active_tasks=active_tasks,
        playbooks=playbooks,
        triggers=triggers,
        focused_artifact=focused_artifact,
    )


def render_workspace_context_summary(
    ctx: WorkspaceContextSnapshot,
    mode: str = "lobby",
) -> str:
    """Render the snapshot as a compact, human-readable summary for prompts."""
    ws = ctx.workspace
    name = (
        getattr(ws, "name", f"workspace_{ctx.workspace_id}")
        if ws
        else f"workspace_{ctx.workspace_id}"
    )
    lines = [
        f"# 当前空间：{name} (id={ctx.workspace_id})",
        f"模式：{mode}",
    ]

    materialized = ctx.materialized_resources
    if materialized:
        dynamic = getattr(materialized, "dynamic_resources", []) or []
        extra = getattr(materialized, "extra_agents", []) or []
        if dynamic:
            lines.append(f"已挂载动态资源：{len(dynamic)}")
        if extra:
            lines.append(f"已挂载子 Agent：{len(extra)}")

    if ctx.task:
        lines.append(
            f"当前任务：{getattr(ctx.task, 'title', '')} "
            f"(id={getattr(ctx.task, 'id', '')})"
        )

    if ctx.playbooks:
        lines.append("可用剧本：")
        for pb in ctx.playbooks:
            lines.append(f"- id={getattr(pb, 'id', '')} {getattr(pb, 'name', '')}")

    if ctx.triggers:
        lines.append("已有触发规则(定时/条件任务,勿重复创建)：")
        for tr in ctx.triggers:
            tr_type = getattr(tr, "type", "")
            config = getattr(tr, "config", None) or {}
            cron = config.get("cron") if isinstance(config, dict) else None
            schedule = f"cron={cron}" if cron else tr_type
            active = "active" if getattr(tr, "is_active", False) else "paused"
            lines.append(
                f"- id={getattr(tr, 'id', '')} [{schedule}] "
                f"→ 剧本#{getattr(tr, 'target_playbook_id', '')} "
                f"{getattr(tr, 'name', '')}({active})"
            )

    if ctx.playbook_declaration:
        skills = (ctx.playbook_declaration or {}).get("skills", []) or []
        if skills:
            skill_names = [
                s.get("name", str(s)) if isinstance(s, dict) else str(s)
                for s in skills
            ]
            lines.append(f"剧本技能：{', '.join(skill_names)}")

        deliverables = (ctx.playbook_declaration or {}).get("deliverables") or []
        if deliverables:
            lines.append("预期交付物：")
            for d in deliverables:
                lines.append(f"- {d.get('type')}: {d.get('title', '')}")

        distill = (ctx.playbook_declaration or {}).get("distill") or {}
        if distill.get("forced"):
            lines.append("注：本任务需在关闭前将结论沉淀为空间资产。")

    return "\n".join(lines)
