"""HTTP auth chain tests — visibility filtering, owner checks, api_keys.

Conventions under test (see knowledge/api/auth.py):
- permissions plugin OFF (single-machine): no filtering, no owner written.
- permissions plugin ON: private spaces hidden from non-owners (404),
  shared/public read-only for non-owners (403 on write), owner recorded
  at create time.
- ServeConfig.api_keys non-empty → Bearer token required on every route.

The permissions plugin is toggled by patching `_is_permissions_enabled`
in the consuming modules; users are injected via dependency_overrides on
`get_user_from_headers`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from derisk.component import SystemApp
from derisk_serve.knowledge.api import endpoints as ep
from derisk_serve.knowledge.api import auth as auth_mod
from derisk_serve.knowledge.config import ServeConfig
from derisk_serve.knowledge.service.service import Service
from derisk_serve.utils.auth import UserRequest, get_user_from_headers


def _user(user_id: str, role: str = "normal") -> UserRequest:
    return UserRequest(user_id=user_id, role=role)


@pytest_asyncio.fixture
async def service(tmp_path: Path):
    cfg = ServeConfig()
    cfg.local_root = str(tmp_path / "spaces")
    svc = Service(system_app=SystemApp(), serve_config=cfg)
    # alice's private space, a shared space owned by alice, and a legacy
    # space with no owner (pre-auth behavior).
    await svc.create_space("alice-private", owner_id="alice", visibility="private")
    await svc.create_space("alice-shared", owner_id="alice", visibility="shared")
    await svc.create_space("legacy")
    yield svc
    await svc.close_all()


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(ep.router)
    app.dependency_overrides[ep.get_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def plugin_on(monkeypatch):
    """Simulate the permissions feature plugin being enabled."""
    monkeypatch.setattr(ep, "_is_permissions_enabled", lambda: True)
    monkeypatch.setattr(auth_mod, "_is_permissions_enabled", lambda: True)


def _as(client, user: UserRequest):
    client.app.dependency_overrides[get_user_from_headers] = lambda: user


# ---------------------------------------------------------------------------
# Plugin off (single-machine) — behavior unchanged
# ---------------------------------------------------------------------------


def test_plugin_off_lists_all_spaces(client, service):
    r = client.get("/spaces")
    assert r.status_code == 200
    slugs = {s["slug"] for s in r.json()["data"]}
    assert {"alice-private", "alice-shared", "legacy"} <= slugs


def test_plugin_off_no_owner_written(client, service):
    r = client.post("/spaces", json={"slug": "anon-space"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_id"] in (None, "")


def test_plugin_off_private_space_open_to_all(client):
    r = client.get("/spaces/alice-private/docs")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Plugin on — visibility + ownership enforced
# ---------------------------------------------------------------------------


def test_plugin_on_list_filters_private(client, service, plugin_on):
    _as(client, _user("bob"))
    r = client.get("/spaces")
    assert r.status_code == 200
    slugs = {s["slug"] for s in r.json()["data"]}
    assert "alice-private" not in slugs
    assert "alice-shared" in slugs
    assert "legacy" in slugs  # legacy (ownerless) stays visible


def test_plugin_on_private_space_hidden_from_non_owner(client, plugin_on):
    _as(client, _user("bob"))
    r = client.get("/spaces/alice-private/docs")
    assert r.status_code == 404
    _as(client, _user("alice"))
    r = client.get("/spaces/alice-private/docs")
    assert r.status_code == 200


def test_plugin_on_shared_space_read_only_for_non_owner(client, plugin_on):
    _as(client, _user("bob"))
    assert client.get("/spaces/alice-shared/docs").status_code == 200
    r = client.post(
        "/spaces/alice-shared/docs",
        json={"path": "concepts/x.md", "content": "---\ntype: concept\ntitle: X\n---\n\nx\n"},
    )
    assert r.status_code == 403
    _as(client, _user("alice"))
    r = client.post(
        "/spaces/alice-shared/docs",
        json={"path": "concepts/x.md", "content": "---\ntype: concept\ntitle: X\n---\n\nx\n"},
    )
    assert r.status_code == 200


def test_plugin_on_admin_bypasses(client, plugin_on):
    _as(client, _user("carol", role="admin"))
    assert client.get("/spaces/alice-private/docs").status_code == 200


def test_plugin_on_create_records_owner(client, service, plugin_on):
    _as(client, _user("dave"))
    r = client.post("/spaces", json={"slug": "dave-space"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["owner_id"] == "dave"
    assert r.json()["data"]["visibility"] == "private"


def test_plugin_on_patch_delete_require_owner(client, plugin_on):
    _as(client, _user("bob"))
    assert client.patch("/spaces/alice-shared", json={}).status_code == 403
    assert client.delete("/spaces/alice-shared").status_code == 403
    _as(client, _user("alice"))
    assert client.patch("/spaces/alice-shared", json={}).status_code == 200


# ---------------------------------------------------------------------------
# api_keys (datasource convention)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def keyed_client(tmp_path: Path):
    cfg = ServeConfig()
    cfg.local_root = str(tmp_path / "spaces")
    cfg.api_keys = "k1,k2"
    svc = Service(system_app=SystemApp(), serve_config=cfg)
    app = FastAPI()
    app.include_router(ep.router)
    app.dependency_overrides[ep.get_service] = lambda: svc
    yield TestClient(app)
    await svc.close_all()


def test_api_keys_required_when_configured(keyed_client):
    assert keyed_client.get("/spaces").status_code == 401
    r = keyed_client.get(
        "/spaces", headers={"Authorization": "Bearer nope"}
    )
    assert r.status_code == 401
    r = keyed_client.get("/spaces", headers={"Authorization": "Bearer k2"})
    assert r.status_code == 200
