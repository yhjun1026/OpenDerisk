"""Layer 2 (空间操作) write tools — Lobby only. start_task creates a real Task; other tools create interventions."""
from typing import Callable, List, Optional

from derisk.agent.resource.tool.base import FunctionTool
from derisk_serve.intervention.api.schemas import InterventionRequest
from derisk_serve.workspace.agent_tools._task_creator import create_task_from_tool
from derisk_serve.workspace.agent_tools.read_tools import (
    get_intervention_service,
    get_playbook_service,
    get_trigger_service,
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
    parent_conv_id: Optional[str] = None,
    on_event: Optional[WorkspaceEventCallback] = None,
) -> dict:
    svc = get_intervention_service(system_app)
    request = InterventionRequest(
        workspace_id=workspace_id,
        task_id=task_id,
        conv_uid=conv_uid,
        parent_conv_id=parent_conv_id,
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
        trigger_type = kwargs.get("trigger_type")
        if trigger_type:
            # 定时/条件触发路径:创建触发源(规则),到点/事件发生时自动按剧本创建任务
            return _create_trigger_rule(
                trigger_type=trigger_type,
                playbook_id=playbook_id,
                title=title,
                description=description,
                cron=kwargs.get("cron"),
                trigger_config=kwargs.get("trigger_config"),
            )
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

    def _create_trigger_rule(
        *, trigger_type, playbook_id, title, description, cron, trigger_config
    ):
        from derisk_serve.trigger.api.schemas import TriggerSourceRequest

        if trigger_type not in ("timer", "webhook", "alert"):
            return {"error": f"不支持的 trigger_type: {trigger_type},应为 timer/webhook/alert"}
        if not playbook_id:
            return {"error": "创建触发规则必须指定 playbook_id(用哪个剧本执行)"}
        if trigger_type == "timer" and not cron:
            return {"error": "trigger_type=timer 时必须提供 cron 表达式,如 '0 20 * * 5'"}
        config = _coerce_declaration(trigger_config)
        if cron:
            config["cron"] = cron
        svc = get_trigger_service(system_app)
        entity = svc.create(TriggerSourceRequest(
            workspace_id=workspace_id,
            type=trigger_type,
            name=title or description or "未命名触发规则",
            target_playbook_id=int(playbook_id),
            instruction=description or title,
            config=config,
        ))
        return {
            "trigger_id": entity.id,
            "type": entity.type,
            "cron": (entity.config or {}).get("cron"),
            "note": "触发规则已创建;timer 类型已注册调度,到点自动按剧本创建任务",
        }

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
        ("start_task", "发起任务:默认立即创建并执行;传 trigger_type 则创建定时/条件触发规则,到点自动按剧本创建任务", start_task, {
            "playbook_id": _p("playbook_id", "integer", "剧本 ID,不传则为 ad-hoc 任务;创建触发规则时必传"),
            "title": _p("title", "string", "任务/规则名称(简短标识)"),
            "description": _p("description", "string", "任务目标指令:写给执行者的具体目标——分析什么方向、产出什么(剧本是通用能力,指令使其具体化);创建触发规则时作为每次任务的指令。调度时间不要写在这里,用 cron 表达"),
            "trigger_type": _p("trigger_type", "string", "定时/条件触发时传 timer/webhook/alert;不传=立即执行"),
            "cron": _p("cron", "string", "trigger_type=timer 时必填,标准 cron 表达式,如 '0 20 * * 5'(每周五20点)"),
            "trigger_config": _p("trigger_config", "string", "JSON 字符串;webhook 传 {\"secret\":\"...\"},alert 传 {\"alert_name\":\"...\"}"),
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
    追加直接写工具:create/update/delete_playbook + resolve/abort_intervention
    + update/delete/fire_trigger。
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

    def update_trigger(**kwargs):
        from derisk_serve.trigger.api.schemas import TriggerSourceRequest

        svc = get_trigger_service(system_app)
        trigger_id = int(kwargs.get("trigger_id"))
        existing = svc.get_by_id(trigger_id)
        if not existing:
            return {"error": f"trigger {trigger_id} not found"}
        config = dict(existing.config or {})
        extra = _coerce_declaration(kwargs.get("trigger_config"))
        if extra:
            config.update(extra)
        if kwargs.get("cron"):
            config["cron"] = kwargs["cron"]
        entity = svc.update(TriggerSourceRequest(
            id=trigger_id,
            workspace_id=workspace_id,
            type=kwargs.get("type") or existing.type,
            name=kwargs.get("name") or existing.name,
            target_playbook_id=int(kwargs.get("playbook_id") or existing.target_playbook_id),
            instruction=kwargs.get("instruction") or existing.instruction,
            config=config,
            is_active=kwargs.get("is_active") if kwargs.get("is_active") is not None else existing.is_active,
        ))
        return {"trigger_id": entity.id, "is_active": entity.is_active}

    def delete_trigger(**kwargs):
        svc = get_trigger_service(system_app)
        trigger_id = int(kwargs.get("trigger_id"))
        deleted = svc.delete(trigger_id)
        return {"trigger_id": trigger_id, "deleted": deleted}

    def fire_trigger(**kwargs):
        from derisk_serve.trigger.api.schemas import TriggerFireRequest

        svc = get_trigger_service(system_app)
        trigger_id = int(kwargs.get("trigger_id"))
        payload = _coerce_declaration(kwargs.get("payload"))
        result = svc.fire(TriggerFireRequest(
            workspace_id=workspace_id,
            trigger_id=trigger_id,
            payload=payload,
        ))
        task_id = result.get("task_id")
        if task_id and on_event:
            trigger = svc.get_by_id(trigger_id)
            on_event("task_created", {
                "task_id": task_id,
                "title": getattr(trigger, "instruction", None) or getattr(trigger, "name", ""),
                "status": "pending_trigger",
                "playbook_id": getattr(trigger, "target_playbook_id", None),
                "playbook_name": None,
                "triggered_by": getattr(trigger, "type", None),
                "workspace_id": workspace_id,
            })
        return result

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
        ("update_trigger", "更新指定触发规则(改 cron/启停/换剧本等)", update_trigger, {
            "trigger_id": _p("trigger_id", "integer", "触发规则 ID", required=True),
            "name": _p("name", "string", "规则名称"),
            "type": _p("type", "string", "timer/webhook/alert/manual"),
            "playbook_id": _p("playbook_id", "integer", "目标剧本 ID"),
            "instruction": _p("instruction", "string", "触发时作为任务标题的指令"),
            "cron": _p("cron", "string", "timer 类型的 cron 表达式"),
            "trigger_config": _p("trigger_config", "string", "JSON 字符串,合并进现有 config"),
            "is_active": _p("is_active", "boolean", "启用/暂停"),
        }),
        ("delete_trigger", "删除指定触发规则(删除前需用户确认)", delete_trigger, {
            "trigger_id": _p("trigger_id", "integer", "触发规则 ID", required=True),
        }),
        ("fire_trigger", "立即按指定触发规则执行一次(创建并启动任务)", fire_trigger, {
            "trigger_id": _p("trigger_id", "integer", "触发规则 ID", required=True),
            "payload": _p("payload", "string", "JSON 字符串,作为任务输入负载"),
        }),
    ]
    for name, desc, fn, tool_args in extra_specs:
        base.append(FunctionTool(name=name, description=desc, func=fn, args=tool_args))
    return base
