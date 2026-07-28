"""LLM usage API endpoints."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..api.schemas import (
    AgentUsageVO,
    ConversationUsageVO,
    DeleteResultVO,
    ModelUsageVO,
    OverviewVO,
    TimeSeriesPointVO,
    UsageListResult,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service

logger = logging.getLogger(__name__)

router = APIRouter()

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance."""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


@router.get("/overview", response_model=Result[OverviewVO])
async def get_overview(
    conv_id: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    model_name: Optional[str] = Query(default=None),
    start_ms: Optional[int] = Query(default=None, description="epoch ms inclusive"),
    end_ms: Optional[int] = Query(default=None, description="epoch ms exclusive"),
    service: Service = Depends(get_service),
) -> Result[OverviewVO]:
    return Result.succ(
        service.overview(
            conv_id=conv_id,
            agent_id=agent_id,
            model_name=model_name,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    )


@router.get("/calls", response_model=Result[UsageListResult])
async def list_calls(
    conv_id: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    model_name: Optional[str] = Query(default=None),
    start_ms: Optional[int] = Query(default=None),
    end_ms: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    service: Service = Depends(get_service),
) -> Result[UsageListResult]:
    return Result.succ(
        service.list_calls(
            page=page,
            page_size=page_size,
            conv_id=conv_id,
            agent_id=agent_id,
            model_name=model_name,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    )


@router.get("/by-conversation", response_model=Result[List[ConversationUsageVO]])
async def by_conversation(
    agent_id: Optional[str] = Query(default=None),
    model_name: Optional[str] = Query(default=None),
    start_ms: Optional[int] = Query(default=None),
    end_ms: Optional[int] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[ConversationUsageVO]]:
    return Result.succ(
        service.aggregate_by_conversation(
            agent_id=agent_id,
            model_name=model_name,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    )


@router.get("/by-agent", response_model=Result[List[AgentUsageVO]])
async def by_agent(
    conv_id: Optional[str] = Query(default=None),
    model_name: Optional[str] = Query(default=None),
    start_ms: Optional[int] = Query(default=None),
    end_ms: Optional[int] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[AgentUsageVO]]:
    return Result.succ(
        service.aggregate_by_agent(
            conv_id=conv_id,
            model_name=model_name,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    )


@router.get("/by-model", response_model=Result[List[ModelUsageVO]])
async def by_model(
    conv_id: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    start_ms: Optional[int] = Query(default=None),
    end_ms: Optional[int] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[ModelUsageVO]]:
    return Result.succ(
        service.aggregate_by_model(
            conv_id=conv_id,
            agent_id=agent_id,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    )


@router.get("/time-series", response_model=Result[List[TimeSeriesPointVO]])
async def time_series(
    start_ms: int = Query(..., description="epoch ms inclusive"),
    end_ms: int = Query(..., description="epoch ms exclusive"),
    bucket_sec: int = Query(..., ge=60, description="bucket size in seconds"),
    conv_id: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    model_name: Optional[str] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[TimeSeriesPointVO]]:
    return Result.succ(
        service.time_series(
            start_ms=start_ms,
            end_ms=end_ms,
            bucket_sec=bucket_sec,
            conv_id=conv_id,
            agent_id=agent_id,
            model_name=model_name,
        )
    )


@router.delete("/records", response_model=Result[DeleteResultVO])
async def delete_records(
    conv_id: Optional[str] = Query(default=None),
    before_ms: Optional[int] = Query(default=None, description="delete records with started_at < before_ms"),
    service: Service = Depends(get_service),
) -> Result[DeleteResultVO]:
    if not conv_id and before_ms is None:
        return Result.failed(msg="Provide conv_id or before_ms to delete records")
    return Result.succ(service.delete_records(conv_id=conv_id, before_ms=before_ms))


@router.get("/distinct-agents", response_model=Result[List[str]])
async def distinct_agents(
    start_ms: Optional[int] = Query(default=None),
    end_ms: Optional[int] = Query(default=None),
    service: Service = Depends(get_service),
) -> Result[List[str]]:
    """Get distinct agent_ids from usage records."""
    return Result.succ(service.distinct_agents(start_ms=start_ms, end_ms=end_ms))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints."""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
