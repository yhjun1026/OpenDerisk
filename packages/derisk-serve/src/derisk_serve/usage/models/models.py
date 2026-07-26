"""LLM usage database entity and DAO."""

import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    desc,
    func,
    case,
)

from derisk.agent.util.llm.usage_recorder import LLMUsageRecord
from derisk.storage.metadata import BaseDao, Model
from derisk.util.pagination_utils import PaginationResult

from ..api.schemas import (
    AgentUsageVO,
    ConversationUsageVO,
    DeleteResultVO,
    ModelUsageVO,
    OverviewVO,
    TimeSeriesPointVO,
    UsageCallVO,
    UsageListResult,
)
from ..config import SERVER_APP_TABLE_NAME, ServeConfig

logger = logging.getLogger(__name__)


class LLMUsageEntity(Model):
    """Database entity for a single LLM call's usage."""

    __tablename__ = SERVER_APP_TABLE_NAME

    id = Column(Integer, primary_key=True, autoincrement=True)
    conv_id = Column(String(128), index=True, nullable=True)
    agent_id = Column(String(128), index=True, nullable=True)
    user_id = Column(String(128), nullable=True)
    session_id = Column(String(128), nullable=True)
    trace_id = Column(String(128), nullable=True)
    model_name = Column(String(128), index=True, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    first_token_ms = Column(Integer, nullable=True)
    tokens_per_sec = Column(Float, nullable=True)
    stream = Column(Integer, default=1)
    error_code = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    started_at = Column(Integer, index=True, nullable=False)
    gmt_created = Column(
        DateTime,
        name="gmt_create",
        default=datetime.now,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_usage_conv_time", "conv_id", "started_at"),
        Index("idx_usage_agent_time", "agent_id", "started_at"),
    )

    def __repr__(self):
        return (
            f"LLMUsageEntity(id={self.id}, model='{self.model_name}', "
            f"conv_id='{self.conv_id}', total_tokens={self.total_tokens}, "
            f"latency_ms={self.latency_ms})"
        )


def _filters_to_dict(
    conv_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    model_name: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> dict:
    return {
        "conv_id": conv_id,
        "agent_id": agent_id,
        "model_name": model_name,
        "start_ms": start_ms,
        "end_ms": end_ms,
    }


class UsageDao(BaseDao[LLMUsageEntity, Any, Any]):
    """Data Access Object for LLM usage records."""

    def __init__(self, serve_config: Optional[ServeConfig] = None):
        super().__init__()
        self._serve_config = serve_config

    # ------------------------------------------------------------------ write
    def insert_record(self, record: LLMUsageRecord) -> None:
        """Insert one LLM call usage record. Sync; called from async recorder."""
        from derisk.agent.core.model_pricing import get_pricing

        prompt_per_1m, completion_per_1m = get_pricing(record.model_name)
        cost = (
            (record.prompt_tokens or 0) * prompt_per_1m / 1_000_000
            + (record.completion_tokens or 0) * completion_per_1m / 1_000_000
        )
        entity = LLMUsageEntity(
            conv_id=record.conv_id,
            agent_id=record.agent_id,
            user_id=record.user_id,
            session_id=record.session_id,
            trace_id=record.trace_id,
            model_name=record.model_name or "unknown",
            prompt_tokens=record.prompt_tokens or 0,
            completion_tokens=record.completion_tokens or 0,
            total_tokens=record.total_tokens or 0,
            latency_ms=record.latency_ms or 0,
            first_token_ms=record.first_token_ms,
            tokens_per_sec=record.tokens_per_sec,
            stream=1 if record.stream else 0,
            error_code=record.error_code or 0,
            cost_usd=cost,
            started_at=record.started_at or 0,
        )
        session = self.get_raw_session()
        try:
            session.add(entity)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------ helpers
    def _apply_filters(self, query, f: dict):
        if f.get("conv_id"):
            query = query.filter(LLMUsageEntity.conv_id == f["conv_id"])
        if f.get("agent_id"):
            query = query.filter(LLMUsageEntity.agent_id == f["agent_id"])
        if f.get("model_name"):
            query = query.filter(LLMUsageEntity.model_name == f["model_name"])
        if f.get("start_ms") is not None:
            query = query.filter(LLMUsageEntity.started_at >= f["start_ms"])
        if f.get("end_ms") is not None:
            query = query.filter(LLMUsageEntity.started_at < f["end_ms"])
        return query

    @staticmethod
    def _to_call_vo(entity: LLMUsageEntity) -> UsageCallVO:
        gmt = entity.gmt_created
        return UsageCallVO(
            id=entity.id,
            conv_id=entity.conv_id,
            agent_id=entity.agent_id,
            user_id=entity.user_id,
            session_id=entity.session_id,
            trace_id=entity.trace_id,
            model_name=entity.model_name,
            prompt_tokens=entity.prompt_tokens or 0,
            completion_tokens=entity.completion_tokens or 0,
            total_tokens=entity.total_tokens or 0,
            latency_ms=entity.latency_ms or 0,
            first_token_ms=entity.first_token_ms,
            tokens_per_sec=entity.tokens_per_sec,
            stream=entity.stream if entity.stream is not None else 1,
            error_code=entity.error_code or 0,
            cost_usd=entity.cost_usd or 0.0,
            started_at=entity.started_at or 0,
            gmt_created=gmt.isoformat() if gmt else None,
        )

    # ------------------------------------------------------------------ reads
    def list_calls(
        self,
        page: int = 1,
        page_size: int = 20,
        **filter_kwargs,
    ) -> UsageListResult:
        f = _filters_to_dict(**filter_kwargs)
        with self.session(commit=False) as session:
            query = session.query(LLMUsageEntity)
            query = self._apply_filters(query, f)
            total = query.count()
            rows = (
                query.order_by(desc(LLMUsageEntity.started_at))
                .offset(max(0, (page - 1)) * page_size)
                .limit(page_size)
                .all()
            )
            items = [self._to_call_vo(r) for r in rows]
        return UsageListResult(
            items=items, total_count=total, page=page, page_size=page_size
        )

    def overview(self, **filter_kwargs) -> OverviewVO:
        f = _filters_to_dict(**filter_kwargs)
        with self.session(commit=False) as session:
            row = self._apply_filters(
                session.query(
                    func.count(LLMUsageEntity.id).label("total_calls"),
                    func.sum(
                        case((LLMUsageEntity.error_code != 0, 1), else_=0)
                    ).label("error_calls"),
                    func.sum(LLMUsageEntity.prompt_tokens).label("prompt_tokens"),
                    func.sum(LLMUsageEntity.completion_tokens).label("completion_tokens"),
                    func.sum(LLMUsageEntity.total_tokens).label("total_tokens"),
                    func.sum(LLMUsageEntity.cost_usd).label("cost_usd"),
                    func.avg(LLMUsageEntity.latency_ms).label("avg_latency_ms"),
                    func.avg(LLMUsageEntity.tokens_per_sec).label("avg_tokens_per_sec"),
                ),
                f,
            ).first()
        if not row or row.total_calls == 0:
            return OverviewVO()
        return OverviewVO(
            total_calls=int(row.total_calls or 0),
            error_calls=int(row.error_calls or 0),
            prompt_tokens=int(row.prompt_tokens or 0),
            completion_tokens=int(row.completion_tokens or 0),
            total_tokens=int(row.total_tokens or 0),
            cost_usd=float(row.cost_usd or 0.0),
            avg_latency_ms=float(row.avg_latency_ms) if row.avg_latency_ms is not None else None,
            avg_tokens_per_sec=float(row.avg_tokens_per_sec)
            if row.avg_tokens_per_sec is not None
            else None,
        )

    def aggregate_by_conversation(self, **filter_kwargs) -> List[ConversationUsageVO]:
        f = _filters_to_dict(**filter_kwargs)
        with self.session(commit=False) as session:
            rows = (
                self._apply_filters(
                    session.query(
                        LLMUsageEntity.conv_id.label("conv_id"),
                        func.max(LLMUsageEntity.agent_id).label("agent_id"),
                        func.count(LLMUsageEntity.id).label("calls"),
                        func.sum(
                            case((LLMUsageEntity.error_code != 0, 1), else_=0)
                        ).label("error_calls"),
                        func.sum(LLMUsageEntity.prompt_tokens).label("prompt_tokens"),
                        func.sum(LLMUsageEntity.completion_tokens).label("completion_tokens"),
                        func.sum(LLMUsageEntity.total_tokens).label("total_tokens"),
                        func.sum(LLMUsageEntity.cost_usd).label("cost_usd"),
                        func.avg(LLMUsageEntity.latency_ms).label("avg_latency_ms"),
                        func.avg(LLMUsageEntity.tokens_per_sec).label("avg_tokens_per_sec"),
                    ),
                    f,
                )
                .filter(LLMUsageEntity.conv_id.isnot(None))
                .group_by(LLMUsageEntity.conv_id)
                .order_by(desc("total_tokens"))
                .all()
            )
        return [
            ConversationUsageVO(
                conv_id=r.conv_id,
                agent_id=r.agent_id,
                calls=int(r.calls or 0),
                error_calls=int(r.error_calls or 0),
                prompt_tokens=int(r.prompt_tokens or 0),
                completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                cost_usd=float(r.cost_usd or 0.0),
                avg_latency_ms=float(r.avg_latency_ms) if r.avg_latency_ms is not None else None,
                avg_tokens_per_sec=float(r.avg_tokens_per_sec)
                if r.avg_tokens_per_sec is not None
                else None,
            )
            for r in rows
        ]

    def aggregate_by_agent(self, **filter_kwargs) -> List[AgentUsageVO]:
        f = _filters_to_dict(**filter_kwargs)
        with self.session(commit=False) as session:
            rows = (
                self._apply_filters(
                    session.query(
                        func.coalesce(LLMUsageEntity.agent_id, "unknown").label("agent_id"),
                        func.count(LLMUsageEntity.id).label("calls"),
                        func.sum(
                            case((LLMUsageEntity.error_code != 0, 1), else_=0)
                        ).label("error_calls"),
                        func.sum(LLMUsageEntity.prompt_tokens).label("prompt_tokens"),
                        func.sum(LLMUsageEntity.completion_tokens).label("completion_tokens"),
                        func.sum(LLMUsageEntity.total_tokens).label("total_tokens"),
                        func.sum(LLMUsageEntity.cost_usd).label("cost_usd"),
                        func.avg(LLMUsageEntity.latency_ms).label("avg_latency_ms"),
                        func.avg(LLMUsageEntity.tokens_per_sec).label("avg_tokens_per_sec"),
                    ),
                    f,
                )
                .group_by("agent_id")
                .order_by(desc("total_tokens"))
                .all()
            )
        return [
            AgentUsageVO(
                agent_id=r.agent_id,
                calls=int(r.calls or 0),
                error_calls=int(r.error_calls or 0),
                prompt_tokens=int(r.prompt_tokens or 0),
                completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                cost_usd=float(r.cost_usd or 0.0),
                avg_latency_ms=float(r.avg_latency_ms) if r.avg_latency_ms is not None else None,
                avg_tokens_per_sec=float(r.avg_tokens_per_sec)
                if r.avg_tokens_per_sec is not None
                else None,
            )
            for r in rows
        ]

    def aggregate_by_model(self, **filter_kwargs) -> List[ModelUsageVO]:
        f = _filters_to_dict(**filter_kwargs)
        with self.session(commit=False) as session:
            rows = (
                self._apply_filters(
                    session.query(
                        LLMUsageEntity.model_name.label("model_name"),
                        func.count(LLMUsageEntity.id).label("calls"),
                        func.sum(
                            case((LLMUsageEntity.error_code != 0, 1), else_=0)
                        ).label("error_calls"),
                        func.sum(LLMUsageEntity.prompt_tokens).label("prompt_tokens"),
                        func.sum(LLMUsageEntity.completion_tokens).label("completion_tokens"),
                        func.sum(LLMUsageEntity.total_tokens).label("total_tokens"),
                        func.sum(LLMUsageEntity.cost_usd).label("cost_usd"),
                        func.avg(LLMUsageEntity.latency_ms).label("avg_latency_ms"),
                        func.avg(LLMUsageEntity.tokens_per_sec).label("avg_tokens_per_sec"),
                    ),
                    f,
                )
                .group_by(LLMUsageEntity.model_name)
                .order_by(desc("total_tokens"))
                .all()
            )
        return [
            ModelUsageVO(
                model_name=r.model_name,
                calls=int(r.calls or 0),
                error_calls=int(r.error_calls or 0),
                prompt_tokens=int(r.prompt_tokens or 0),
                completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                cost_usd=float(r.cost_usd or 0.0),
                avg_latency_ms=float(r.avg_latency_ms) if r.avg_latency_ms is not None else None,
                avg_tokens_per_sec=float(r.avg_tokens_per_sec)
                if r.avg_tokens_per_sec is not None
                else None,
            )
            for r in rows
        ]

    def time_series(
        self,
        start_ms: int,
        end_ms: int,
        bucket_sec: int,
        **filter_kwargs,
    ) -> List[TimeSeriesPointVO]:
        """Bucket calls into time intervals. bucket via (started_at - started_at % size)."""
        f = _filters_to_dict(
            start_ms=start_ms,
            end_ms=end_ms,
            conv_id=filter_kwargs.get("conv_id"),
            agent_id=filter_kwargs.get("agent_id"),
            model_name=filter_kwargs.get("model_name"),
        )
        bucket_size_ms = max(1, int(bucket_sec)) * 1000
        bucket_expr = LLMUsageEntity.started_at - (
            LLMUsageEntity.started_at % bucket_size_ms
        )
        with self.session(commit=False) as session:
            rows = (
                self._apply_filters(
                    session.query(
                        bucket_expr.label("bucket_ms"),
                        func.count(LLMUsageEntity.id).label("calls"),
                        func.sum(LLMUsageEntity.prompt_tokens).label("prompt_tokens"),
                        func.sum(LLMUsageEntity.completion_tokens).label("completion_tokens"),
                        func.sum(LLMUsageEntity.total_tokens).label("total_tokens"),
                        func.sum(LLMUsageEntity.cost_usd).label("cost_usd"),
                    ),
                    f,
                )
                .group_by("bucket_ms")
                .order_by("bucket_ms")
                .all()
            )
        return [
            TimeSeriesPointVO(
                bucket_ms=int(r.bucket_ms or 0),
                calls=int(r.calls or 0),
                prompt_tokens=int(r.prompt_tokens or 0),
                completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
                cost_usd=float(r.cost_usd or 0.0),
            )
            for r in rows
        ]

    def delete_records(
        self,
        conv_id: Optional[str] = None,
        before_ms: Optional[int] = None,
    ) -> int:
        with self.session() as session:
            q = session.query(LLMUsageEntity)
            if conv_id:
                q = q.filter(LLMUsageEntity.conv_id == conv_id)
            if before_ms is not None:
                q = q.filter(LLMUsageEntity.started_at < before_ms)
            count = q.count()
            q.delete(synchronize_session=False)
        return int(count)
