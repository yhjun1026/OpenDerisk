"""Integration test: artifact update must persist to DB.

Regression for the same chained ``self._dao.get_raw_session().commit()`` bug
as playbook update -- ``db._session`` is a ``sessionmaker`` (not
``scoped_session``), so each ``get_raw_session()`` returns a fresh session and
the old update() committed a different empty session, losing the edit.
"""
from unittest.mock import MagicMock

import pytest

from derisk.storage.metadata import db
from derisk_serve.artifact.api.schemas import ArtifactRequest
from derisk_serve.artifact.models.models import ArtifactDao, ArtifactVersionDao
from derisk_serve.artifact.service.service import ArtifactService


@pytest.fixture
def artifact_service(tmp_path):
    db.init_db(f"sqlite:///{tmp_path / 't.db'}")
    db.create_all()
    svc = ArtifactService(MagicMock(), MagicMock())
    svc._dao = ArtifactDao()
    svc._version_dao = ArtifactVersionDao()
    svc._system_app = MagicMock()
    return svc


def test_update_persists_title_and_bumps_version(artifact_service):
    created = artifact_service.create(ArtifactRequest(
        task_id=1, workspace_id=1, type="report", title="original",
        content_ref="ref-1",
    ))
    aid = created.id

    artifact_service.update(ArtifactRequest(
        id=aid, task_id=1, workspace_id=1, type="report", title="EDITED",
        content_ref="ref-2",
    ))

    # Re-read from a fresh session: must reflect the persisted edit, not stale data.
    refetched = artifact_service.get_by_id(aid)
    assert refetched is not None
    assert refetched.current_version == 2
    assert refetched.title == "EDITED"
    assert refetched.content_ref == "ref-2"

    versions = artifact_service.list_versions(aid)
    assert [v.version for v in versions] == [2, 1]
