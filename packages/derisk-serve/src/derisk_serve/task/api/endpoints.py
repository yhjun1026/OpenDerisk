"""Task API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from .schemas import (
    TaskCloseRequest, TaskListFilter, TaskRequest, TaskResponse,
)
from ..config import ServeConfig
from ..service.service import TASK_SERVICE_COMPONENT_NAME, TaskService as Service
from derisk_serve.agent.agents.controller import multi_agents
from derisk_serve.playbook import runtime as playbook_runtime

router = APIRouter()
global_system_app: Optional[SystemApp] = None
logger = logging.getLogger(__name__)


def get_service() -> Service:
    if global_system_app is None:
        raise HTTPException(status_code=500, detail="System app not initialized")
    return global_system_app.get_component(TASK_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: Service = Depends(get_service),
) -> Optional[str]:
    if service.config.api_keys:
        api_keys = [k.strip() for k in service.config.api_keys.split(",")]
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(status_code=401, detail="invalid api key")
        return token
    return None


@router.post("/tasks/create", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def create_task(
    request: TaskRequest, service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    try:
        return Result.succ(service.create(request))
    except Exception as e:
        logger.exception("task create exception!")
        return Result.failed(str(e))


@router.post("/tasks/list", response_model=Result,
             dependencies=[Depends(check_api_key)])
async def list_tasks(
    f: TaskListFilter, service: Service = Depends(get_service),
) -> Result:
    try:
        return Result.succ(service.list_tasks(f))
    except Exception as e:
        logger.exception("task list exception!")
        return Result.failed(str(e))


@router.get("/tasks/info", response_model=Result[TaskResponse],
            dependencies=[Depends(check_api_key)])
async def get_task(
    task_id: int = Query(...), service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    try:
        result = service.get_by_id(task_id)
        if not result:
            return Result.failed(f"task {task_id} not found")
        return Result.succ(result)
    except Exception as e:
        logger.exception("task info exception!")
        return Result.failed(str(e))


@router.post("/tasks/update", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def update_task(
    request: TaskRequest, service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    try:
        return Result.succ(service.update(request))
    except Exception as e:
        logger.exception("task update exception!")
        return Result.failed(str(e))


@router.post("/tasks/{task_id}/start", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def start_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    try:
        result = service.start(task_id)
        # If the task is bound to a playbook, launch the playbook runtime
        # in the background to drive the Agent to completion.
        if result and result.playbook_id:
            background_tasks.add_task(
                playbook_runtime.run_task,
                service._system_app,
                task_id,
            )
        return Result.succ(result)
    except Exception as e:
        logger.exception("task start exception!")
        return Result.failed(str(e))


@router.post("/tasks/{task_id}/terminate", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def terminate_task(
    task_id: int,
    service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    """终止任务:停止对应 Agent 运行(与 /v1/chat/stop 同语义),状态转为 closed。"""
    try:
        task = service.get_by_id(task_id)
        if not task:
            return Result.failed(f"task {task_id} not found")
        if task.status not in ("running", "awaiting_human"):
            return Result.failed(f"task status {task.status} cannot be terminated")
        if task.conv_session_id:
            try:
                await multi_agents.stop_chat(task.conv_session_id)
            except Exception as e:
                logger.warning(f"stop agent chat failed for task {task_id}: {e}")
        return Result.succ(service.transition(task_id, "closed"))
    except Exception as e:
        logger.exception("task terminate exception!")
        return Result.failed(str(e))


@router.post("/tasks/{task_id}/delete", response_model=Result[bool],
             dependencies=[Depends(check_api_key)])
async def delete_task(
    task_id: int,
    service: Service = Depends(get_service),
) -> Result[bool]:
    """删除任务记录。运行中/待介入的任务需先终止。"""
    try:
        task = service.get_by_id(task_id)
        if not task:
            return Result.failed(f"task {task_id} not found")
        if task.status in ("running", "awaiting_human"):
            return Result.failed("task is active — terminate it before delete")
        service.delete(task_id)
        return Result.succ(True)
    except Exception as e:
        logger.exception("task delete exception!")
        return Result.failed(str(e))


@router.post("/tasks/close", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def close_task(
    request: TaskCloseRequest, service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    try:
        return Result.succ(service.close(request))
    except ValueError as e:
        # distill enforcement
        return Result.failed(msg=str(e), err_code="E4091")
    except Exception as e:
        logger.exception("task close exception!")
        return Result.failed(str(e))


@router.post("/tasks/{task_id}/archive", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def archive_task(
    task_id: int, service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    try:
        return Result.succ(service.archive(task_id))
    except Exception as e:
        logger.exception("task archive exception!")
        return Result.failed(str(e))


@router.post("/tasks/{parent_task_id}/spawn", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def spawn_task(
    parent_task_id: int,
    request: TaskRequest,
    relation_type: str = Query("spawned_by"),
    service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    try:
        return Result.succ(service.spawn(parent_task_id, request, relation_type))
    except Exception as e:
        logger.exception("task spawn exception!")
        return Result.failed(str(e))


@router.post("/tasks/{task_id}/reassign", response_model=Result[TaskResponse],
             dependencies=[Depends(check_api_key)])
async def reassign_task(
    task_id: int,
    request: dict,
    service: Service = Depends(get_service),
) -> Result[TaskResponse]:
    """转交任务:改 assignee + 新负责人待办出现 + 原 assignee 待办消除。"""
    try:
        new_assignee = request.get("assignee_user_id")
        if not new_assignee:
            return Result.failed("assignee_user_id is required")
        return Result.succ(service.reassign(task_id, int(new_assignee)))
    except Exception as e:
        logger.exception("task reassign exception!")
        return Result.failed(str(e))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
