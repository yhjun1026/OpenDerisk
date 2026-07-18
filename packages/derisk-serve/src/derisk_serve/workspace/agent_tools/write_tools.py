"""Layer 2 (空间操作) write tools — Lobby only. start_task creates a real Task; other tools create interventions."""
from typing import Callable, List, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk_serve.intervention.api.schemas import InterventionRequest
from derisk_serve.workspace.agent_tools._task_creator import create_task_from_tool
from derisk_serve.workspace.agent_tools.read_tools import (
    get_intervention_service,
    get_playbook_service,
)

WorkspaceEventCallback = Callable[[str, dict], None]


def _p(name, type_, desc, required=False):
    from derisk.agent.resource.tool.base import ToolParameter

    return ToolParameter(name=name, type=type_, description=desc, required=required)


def _make_intervention(
    system_app,
    *,
    tool_name: str,
    args: dict,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int],
    on_event: Optional[WorkspaceEventCallback] = None,
) -> dict:
    svc = get_intervention_service(system_app)
    request = InterventionRequest(
        workspace_id=workspace_id,
        task_id=task_id,
        conv_uid=conv_uid,
        requested_by=user_id if user_id is not None else "system",
        question={"tool": tool_name, "args": args},
    )
    entity = svc.create(request=request)
    if on_event:
        on_event("intervention_triggered", {
            "intervention_id": entity.id,
            "task_id": task_id,
            "workspace_id": workspace_id,
            "tool": tool_name,
            "requested_by": request.requested_by,
        })
    return {"intervention_id": entity.id, "status": "awaiting_human"}


def build_write_tools(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int] = None,
    on_event: Optional[WorkspaceEventCallback] = None,
) -> List[FunctionTool]:
    def start_task(**kwargs):
        playbook_id = kwargs.get("playbook_id")
        title = kwargs.get("title")
        description = kwargs.get("description")
        result = create_task_from_tool(
            system_app,
            workspace_id=workspace_id,
            user_id=user_id,
            playbook_id=playbook_id,
            title=title,
            description=description,
        )
        if on_event:
            on_event("task_created", {
                "task_id": result["task_id"],
                "title": result["title"],
                "status": result["status"],
                "playbook_id": result["playbook_id"],
                "playbook_name": result["playbook_name"],
                "triggered_by": result["triggered_by"],
                "workspace_id": workspace_id,
            })
        return result

    def _make_close_task_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="close_task",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
            on_event=on_event,
        )

    def _make_publish_asset_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="publish_asset",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
            on_event=on_event,
        )

    def _make_create_delivery_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="create_delivery",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
            on_event=on_event,
        )

    def _make_update_workspace_tool(**kwargs):
        return _make_intervention(
            system_app,
            tool_name="update_workspace",
            args=kwargs,
            workspace_id=workspace_id,
            user_id=user_id,
            conv_uid=conv_uid,
            task_id=task_id,
            on_event=on_event,
        )

    specs = [
        ("start_task", "在当前空间下发起一个任务", start_task, {
            "playbook_id": _p("playbook_id", "integer", "剧本 ID,不传则为 ad-hoc 任务"),
            "title": _p("title", "string", "任务标题"),
            "description": _p("description", "string", "任务目标描述"),
        }),
        ("close_task", "关闭指定任务", _make_close_task_tool, {
            "task_id": _p("task_id", "integer", "要关闭的任务 ID", required=True),
        }),
        ("publish_asset", "将一个交付物沉淀为空间级 Asset", _make_publish_asset_tool, {
            "artifact_id": _p("artifact_id", "integer", "交付物 ID", required=True),
            "name": _p("name", "string", "Asset 名称"),
        }),
        ("create_delivery", "创建一条投递记录", _make_create_delivery_tool, {
            "artifact_id": _p("artifact_id", "integer", "交付物 ID", required=True),
            "channel": _p("channel", "string", "投递渠道,如 in_app/email"),
            "target": _p("target", "string", "投递目标"),
        }),
        ("update_workspace", "更新空间基本信息", _make_update_workspace_tool, {
            "name": _p("name", "string", "空间名称"),
            "description": _p("description", "string", "空间描述"),
        }),
    ]
    tools: List[FunctionTool] = []
    for name, desc, fn, tool_args in specs:
        tools.append(FunctionTool(name=name, description=desc, func=fn, args=tool_args))
    return tools


