"""WorkspaceService.get_or_create_home 测试:首页默认空间幂等解析。

解析顺序:
1. 有 settings.is_home 标记 -> 返回
2. 无标记 -> 最早创建(id 最小)补标记(存量用户零迁移)
3. 无空间 -> 新建"我的工作台"(create 派生钩子生效)
归档空间不参与选择。
"""
import pytest

from derisk.storage.metadata import db
from derisk_serve.workspace.api.schemas import WorkspaceRequest
from derisk_serve.workspace.config import ServeConfig
from derisk_serve.workspace.models.models import (
    WorkspaceDao,
    WorkspaceMemberDao,
    WorkspaceResourceDao,
    WorkspaceConversationLinkDao,
)
from derisk_serve.workspace.service.service import WorkspaceService


@pytest.fixture
def service(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    svc = WorkspaceService(
        None,
        ServeConfig(),
        dao=WorkspaceDao(),
        member_dao=WorkspaceMemberDao(),
        resource_dao=WorkspaceResourceDao(),
        conv_link_dao=WorkspaceConversationLinkDao(),
    )
    # init_app 不走(无 SystemApp);create 的 ECP 供给钩子对 None system_app
    # 已做 fail-open 保护。
    return svc


def _create(svc, name, owner=1, **kw):
    return svc.create(WorkspaceRequest(name=name, owner_user_id=owner, **kw))


def test_create_when_no_workspace(service):
    home = service.get_or_create_home(user_id=1)
    assert home.name == "我的工作台"
    assert home.settings.get("is_home") is True
    # 幂等:再次调用返回同一空间,不新建
    again = service.get_or_create_home(user_id=1)
    assert again.id == home.id
    assert len(service.list_workspaces(1)) == 1


def test_marked_home_wins(service):
    _create(service, "空间A")
    b = _create(service, "空间B", settings={"is_home": True})
    home = service.get_or_create_home(user_id=1)
    assert home.id == b.id


def test_legacy_unmarked_falls_back_to_earliest_and_marks(service):
    """存量用户:无 is_home 标记时取最早创建的,并补上标记。"""
    a = _create(service, "空间A")
    _create(service, "空间B")
    home = service.get_or_create_home(user_id=1)
    assert home.id == a.id
    # 标记已补:重查确认 settings 落库
    refetched = service.get_by_id(a.id)
    assert refetched.settings.get("is_home") is True
    # 再次调用直接命中标记
    assert service.get_or_create_home(user_id=1).id == a.id


def test_archived_home_is_skipped(service):
    a = _create(service, "空间A", settings={"is_home": True})
    b = _create(service, "空间B")
    service.archive(a.workspace_code)
    home = service.get_or_create_home(user_id=1)
    assert home.id == b.id
    # B 被补标
    assert service.get_by_id(b.id).settings.get("is_home") is True


def test_other_users_workspaces_invisible(service):
    _create(service, "别人的空间", owner=2)
    home = service.get_or_create_home(user_id=1)
    assert home.name == "我的工作台"
    assert home.owner_user_id == 1
