"""Tests for WorkspaceConversationLinkDao."""
from unittest.mock import MagicMock

import pytest

from derisk.storage.metadata import db
from derisk_serve.workspace.models.models import (
    WorkspaceConversationLinkDao,
    WorkspaceConversationLinkEntity,
)
from derisk_serve.workspace.service.service import WorkspaceService


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    with db.session() as session:
        yield session


@pytest.fixture
def service(db_session):
    system_app = MagicMock()
    config = MagicMock()
    return WorkspaceService(
        system_app=system_app,
        config=config,
        conv_link_dao=WorkspaceConversationLinkDao(),
    )


def _refresh(session, conv_uid):
    return (
        session.query(WorkspaceConversationLinkEntity)
        .filter(WorkspaceConversationLinkEntity.conv_uid == conv_uid)
        .first()
    )


def test_link_with_set_current_flips_previous(db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1, set_current=True)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id=1, set_current=True)

    refreshed_first = _refresh(db_session, "conv-1")
    refreshed_second = _refresh(db_session, "conv-2")
    assert refreshed_first.is_current is False
    assert refreshed_second.is_current is True


def test_get_current_conversation(db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1, set_current=True)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id=1, set_current=False)

    current = dao.get_current(workspace_id=1, user_id=1)
    assert current.conv_uid == "conv-1"


def test_rename_conversation(db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1, title="old")
    dao.rename(conv_uid="conv-1", title="new title")

    refreshed = _refresh(db_session, "conv-1")
    assert refreshed.title == "new title"


def test_to_response_includes_new_fields():
    entity = WorkspaceConversationLinkEntity(
        id=1,
        workspace_id=1,
        conv_uid="conv-1",
        task_id=2,
        user_id=3,
        title="title",
        is_current=True,
    )
    response = WorkspaceConversationLinkDao().to_response(entity)
    assert response["title"] == "title"
    assert response["is_current"] is True


# ---------------- Conversation service ----------------


def test_service_set_current_persists(service, db_session):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id=1)

    service.set_current_conversation(workspace_id=1, user_id=1, conv_uid="conv-2")

    current = service.get_current_conversation(workspace_id=1, user_id=1)
    assert current["conv_uid"] == "conv-2"
    refreshed_first = _refresh(db_session, "conv-1")
    refreshed_second = _refresh(db_session, "conv-2")
    assert refreshed_first.is_current is False
    assert refreshed_second.is_current is True


def test_service_set_current_wrong_user_raises(service):
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=2)
    with pytest.raises(ValueError, match="not linked to workspace 1 for user 1"):
        service.set_current_conversation(workspace_id=1, user_id=1, conv_uid="conv-1")


def test_service_rename(service, db_session):
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=1)
    renamed = service.rename_conversation(conv_uid="conv-1", title="my title")
    assert renamed["title"] == "my title"
    refreshed = _refresh(db_session, "conv-1")
    assert refreshed.title == "my title"


def test_first_link_becomes_current_when_none_set(service):
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=1)
    current = service.get_current_conversation(workspace_id=1, user_id=1)
    assert current["conv_uid"] == "conv-1"


def test_subsequent_link_does_not_flip_current(service):
    dao = WorkspaceConversationLinkDao()
    dao.link(workspace_id=1, conv_uid="conv-1", user_id=1, set_current=True)
    dao.link(workspace_id=1, conv_uid="conv-2", user_id=1, set_current=False)

    current = service.get_current_conversation(workspace_id=1, user_id=1)
    assert current["conv_uid"] == "conv-1"


def test_link_without_user_id_does_not_auto_set_current(service):
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=None)
    current = service.get_current_conversation(workspace_id=1, user_id=None)
    assert current is None


def test_service_set_current_unowned_link_with_real_user(service, db_session):
    """无主 link(user_id=None) + 真实 user_id 调 set-current 应成功。

    回归 _set_current_internal(set 用 user_id == X 严格匹配)与 get_current
    (OR 含 NULL)语义不对称导致的 'Failed to set current conversation' 报错:
    set 匹配不到无主 link -> is_current 没置位 -> get 查不到 -> 抛错。
    """
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-1", user_id=None)
    WorkspaceConversationLinkDao().link(workspace_id=1, conv_uid="conv-2", user_id=None)

    # 真实 user_id=1 切换到无主 link conv-2
    service.set_current_conversation(workspace_id=1, user_id=1, conv_uid="conv-2")

    current = service.get_current_conversation(workspace_id=1, user_id=1)
    assert current is not None
    assert current["conv_uid"] == "conv-2"
    assert current["is_current"] is True
    # 同域其他无主 link 被清 False
    assert _refresh(db_session, "conv-1").is_current is False
