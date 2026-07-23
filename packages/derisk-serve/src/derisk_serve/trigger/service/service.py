"""Trigger service — creates a Task from a fired trigger source.

MVP: timer/webhook/alert/manual all funnel through `fire()` which creates
a Task in `pending_trigger` status pointing at the target playbook.
The CronService wiring is left as an integration point — the timer
trigger's `config.cron` is stored but actual scheduling is the
responsibility of the caller (MVP relies on manual fire + external cron).
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import (
    TriggerFireRequest, TriggerListFilter, TriggerSourceRequest,
    TriggerSourceResponse,
)
from ..config import ServeConfig
from ..models.models import TriggerSourceDao, TriggerSourceEntity

TRIGGER_SERVICE_COMPONENT_NAME = "serve_trigger_service"
logger = logging.getLogger(__name__)

# hold refs to detached cron-registration tasks so CPython doesn't GC them mid-flight
_pending_cron_tasks: set = set()


class TriggerService(BaseService[TriggerSourceEntity, TriggerSourceRequest, TriggerSourceResponse]):
    name = TRIGGER_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[TriggerSourceDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: TriggerSourceDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or TriggerSourceDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: TriggerSourceRequest) -> TriggerSourceResponse:
        response = self._dao.create(request)
        self._sync_cron_for_trigger(response, "register")
        return response

    def update(self, request: TriggerSourceRequest) -> TriggerSourceResponse:
        if not request.id:
            raise ValueError("trigger id required for update")
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == request.id
            ).first()
            if not entity:
                raise ValueError(f"trigger {request.id} not found")
            entity.name = request.name
            entity.type = request.type
            entity.target_playbook_id = request.target_playbook_id
            entity.instruction = request.instruction
            entity.config_json = json.dumps(request.config or {}, ensure_ascii=False)
            entity.is_active = request.is_active
            session.commit()
            response = self._dao.to_response(entity)
            self._sync_cron_for_trigger(response, "update")
            return response
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, trigger_id: int) -> bool:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == trigger_id
            ).first()
            if not entity:
                return False
            cron_trigger = self._dao.to_response(entity) if entity.type == "timer" else None
            session.delete(entity)
            session.commit()
            if cron_trigger:
                self._sync_cron_for_trigger(cron_trigger, "remove")
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _launch_task(self, task_id: int) -> None:
        """detached 启动 task 执行(start + run_task),不阻塞 fire 调用方。

        复用 workspace._task_creator 的 detached 启动器(含失败转 failed)。
        所有 fire 调用路径(timer 经 cron / webhook / alert / 手动 fire)都在
        事件循环内;若不在(loop 缺失)则降级为停留在 pending_trigger。
        """
        try:
            from derisk_serve.workspace.agent_tools._task_creator import (
                _pending_detached_tasks, _run_task_detached,
            )
        except ImportError as e:
            logger.warning("cannot import _run_task_detached for trigger task %s: %s", task_id, e)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("no running loop; trigger task %s left in pending_trigger", task_id)
            return
        t = loop.create_task(_run_task_detached(self._system_app, task_id, None))
        _pending_detached_tasks.add(t)
        t.add_done_callback(_pending_detached_tasks.discard)

    def _sync_cron_for_trigger(self, trigger: TriggerSourceResponse, action: str) -> None:
        """timer 触发器 CRUD 时同步注册/更新/移除对应 cron job。

        定时任务真正可调度靠这一步:把 trigger 的 cron 注册到 cron service
        (APScheduler),payload 指向 trigger_id,到点时 _execute_trigger_fire
        调 fire 执行剧本+指令。非 timer 类型跳过。detached 调用 async 接口,
        失败只记日志。
        """
        if trigger.type != "timer":
            return
        cron_expr = (trigger.config or {}).get("cron")
        job_id = f"trigger:{trigger.id}"

        if action == "remove":
            self._detached_cron_op(job_id, "remove", lambda svc: svc.remove_job(job_id))
            return

        if not trigger.is_active or not cron_expr:
            if not cron_expr:
                logger.warning("timer trigger %s has no cron expr; skip cron register", trigger.id)
            self._detached_cron_op(job_id, "remove", lambda svc: svc.remove_job(job_id))
            return

        from derisk.cron import (
            CronJobCreate, CronJobPatch, CronPayload, CronSchedule,
            PayloadKind, ScheduleKind,
        )
        payload = CronPayload(
            kind=PayloadKind.TRIGGER_FIRE,
            trigger_id=trigger.id,
            workspace_id=trigger.workspace_id,
        )
        schedule = CronSchedule(kind=ScheduleKind.CRON, expr=cron_expr)
        req = CronJobCreate(
            id=job_id, name=trigger.name, enabled=True,
            schedule=schedule, payload=payload,
        )
        if action == "update":
            patch = CronJobPatch(
                name=trigger.name, enabled=True, schedule=schedule, payload=payload,
            )
            coro_factory = lambda svc: self._update_or_add_cron(svc, job_id, patch, req)
        else:
            coro_factory = lambda svc: svc.add_job(req)
        self._detached_cron_op(job_id, action, coro_factory)

    def _detached_cron_op(self, job_id: str, action: str, coro_factory) -> None:
        """detached 启动一个 cron service 操作(async),失败只记日志。"""
        try:
            from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME as CRON_COMP
            from derisk_serve.cron.service.service import Service as CronService
            cron_service = self._system_app.get_component(CRON_COMP, CronService)
        except Exception as e:
            logger.warning("cron service unavailable; trigger cron %s skipped: %s", action, e)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("no running loop; trigger cron %s skipped", action)
            return
        t = loop.create_task(self._run_cron_op(coro_factory(cron_service), job_id, action))
        _pending_cron_tasks.add(t)
        t.add_done_callback(_pending_cron_tasks.discard)

    async def _run_cron_op(self, coro, job_id: str, action: str) -> None:
        """await 一个 cron service 操作并记日志(detached)。"""
        try:
            await coro
            logger.info("cron job %s %sed ok", job_id, action)
        except Exception as e:
            logger.error("cron job %s %s failed: %s", job_id, action, e)

    async def _update_or_add_cron(self, cron_service, job_id: str, patch, req) -> None:
        """update 失败(旧 trigger 尚无 cron job)时 fallback 到 add。"""
        try:
            await cron_service.update_job(job_id, patch)
        except ValueError:
            await cron_service.add_job(req)

    def list_triggers(self, f: TriggerListFilter) -> List[TriggerSourceResponse]:
        return self._dao.list_by_filter(f)

    def get_by_id(self, trigger_id: int) -> Optional[TriggerSourceResponse]:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == trigger_id
            ).first()
            return self._dao.to_response(entity) if entity else None
        finally:
            session.close()

    def fire(self, request: TriggerFireRequest) -> dict:
        """Fire the trigger - create a Task and detached-execute the playbook.

        用 entity.instruction 作为 task.title(指令),创建后 detached 启动
        start + run_task,不阻塞调用方。timer/webhook/alert/手动 fire 四条
        路径统一走这里。返回创建的 task id。
        """
        session = self._dao.get_raw_session()
        try:
            entity = session.query(TriggerSourceEntity).filter(
                TriggerSourceEntity.id == request.trigger_id,
                TriggerSourceEntity.workspace_id == request.workspace_id,
            ).first()
            if not entity:
                raise ValueError(f"trigger {request.trigger_id} not found in workspace {request.workspace_id}")
            if not entity.is_active:
                logger.info("trigger %s inactive; skip fire", entity.id)
                return {"task_id": None, "trigger_id": entity.id, "skipped": True}
            entity.last_fired_at = datetime.now()
            session.commit()

            # Create the Task through task service component
            from derisk_serve.task.service.service import (
                TASK_SERVICE_COMPONENT_NAME, TaskService,
            )
            from derisk_serve.task.api.schemas import TaskRequest

            task_service: TaskService = self._system_app.get_component(
                TASK_SERVICE_COMPONENT_NAME, TaskService,
            )
            task_req = TaskRequest(
                workspace_id=entity.workspace_id,
                type="routine" if entity.type == "timer" else (
                    "incident" if entity.type == "alert" else "adhoc"
                ),
                title=entity.instruction or f"Triggered by {entity.name}",
                description=f"Triggered via {entity.type} (trigger_id={entity.id})",
                status="pending_trigger",
                triggered_by=entity.type,
                trigger_ref=str(entity.id),
                playbook_id=entity.target_playbook_id,
                context={
                    "trigger_payload": request.payload or {},
                    "trigger_config": json.loads(entity.config_json) if entity.config_json else {},
                    "trigger_instruction": entity.instruction,
                },
            )
            task = task_service.create(task_req)
            self._launch_task(task.id)
            return {"task_id": task.id, "trigger_id": entity.id}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
