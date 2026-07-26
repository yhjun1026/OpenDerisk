"""Tests for ServeDao: toolCall payload round-trip persistence."""
import pytest

from derisk.storage.metadata import db
from derisk_serve.cron.api.schemas import (
    CronPayloadSchema,
    CronScheduleSchema,
    ServeRequest,
)
from derisk_serve.cron.config import ServeConfig
from derisk_serve.cron.models.models import CronJobEntity, ServeDao


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    with db.session() as session:
        yield session


def test_toolcall_payload_roundtrip(db_session):
    dao = ServeDao(ServeConfig())
    req = ServeRequest(
        name="daily-call",
        schedule=CronScheduleSchema(kind="every", every_ms=60000),
        payload=CronPayloadSchema(
            kind="toolCall",
            tool_name="call_agent",
            tool_args={"agent_id": "x", "message": "hi"},
        ),
    )
    entity = dao.from_request(req)
    db_session.add(entity)
    db_session.commit()

    fetched = db_session.query(CronJobEntity).first()
    assert fetched is not None
    assert fetched.payload_kind == "toolCall"
    assert fetched.payload_data["tool_name"] == "call_agent"
    assert fetched.payload_data["tool_args"] == {"agent_id": "x", "message": "hi"}

    # Round-trip via to_request
    req2 = dao.to_request(fetched)
    assert req2.payload.kind == "toolCall"
    assert req2.payload.tool_name == "call_agent"
    assert req2.payload.tool_args == {"agent_id": "x", "message": "hi"}


def test_agentturn_payload_roundtrip_unchanged(db_session):
    """Existing agentTurn payload still round-trips correctly (no regression)."""
    dao = ServeDao(ServeConfig())
    req = ServeRequest(
        name="reminder",
        schedule=CronScheduleSchema(kind="cron", expr="0 9 * * *"),
        payload=CronPayloadSchema(
            kind="agentTurn",
            message="do check",
            agent_id="baize",
            session_mode="shared",
        ),
    )
    entity = dao.from_request(req)
    db_session.add(entity)
    db_session.commit()

    fetched = db_session.query(CronJobEntity).first()
    req2 = dao.to_request(fetched)
    assert req2.payload.kind == "agentTurn"
    assert req2.payload.message == "do check"
    assert req2.payload.agent_id == "baize"
    assert req2.payload.tool_name is None


def test_user_id_roundtrip(db_session):
    """#4: created_by_user_id persists and round-trips."""
    dao = ServeDao(ServeConfig())
    req = ServeRequest(
        name="job-with-owner",
        schedule=CronScheduleSchema(kind="every", every_ms=60000),
        payload=CronPayloadSchema(kind="toolCall", tool_name="call_agent"),
        user_id="user-77",
    )
    entity = dao.from_request(req)
    db_session.add(entity)
    db_session.commit()

    fetched = db_session.query(CronJobEntity).first()
    assert fetched.created_by_user_id == "user-77"

    resp = dao.to_response(fetched)
    assert resp.user_id == "user-77"


def test_update_preserves_user_id_when_not_provided(db_session):
    """#4: update without user_id keeps the original creator (e.g. disable)."""
    dao = ServeDao(ServeConfig())
    req = ServeRequest(
        name="job",
        schedule=CronScheduleSchema(kind="every", every_ms=60000),
        payload=CronPayloadSchema(kind="agentTurn", message="hi"),
        user_id="creator-1",
    )
    entity = dao.from_request(req)
    db_session.add(entity)
    db_session.commit()

    # Update without user_id (e.g. disable job)
    patch_req = ServeRequest(
        name="job",
        enabled=False,
        schedule=CronScheduleSchema(kind="every", every_ms=60000),
        payload=CronPayloadSchema(kind="agentTurn", message="hi"),
    )
    dao.update_entity_from_request(entity, patch_req)
    db_session.commit()

    fetched = db_session.query(CronJobEntity).first()
    assert fetched.created_by_user_id == "creator-1"  # preserved


def test_migration_idempotent(db_session):
    """#4: _migrate_v2 is idempotent (re-calling doesn't error, column stays)."""
    dao = ServeDao(ServeConfig())
    # __init__ already ran _migrate_v2 once; call again explicitly twice
    dao._migrate_v2()
    dao._migrate_v2()

    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(db_session.bind)
    cols = {c["name"] for c in insp.get_columns(CronJobEntity.__tablename__)}
    assert "created_by_user_id" in cols