def _coerce_declaration(raw) -> dict:
    """Coerce a declaration payload (str JSON / dict / None) to a dict.

    PlaybookService.validate_declaration requires a dict; tool callers may pass a
    JSON string (e.g. ``declaration_dsl="{}"``) so we parse defensively.
    """
    import json

    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def build_scene_write_tools(
    system_app,
    workspace_id: int,
    user_id: Optional[str],
    conv_uid: str,
    task_id: Optional[int] = None,
    on_event: Optional[WorkspaceEventCallback] = None,
) -> List[FunctionTool]:
    """场景管理写工具全集:任务/剧本/介入/产物交付/workspace,供 WorkspaceSceneResource TOOLS 槽。

    在 ``build_write_tools`` 的 5 个工具(任务/交付/资产/workspace 经介入审批)之上,
    追加 5 个直接写工具:create/update/delete_playbook + resolve/abort_intervention。
    """
    from derisk_serve.playbook.api.schemas import PlaybookRequest
    from derisk_serve.intervention.api.schemas import InterventionResolveRequest

    base = build_write_tools(system_app, workspace_id, user_id, conv_uid, task_id, on_event)

    def create_playbook(**kwargs):
        svc = get_playbook_service(system_app)
        req = PlaybookRequest(
            workspace_id=kwargs.get("workspace_id") or workspace_id,
            name=kwargs.get("name"),
            declaration=_coerce_declaration(kwargs.get("declaration_dsl")),
        )
        entity = svc.create(req)
        return {"playbook_id": entity.id}

    def update_playbook(**kwargs):
        svc = get_playbook_service(system_app)
        playbook_id = int(kwargs.get("playbook_id"))
        req = PlaybookRequest(
            id=playbook_id,
            workspace_id=kwargs.get("workspace_id") or workspace_id,
            name=kwargs.get("name"),
            declaration=_coerce_declaration(kwargs.get("declaration_dsl")),
        )
        entity = svc.update(req)
        return {"playbook_id": entity.id}

    def delete_playbook(**kwargs):
        svc = get_playbook_service(system_app)
        playbook_id = int(kwargs.get("playbook_id"))
        svc.delete(playbook_id)
        return {"playbook_id": playbook_id, "deleted": True}

    def resolve_intervention(**kwargs):
        svc = get_intervention_service(system_app)
        intervention_id = int(kwargs.get("intervention_id"))
        decision = kwargs.get("decision") or {"action": "approved"}
        req = InterventionResolveRequest(decision=decision)
        entity = svc.resolve(intervention_id, req)
        return {
            "intervention_id": entity.id,
            "status": getattr(entity, "status", "resolved"),
        }

    def abort_intervention(**kwargs):
        svc = get_intervention_service(system_app)
        intervention_id = int(kwargs.get("intervention_id"))
        entity = svc.abort(intervention_id)
        return {
            "intervention_id": entity.id,
            "status": getattr(entity, "status", "aborted"),
        }

    extra_specs = [
        ("create_playbook", "在当前空间下创建一个剧本", create_playbook, {
            "name": _p("name", "string", "剧本名称", required=True),
            "declaration_dsl": _p("declaration_dsl", "string", "剧本声明 DSL(JSON 字符串)"),
        }),
        ("update_playbook", "更新指定剧本的声明", update_playbook, {
            "playbook_id": _p("playbook_id", "integer", "剧本 ID", required=True),
            "name": _p("name", "string", "剧本名称"),
            "declaration_dsl": _p("declaration_dsl", "string", "剧本声明 DSL(JSON 字符串)"),
        }),
        ("delete_playbook", "删除指定剧本", delete_playbook, {
            "playbook_id": _p("playbook_id", "integer", "剧本 ID", required=True),
        }),
        ("resolve_intervention", "批准一个待介入请求(记录决策并流转状态)", resolve_intervention, {
            "intervention_id": _p("intervention_id", "integer", "介入 ID", required=True),
            "decision": _p("decision", "string", '决策 JSON,如 {"action":"approved"}'),
        }),
        ("abort_intervention", "中止一个介入请求", abort_intervention, {
            "intervention_id": _p("intervention_id", "integer", "介入 ID", required=True),
        }),
    ]
    for name, desc, fn, tool_args in extra_specs:
        base.append(FunctionTool(name=name, description=desc, func=fn, args=tool_args))
    return base
