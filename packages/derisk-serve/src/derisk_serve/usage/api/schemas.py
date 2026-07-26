"""LLM usage API schemas (view objects)."""

from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field


class UsageCallVO(BaseModel):
    """Single LLM call record."""

    model_config = ConfigDict(title="LLMUsageCall")

    id: int
    conv_id: Optional[str] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    model_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    first_token_ms: Optional[int] = None
    tokens_per_sec: Optional[float] = None
    stream: int = 1
    error_code: int = 0
    cost_usd: float = 0.0
    started_at: int = 0
    gmt_created: Optional[str] = None


class ConversationUsageVO(BaseModel):
    """Aggregated usage per conversation."""

    model_config = ConfigDict(title="ConversationUsage")

    conv_id: str
    agent_id: Optional[str] = None
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: Optional[float] = None
    avg_tokens_per_sec: Optional[float] = None
    error_calls: int = 0


class AgentUsageVO(BaseModel):
    """Aggregated usage per agent."""

    model_config = ConfigDict(title="AgentUsage")

    agent_id: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: Optional[float] = None
    avg_tokens_per_sec: Optional[float] = None
    error_calls: int = 0


class ModelUsageVO(BaseModel):
    """Aggregated usage per model."""

    model_config = ConfigDict(title="ModelUsage")

    model_name: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: Optional[float] = None
    avg_tokens_per_sec: Optional[float] = None
    error_calls: int = 0


class OverviewVO(BaseModel):
    """Overall usage statistics for a filter range."""

    model_config = ConfigDict(title="LLMUsageOverview")

    total_calls: int = 0
    error_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: Optional[float] = None
    avg_tokens_per_sec: Optional[float] = None


class TimeSeriesPointVO(BaseModel):
    """One bucket of a time-series."""

    model_config = ConfigDict(title="LLMUsageTimeSeriesPoint")

    bucket_ms: int
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class UsageListResult(BaseModel):
    """Paginated call list result."""

    model_config = ConfigDict(title="LLMUsageListResult")

    items: List[UsageCallVO] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20


class DeleteResultVO(BaseModel):
    """Result of a delete operation."""

    model_config = ConfigDict(title="LLMUsageDeleteResult")

    deleted: int = 0
