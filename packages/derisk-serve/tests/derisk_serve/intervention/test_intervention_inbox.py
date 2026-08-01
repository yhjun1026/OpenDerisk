"""P1 tests: Intervention 创建/终结 -> 待办收件箱闭环。

验证:
  - Intervention 创建(assignee 有值)-> assignee 待办出现
  - Intervention resolve -> 待办消除
  - Intervention abort -> 待办消除
"""
from unittest.mock import MagicMock

import pytest

from derisk.storage.metadata import db
from derisk_serve.intervention.api.schemas import (
    InterventionRequest,
    InterventionResolveRequest,
)
from derisk_serve.intervention.service.service import InterventionService
from derisk_serve.workspace.inbox import SOURCE_INTERVENTION, InboxService
from derisk_serve.workspace.inbox.schemas import InboxListFilter


@pytest.fixture
def setup(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()

    inbox_service = InboxService(system_app=MagicMock(), config=MagicMock())
    inbox_service.init_app(MagicMock())

    system_app = MagicMock()
    system_app.get_component.return_value = inbox_service

    intv_service = InterventionService(system_app=system_app, config=MagicMock())
    intv_service.init_app(system_app)

    return intv_service, inbox_service


def _list(inbox_service, user_id):
    return inbox_service.list_inbox(InboxListFilter(workspace_id=1, user_id=user_id))


def test_intervention_create_writes_inbox(setup):
    """Intervention 创建(assignee 有值)-> assignee 待办出现。"""
    intv_service, inbox_service = setup
    resp = intv_service.create(InterventionRequest(
        workspace_id=1, type="review", assignee_user_id=5,
        question={"tool": "start_task", "args": {}},
    ))
    items = _list(inbox_service, 5)
    assert len(items) == 1
    assert items[0].source_type == SOURCE_INTERVENTION
    assert items[0].source_id == str(resp.id)
    assert "start_task" in items[0].title


def test_intervention_resolve_clears_inbox(setup):
    """Intervention resolve -> 待办消除。"""
    intv_service, inbox_service = setup
    resp = intv_service.create(InterventionRequest(
        workspace_id=1, assignee_user_id=5, question={"tool": "start_task"},
    ))
    assert len(_list(inbox_service, 5)) == 1
    intv_service.resolve(resp.id, InterventionResolveRequest(resolved_by_user_id=5))
    assert len(_list(inbox_service, 5)) == 0


def test_intervention_abort_clears_inbox(setup):
    """Intervention abort -> 待办消除。"""
    intv_service, inbox_service = setup
    resp = intv_service.create(InterventionRequest(
        workspace_id=1, assignee_user_id=5, question={},
    ))
    assert len(_list(inbox_service, 5)) == 1
    intv_service.abort(resp.id)
    assert len(_list(inbox_service, 5)) == 0
