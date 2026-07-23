"""Integration test: playbook update must persist to DB.

Regression for the chained ``self._dao.get_raw_session().commit()`` bug:
``db._session`` is a ``sessionmaker`` (not ``scoped_session``), so each
``get_raw_session()`` returns a *fresh* session. The old update() queried
``existing`` from session A but committed session B (empty), so ``existing``'s
changes were never persisted -- the API returned in-memory new values and the
page showed "Saved", but reopening showed stale data.
"""
import json
from unittest.mock import MagicMock

import pytest

from derisk.storage.metadata import db
from derisk_serve.playbook.api.schemas import PlaybookRequest
from derisk_serve.playbook.models.models import PlaybookDao, PlaybookVersionDao
from derisk_serve.playbook.service.service import PlaybookService


@pytest.fixture
def playbook_service(tmp_path):
    db.init_db(f"sqlite:///{tmp_path / 't.db'}")
    db.create_all()
    svc = PlaybookService(MagicMock(), MagicMock())
    svc._dao = PlaybookDao()
    svc._version_dao = PlaybookVersionDao()
    svc._system_app = MagicMock()
    return svc


DECL = {
    "text_content": {"goal": "original", "workflow": "s1"},
    "skills": ["db_query_skill"],
    "context": {"assets_required": [], "resources": []},
    "deliverables": [{"type": "report", "delivery": []}],
    "distill": {
        "forced": True,
        "produce": [{"type": "historical_artifact", "from": "deliverable.0"}],
    },
}


def test_update_persists_declaration_and_bumps_version(playbook_service):
    created = playbook_service.create(PlaybookRequest(
        workspace_id=1, name="t", scenario_type="sre", task_type="routine",
        trigger={}, declaration=DECL, is_active=True,
    ))
    pid = created.id

    edited = json.loads(json.dumps(DECL))
    edited["text_content"]["goal"] = "EDITED"
    playbook_service.update(PlaybookRequest(
        id=pid, workspace_id=1, name="t", scenario_type="sre", task_type="routine",
        trigger={}, declaration=edited, is_active=True,
    ))

    # Re-read from a fresh session: must reflect the persisted edit, not stale data.
    refetched = playbook_service.get_by_id(pid)
    assert refetched is not None
    assert refetched.current_version == 2
    assert refetched.declaration["text_content"]["goal"] == "EDITED"

    versions = playbook_service.list_versions(pid)
    assert [v.version for v in versions] == [2, 1]
