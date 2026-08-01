"""ECP 待审批提案 -> 空间共享待办 读时惰性对账测试。

对账语义(镜像 ECP 确认收件箱"最新版本为 proposed 即待审批"):
  1. 绑定 ecp 资源 + proposed 对象 -> sync 后每个成员一条 shared 待办
  2. 提案被 confirm(latest 变 confirmed)-> 再 sync 待办全部消除
  3. 用户手动 done 后 -> 再 sync 不重建(同一提案不骚扰)
  4. 同对象新提案版本(v2)-> v2 待办产生,v1 待办消除
  5. 无 ecp 绑定 -> 不产生待办;遗留 ecp 待办被清
  6. 新成员加入 -> sync 补齐其待办
"""
import json

import pytest

from derisk.storage.metadata import db
from derisk_serve.building.app.models.models_details import AppDetailServeEntity
from derisk_serve.ecp.models.models import SemanticObjectDao
from derisk_serve.workspace.inbox.ecp_sync import (
    resolve_ecp_workspaces,
    sync_ecp_proposals,
)
from derisk_serve.workspace.inbox.models import (
    SOURCE_ECP_PROPOSAL,
    STATUS_DONE,
    STATUS_UNREAD,
    VIS_SHARED,
    InboxItemDao,
    InboxItemEntity,
)
from derisk_serve.workspace.models.models import (
    WorkspaceDao,
    WorkspaceEntity,
    WorkspaceMemberEntity,
)

ECP_WS = "default"
APP_CODE = "scene-workspace-agent"


