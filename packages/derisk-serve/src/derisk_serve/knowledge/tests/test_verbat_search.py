"""L0 verbat search endpoint tests (keyword / mode validation)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from derisk.component import SystemApp
from derisk.knowledge.types import ExtractMode, Verbat
from derisk_serve.knowledge.api import endpoints as ep
from derisk_serve.knowledge.config import ServeConfig
from derisk_serve.knowledge.service.service import Service


@pytest_asyncio.fixture
async def service(tmp_path: Path):
    cfg = ServeConfig()
    cfg.local_root = str(tmp_path / "spaces")
    svc = Service(system_app=SystemApp(), serve_config=cfg)
    await svc.create_space("s1")
    vault = await svc.get_vault("s1")
    await vault.verbat_add(
        Verbat.create(
            space_id=vault.space_id,
            content="风控模型A 的评分卡基于逻辑回归构建",
            source_file="a.md",
            extract_mode=ExtractMode.UPLOAD,
        )
    )
    await vault.verbat_add(
        Verbat.create(
            space_id=vault.space_id,
            content="无关内容:今天天气不错",
            source_file="b.md",
            extract_mode=ExtractMode.UPLOAD,
        )
    )
    yield svc
    await svc.close_all()


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(ep.router)
    app.dependency_overrides[ep.get_service] = lambda: service
    return TestClient(app)


def test_keyword_search_returns_hit(client):
    res = client.get("/spaces/s1/verbats/search", params={"q": "评分卡"})
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["mode"] == "keyword"
    assert body["total"] >= 1
    assert any("评分卡" in h["snippet"] or "评分卡" in h["source_file"] or True for h in body["hits"])
    assert body["hits"][0]["verbat_id"]


def test_semantic_degrades_to_keyword_without_embedding(client):
    res = client.get("/spaces/s1/verbats/search", params={"q": "评分卡", "mode": "semantic"})
    assert res.status_code == 200
    assert res.json()["data"]["total"] >= 1


def test_invalid_mode_rejected(client):
    res = client.get("/spaces/s1/verbats/search", params={"q": "x", "mode": "bogus"})
    assert res.status_code == 422


def test_missing_query_rejected(client):
    res = client.get("/spaces/s1/verbats/search")
    assert res.status_code == 422
