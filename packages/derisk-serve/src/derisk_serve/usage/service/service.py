"""LLM usage service implementation."""

import logging
from typing import Any, Optional

from derisk.agent.util.llm.usage_recorder import LLMUsageRecord
from derisk.component import SystemApp
from derisk.storage.metadata._base_dao import REQ, RES
from derisk_serve.core import BaseService

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
from ..models.models import LLMUsageEntity, UsageDao

logger = logging.getLogger(__name__)


class Service(BaseService[LLMUsageEntity, Any, Any]):
    """LLM usage service: records per-call usage and serves aggregations."""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[UsageDao] = None,
    ):
        self._config = config
        self._dao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or UsageDao(self._config)

    @property
    def dao(self) -> UsageDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._config

    # ----------------------------------------------------------- recorder hook
    async def insert_usage(self, record: LLMUsageRecord) -> None:
        """Async recorder callback registered to derisk-core.

        Errors are swallowed here (record_llm_usage also wraps), so a DB hiccup
        never affects the LLM call path.
        """
        try:
            self._dao.insert_record(record)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[usage] insert failed model={record.model_name}: {e}")

    # ------------------------------------------------------------------- reads
    def list_calls(self, page: int = 1, page_size: int = 20, **filters) -> UsageListResult:
        return self._dao.list_calls(page=page, page_size=page_size, **filters)

    def overview(self, **filters) -> OverviewVO:
        return self._dao.overview(**filters)

    def aggregate_by_conversation(self, **filters) -> list[ConversationUsageVO]:
        return self._dao.aggregate_by_conversation(**filters)

    def aggregate_by_agent(self, **filters) -> list[AgentUsageVO]:
        return self._dao.aggregate_by_agent(**filters)

    def aggregate_by_model(self, **filters) -> list[ModelUsageVO]:
        return self._dao.aggregate_by_model(**filters)

    def time_series(
        self, start_ms: int, end_ms: int, bucket_sec: int, **filters
    ) -> list[TimeSeriesPointVO]:
        return self._dao.time_series(start_ms, end_ms, bucket_sec, **filters)

    def delete_records(
        self, conv_id: Optional[str] = None, before_ms: Optional[int] = None
    ) -> DeleteResultVO:
        deleted = self._dao.delete_records(conv_id=conv_id, before_ms=before_ms)
        return DeleteResultVO(deleted=deleted)

    def distinct_agents(
        self, start_ms: Optional[int] = None, end_ms: Optional[int] = None
    ) -> list[str]:
        """Get distinct agent_ids from usage records."""
        return self._dao.distinct_agents(start_ms=start_ms, end_ms=end_ms)