@pytest.fixture
def setup(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()

    session = WorkspaceDao().get_raw_session()
    session.add(
        WorkspaceEntity(
            id=1,
            workspace_code="ws_test",
            name="测试空间",
            owner_user_id=1,
            default_agent_app_code=APP_CODE,
        )
    )
    session.add_all(
        [
            WorkspaceMemberEntity(workspace_id=1, user_id=1, role="owner"),
            WorkspaceMemberEntity(workspace_id=1, user_id=2, role="contributor"),
        ]
    )
    session.commit()
    session.close()
    return SemanticObjectDao(), InboxItemDao()


def _bind_ecp(resources):
    """写一行 app detail,resources 为给定列表。"""
    session = WorkspaceDao().get_raw_session()
    session.query(AppDetailServeEntity).delete()
    session.add(
        AppDetailServeEntity(
            app_code=APP_CODE,
            app_name="场景 Agent",
            type="agent",
            agent_name="SceneAgent",
            agent_role="scene",
            node_id="node-1",
            resources=json.dumps(resources, ensure_ascii=False),
        )
    )
    session.commit()
    session.close()


def _propose(dao, object_id="metric.gmv", name="GMV"):
    return dao.create_proposal(
        object_id=object_id,
        obj_type="metric",
        payload={"name": name},
        workspace_id=ECP_WS,
    )


def _items(dao, workspace_id=1):
    return dao.list_by_workspace_source(workspace_id, SOURCE_ECP_PROPOSAL)


def _active(items):
    return [i for i in items if i.inbox_status == STATUS_UNREAD]


# ---------------- 关联解析 ----------------
def test_resolve_ecp_workspaces(setup):
    _bind_ecp(
        [
            {"name": "ecp", "type": "ecp", "value": {"workspace_id": ECP_WS}},
            {"name": "db", "type": "db", "value": "1"},
        ]
    )
    # 派生工作区(ecp_<workspace_code>)恒在首位,显式绑定去重追加
    assert resolve_ecp_workspaces(1) == ["ecp_ws_test", ECP_WS]


def test_resolve_ecp_workspaces_value_as_json_string(setup):
    """value 为 JSON 字符串时也能解析。"""
    _bind_ecp(
        [{"name": "ecp", "type": "ecp", "value": json.dumps({"workspace_id": ECP_WS})}]
    )
    assert resolve_ecp_workspaces(1) == ["ecp_ws_test", ECP_WS]


def test_resolve_no_binding(setup):
    """无显式绑定时仍关联派生工作区(场景 agent 运行时装配器自动注入)。"""
    _bind_ecp([{"name": "db", "type": "db", "value": "1"}])
    assert resolve_ecp_workspaces(1) == ["ecp_ws_test"]


def test_resolve_derived_dedup_with_explicit(setup):
    """显式绑定恰好是派生工作区时不重复。"""
    _bind_ecp(
        [{"name": "ecp", "type": "ecp", "value": {"workspace_id": "ecp_ws_test"}}]
    )
    assert resolve_ecp_workspaces(1) == ["ecp_ws_test"]


# ---------------- 补:提案 -> 全员共享待办 ----------------
def test_proposal_becomes_shared_todo_for_all_members(setup):
    object_dao, inbox_dao = setup
    _bind_ecp([{"name": "ecp", "type": "ecp", "value": {"workspace_id": ECP_WS}}])
    _propose(object_dao)

    stats = sync_ecp_proposals(1)
    assert stats["created"] == 2  # 两个成员各一条

    items = _active(_items(inbox_dao))
    assert {i.user_id for i in items} == {1, 2}
    assert all(i.visibility == VIS_SHARED for i in items)
    assert all(i.source_type == SOURCE_ECP_PROPOSAL for i in items)
    assert items[0].source_id == f"{ECP_WS}:metric.gmv@v1"
    assert "GMV" in items[0].title

    # 幂等:再 sync 不重复创建
    stats = sync_ecp_proposals(1)
    assert stats == {"created": 0, "resolved": 0}


# ---------------- 消:confirm 后待办消除 ----------------
def test_confirm_resolves_todo(setup):
    object_dao, inbox_dao = setup
    _bind_ecp([{"name": "ecp", "type": "ecp", "value": {"workspace_id": ECP_WS}}])
    _propose(object_dao)
    sync_ecp_proposals(1)
    assert len(_active(_items(inbox_dao))) == 2

    object_dao.confirm_version("metric.gmv", 1, ECP_WS, "u1")
    stats = sync_ecp_proposals(1)
    assert stats["resolved"] == 1  # 按 source_id 批量消除计 1 次
    assert len(_active(_items(inbox_dao))) == 0
    assert all(i.inbox_status == STATUS_DONE for i in _items(inbox_dao))


# ---------------- 手动 done 不重建 ----------------
def test_manual_done_not_recreated(setup):
    object_dao, inbox_dao = setup
    _bind_ecp([{"name": "ecp", "type": "ecp", "value": {"workspace_id": ECP_WS}}])
    _propose(object_dao)
    sync_ecp_proposals(1)

    item = [i for i in _active(_items(inbox_dao)) if i.user_id == 2][0]
    inbox_dao.update_status(item.id, 2, STATUS_DONE)

    stats = sync_ecp_proposals(1)
    assert stats["created"] == 0
    user2_items = [i for i in _items(inbox_dao) if i.user_id == 2]
    assert len(user2_items) == 1
    assert user2_items[0].inbox_status == STATUS_DONE


# ---------------- 新版本:v1 消、v2 补 ----------------
def test_new_version_replaces_old_todo(setup):
    object_dao, inbox_dao = setup
    _bind_ecp([{"name": "ecp", "type": "ecp", "value": {"workspace_id": ECP_WS}}])
    _propose(object_dao)
    sync_ecp_proposals(1)

    _propose(object_dao)  # v2
    sync_ecp_proposals(1)

    active = _active(_items(inbox_dao))
    assert {i.source_id for i in active} == {f"{ECP_WS}:metric.gmv@v2"}
    v1_items = [
        i for i in _items(inbox_dao) if i.source_id == f"{ECP_WS}:metric.gmv@v1"
    ]
    assert all(i.inbox_status == STATUS_DONE for i in v1_items)


# ---------------- 无绑定:不产生 + 遗留清除 ----------------
def test_no_binding_produces_nothing_and_cleans_stale(setup):
    object_dao, inbox_dao = setup
    _bind_ecp([{"name": "ecp", "type": "ecp", "value": {"workspace_id": ECP_WS}}])
    _propose(object_dao)
    sync_ecp_proposals(1)
    assert len(_active(_items(inbox_dao))) == 2

    # 移除绑定(换成 db 资源)
    _bind_ecp([{"name": "db", "type": "db", "value": "1"}])
    sync_ecp_proposals(1)
    assert len(_active(_items(inbox_dao))) == 0


# ---------------- 新成员补齐 ----------------
def test_new_member_gets_todo(setup):
    object_dao, inbox_dao = setup
    _bind_ecp([{"name": "ecp", "type": "ecp", "value": {"workspace_id": ECP_WS}}])
    _propose(object_dao)
    sync_ecp_proposals(1)

    session = WorkspaceDao().get_raw_session()
    session.add(WorkspaceMemberEntity(workspace_id=1, user_id=3, role="viewer"))
    session.commit()
    session.close()

    stats = sync_ecp_proposals(1)
    assert stats["created"] == 1
    user3_items = [i for i in _active(_items(inbox_dao)) if i.user_id == 3]
    assert len(user3_items) == 1


# ---------------- 派生工作区:零显式绑定也对账 ----------------
def test_derived_workspace_proposal_becomes_todo(setup):
    """场景 agent 运行时装配器自动把提案落在派生工作区(ecp_<code>),
    无需任何显式 app 绑定,inbox 对账也必须看到。"""
    object_dao, inbox_dao = setup
    _bind_ecp([])  # 无任何资源绑定
    object_dao.create_proposal(
        object_id="metric.rev",
        obj_type="metric",
        payload={"name": "营收"},
        workspace_id="ecp_ws_test",
    )

    stats = sync_ecp_proposals(1)
    assert stats["created"] == 2
    items = _active(_items(inbox_dao))
    assert items[0].source_id == "ecp_ws_test:metric.rev@v1"
