"""Integration tests for the usage Serve lifecycle + recorder wiring."""

import asyncio

import pytest
from fastapi import FastAPI

from derisk.agent.util.llm.usage_recorder import (
    LLMUsageRecord,
    clear_llm_usage_recorders,
    record_llm_usage,
)
from derisk.component import SystemApp
from derisk.storage.metadata import db
from derisk_serve.usage.config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from derisk_serve.usage.models.models import LLMUsageEntity
from derisk_serve.usage.serve import Serve
from derisk_serve.usage.service.service import Service


@pytest.fixture
def system_app(tmp_path):
    db.init_db(f"sqlite:///{tmp_path}/serve.db")
    app = FastAPI()
    sa = SystemApp(asgi_app=app)
    serve = Serve(sa, config=ServeConfig())
    serve.on_init()
    serve.init_app(sa)
    serve.before_start()
    yield sa
    clear_llm_usage_recorders()


def test_router_mounted(system_app):
    paths = {getattr(r, "path", "") for r in system_app.app.routes}
    assert "/api/v1/serve/usage/overview" in paths
    assert "/api/v1/serve/usage/calls" in paths
    assert "/api/v1/serve/usage/by-agent" in paths
    assert "/api/v1/serve/usage/by-model" in paths
    assert "/api/v1/serve/usage/by-conversation" in paths
    assert "/api/v1/serve/usage/time-series" in paths
    assert "/api/v1/serve/usage/records" in paths


def test_table_created(system_app):
    # If the table didn't exist, this query would raise. Counting 0 confirms it.
    with db.session() as s:
        assert s.query(LLMUsageEntity).count() == 0


def test_recorder_registered_and_writes(system_app):
    svc = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)
    assert svc is not None
    # before_start registered svc.insert_usage as a recorder; dispatch writes a row.
    asyncio.run(
        record_llm_usage(
            LLMUsageRecord(
                model_name="gpt-4o",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                latency_ms=100,
                stream=True,
                started_at=1_700_000_000_000,
                conv_id="c1",
                agent_id="a1",
            )
        )
    )
    with db.session() as s:
        rows = s.query(LLMUsageEntity).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.total_tokens == 15
        assert row.conv_id == "c1"
        assert row.model_name == "gpt-4o"
        assert row.agent_id == "a1"
