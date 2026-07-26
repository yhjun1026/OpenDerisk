"""Tests for TaskService.delete (hard delete + relation cleanup)."""
import pytest

from derisk.storage.metadata import db
from derisk_serve.task.api.schemas import TaskRequest
from derisk_serve.task.config import ServeConfig
from derisk_serve.task.models.models import (
    TaskDao, TaskEntity, TaskRelationEntity,
)
from derisk_serve.task.service.service import TaskService


@pytest.fixture
def service(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    return TaskService(None, ServeConfig(), TaskDao())


def _create(service: TaskService, title: str = "task"):
    return service.create(TaskRequest(workspace_id=1, title=title))


def test_delete_removes_task(service):
    task = _create(service)
    service.delete(task.id)
    assert service.get_by_id(task.id) is None


def test_delete_cleans_relation_rows(service):
    parent = _create(service, "parent")
    child = service.spawn(parent.id, TaskRequest(workspace_id=1, title="child"))

    service.delete(parent.id)
    service.delete(child.id)

    with db.session() as session:
        assert session.query(TaskRelationEntity).count() == 0
        assert session.query(TaskEntity).count() == 0


def test_delete_missing_task_raises(service):
    with pytest.raises(ValueError, match="not found"):
        service.delete(999)


def test_terminate_transition_running_to_closed(service):
    task = _create(service)
    service.start(task.id)
    closed = service.transition(task.id, "closed")
    assert closed.status == "closed"
    assert closed.closed_at is not None
