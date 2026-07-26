"""Tests for the LLM usage DAO (insert + aggregations)."""

import pytest

from derisk.agent.util.llm.usage_recorder import LLMUsageRecord
from derisk.storage.metadata import db
from derisk_serve.usage.models.models import LLMUsageEntity, UsageDao


@pytest.fixture
def dao(tmp_path):
    db_path = tmp_path / "usage_test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    return UsageDao()


NOW = 1_700_000_000_000


def _seed(dao: UsageDao):
    for r in [
        LLMUsageRecord(
            model_name="gpt-4o", prompt_tokens=100, completion_tokens=50,
            total_tokens=150, latency_ms=1000, stream=True, started_at=NOW,
            conv_id="conv_a", agent_id="agent1", user_id="u1",
            tokens_per_sec=50.0, error_code=0,
        ),
        LLMUsageRecord(
            model_name="gpt-4o", prompt_tokens=200, completion_tokens=80,
            total_tokens=280, latency_ms=2000, stream=True, started_at=NOW + 60_000,
            conv_id="conv_a", agent_id="agent1", user_id="u1",
            tokens_per_sec=40.0, error_code=0,
        ),
        LLMUsageRecord(
            model_name="glm-4", prompt_tokens=300, completion_tokens=120,
            total_tokens=420, latency_ms=3000, stream=True, started_at=NOW + 120_000,
            conv_id="conv_b", agent_id="agent2", user_id="u1",
            tokens_per_sec=40.0, error_code=1,
        ),
    ]:
        dao.insert_record(r)


def test_overview_aggregation(dao):
    _seed(dao)
    ov = dao.overview()
    assert ov.total_calls == 3
    assert ov.error_calls == 1
    assert ov.prompt_tokens == 600
    assert ov.completion_tokens == 250
    assert ov.total_tokens == 850
    assert abs(ov.avg_latency_ms - 2000.0) < 0.1
    assert ov.cost_usd > 0


def test_aggregate_by_conversation(dao):
    _seed(dao)
    convs = dao.aggregate_by_conversation()
    assert len(convs) == 2
    ca = next(c for c in convs if c.conv_id == "conv_a")
    assert ca.calls == 2 and ca.total_tokens == 430 and ca.error_calls == 0
    cb = next(c for c in convs if c.conv_id == "conv_b")
    assert cb.calls == 1 and cb.total_tokens == 420 and cb.error_calls == 1


def test_aggregate_by_agent(dao):
    _seed(dao)
    agents = dao.aggregate_by_agent()
    a1 = next(a for a in agents if a.agent_id == "agent1")
    assert a1.calls == 2 and a1.total_tokens == 430


def test_aggregate_by_model(dao):
    _seed(dao)
    models = dao.aggregate_by_model()
    m = next(x for x in models if x.model_name == "gpt-4o")
    assert m.calls == 2 and m.total_tokens == 430


def test_time_series_bucketing(dao):
    _seed(dao)
    ts = dao.time_series(start_ms=NOW, end_ms=NOW + 200_000, bucket_sec=60)
    assert len(ts) == 3
    assert sum(t.calls for t in ts) == 3
    assert sum(t.total_tokens for t in ts) == 850


def test_list_calls_pagination_and_filter(dao):
    _seed(dao)
    lst = dao.list_calls(page=1, page_size=2)
    assert lst.total_count == 3 and len(lst.items) == 2
    lst2 = dao.list_calls(page=1, page_size=10, conv_id="conv_a")
    assert lst2.total_count == 2


def test_delete_records(dao):
    _seed(dao)
    deleted = dao.delete_records(conv_id="conv_a")
    assert deleted == 2
    assert dao.overview().total_calls == 1
