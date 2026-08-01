"""P0 tests for Inbox(个人待办收件箱)+ task reassign -> inbox 闭环。

验证待办的核心语义:
  1. 自己发起的任务不产生待办(待办=阻塞事件,非指派)
  2. 自动完成的任务全程不产生待办
  3. 转交任务 -> 新负责人待办出现(personal)
  4. 转交再转交 -> 原 assignee 待办消除
  5. shared 待办(多人各一条)一人完成全员消除
  6. personal 待办 resolve 只消除本人
  7. 用户手动推进待办状态(接手/完成),他人不能改
"""
from unittest.mock import MagicMock

import pytest

from derisk.storage.metadata import db
from derisk_serve.task.api.schemas import TaskRequest
from derisk_serve.task.service.service import TaskService
from derisk_serve.workspace.inbox import (
    SOURCE_ECP_PROPOSAL,
    SOURCE_TASK,
    STATUS_DONE,
    STATUS_UNREAD,
    VIS_PERSONAL,
    VIS_SHARED,
    InboxService,
)
from derisk_serve.workspace.inbox.schemas import InboxListFilter


@pytest.fixture
def setup(tmp_path):
    """init sqlite + 真实 InboxService + TaskService(mock system_app 注入 inbox)。"""
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()

    inbox_service = InboxService(system_app=MagicMock(), config=MagicMock())
    inbox_service.init_app(MagicMock())

    system_app = MagicMock()
    # TaskService.reassign 通过 get_component 拿 InboxService
    system_app.get_component.return_value = inbox_service

    task_service = TaskService(system_app=system_app, config=MagicMock())
    task_service.init_app(system_app)

    return task_service, inbox_service


def _list(inbox_service, user_id, status=None, source_type=None):
    return inbox_service.list_inbox(InboxListFilter(
        workspace_id=1, user_id=user_id, status=status, source_type=source_type,
    ))


# ---------------- 待办本质:自己发起 / 自动完成 不产生待办 ----------------
def test_self_created_task_produces_no_inbox(setup):
    """自己发起的任务不产生待办(待办是阻塞事件,不是指派)。"""
    task_service, inbox_service = setup
    task_service.create(TaskRequest(workspace_id=1, title="t", created_by_user_id=1))
    assert len(_list(inbox_service, 1)) == 0


def test_auto_completed_task_produces_no_inbox(setup):
    """任务自动跑完(无阻塞)全程不产生待办。"""
    task_service, inbox_service = setup
    task = task_service.create(TaskRequest(workspace_id=1, title="t", created_by_user_id=1))
    task_service.start(task.id)                       # draft -> running
    task_service.transition(task.id, "delivered")     # running -> delivered
    task_service.transition(task.id, "closed")        # delivered -> closed
    assert len(_list(inbox_service, 1)) == 0


# ---------------- 转交 -> 待办出现 ----------------
def test_reassign_creates_inbox_for_new_assignee(setup):
    task_service, inbox_service = setup
    task = task_service.create(TaskRequest(workspace_id=1, title="t", created_by_user_id=1))
    task_service.reassign(task.id, 2)

    items2 = _list(inbox_service, 2)
    assert len(items2) == 1
    assert items2[0].source_type == SOURCE_TASK
    assert items2[0].source_id == str(task.id)
    assert items2[0].visibility == VIS_PERSONAL
    assert items2[0].inbox_status == STATUS_UNREAD


def test_reassign_resolves_old_assignee_inbox(setup):
    """转交后原 assignee 的待办消除(personal 精确)。"""
    task_service, inbox_service = setup
    task = task_service.create(TaskRequest(workspace_id=1, title="t", created_by_user_id=1))
    task_service.reassign(task.id, 2)
    assert len(_list(inbox_service, 2)) == 1

    task_service.reassign(task.id, 3)  # 再转给 user3
    assert len(_list(inbox_service, 2)) == 0   # user2 消除
    assert len(_list(inbox_service, 3)) == 1   # user3 出现


# ---------------- shared 待办:多人各一条,一人完成全员消除 ----------------
def test_shared_inbox_resolved_for_all(setup):
    """ECP 提案类共享待办:给多 confirmer 各写一条,一人确认全员消除。"""
    _, inbox_service = setup
    # 造一条真实待审批提案(source_id 与惰性对账格式一致),
    # 否则对账会把无对应提案的待办当陈旧数据消除
    import json as _json

    from derisk_serve.building.app.models.models_details import (
        AppDetailServeEntity,
    )
    from derisk_serve.ecp.models.models import SemanticObjectDao
    from derisk_serve.workspace.models.models import (
        WorkspaceDao,
        WorkspaceEntity,
    )

    session = WorkspaceDao().get_raw_session()
    session.add(
        WorkspaceEntity(
            id=1, workspace_code="ws_t", name="t", owner_user_id=1,
            default_agent_app_code="app-1",
        )
    )
    session.add(
        AppDetailServeEntity(
            app_code="app-1", app_name="a", type="agent",
            agent_name="ag", agent_role="r", node_id="n1",
            resources=_json.dumps(
                [{"name": "ecp", "type": "ecp",
                  "value": {"workspace_id": "default"}}]
            ),
        )
    )
    session.commit()
    session.close()
    SemanticObjectDao().create_proposal(
        object_id="prop-1", obj_type="metric", payload={"name": "X"},
        workspace_id="default",
    )
    source_id = "default:prop-1@v1"

    inbox_service.create_for_users(
        workspace_id=1, user_ids=[1, 2, 3],
        source_type=SOURCE_ECP_PROPOSAL, source_id=source_id,
        title="确认提案 X", visibility=VIS_SHARED,
    )
    assert len(_list(inbox_service, 1)) == 1
    assert len(_list(inbox_service, 2)) == 1
    assert len(_list(inbox_service, 3)) == 1

    # 任一人确认 -> 全员消除(不传 user_id 按 source_id 批量)
    inbox_service.resolve(
        workspace_id=1, source_type=SOURCE_ECP_PROPOSAL, source_id=source_id,
    )
    for uid in (1, 2, 3):
        # 活跃待办列表为空(都已 done)
        assert len(_list(inbox_service, uid)) == 0
        # done 历史仍可查
        done = _list(inbox_service, uid, status=STATUS_DONE)
        assert len(done) == 1


# ---------------- personal 待办:resolve 只消除本人 ----------------
def test_personal_inbox_resolved_only_for_user(setup):
    """personal 待办(转交)resolve 传 user_id 只消除本人,他人不变。"""
    _, inbox_service = setup
    inbox_service.create_item(
        workspace_id=1, user_id=1, source_type=SOURCE_TASK,
        source_id="t1", title="t", visibility=VIS_PERSONAL,
    )
    inbox_service.create_item(
        workspace_id=1, user_id=2, source_type=SOURCE_TASK,
        source_id="t1", title="t", visibility=VIS_PERSONAL,
    )
    # 只消除 user1
    inbox_service.resolve(
        workspace_id=1, source_type=SOURCE_TASK, source_id="t1", user_id=1,
    )
    assert len(_list(inbox_service, 1)) == 0                       # user1 活跃空
    assert _list(inbox_service, 1, status=STATUS_DONE)[0].inbox_status == STATUS_DONE
    assert _list(inbox_service, 2)[0].inbox_status == STATUS_UNREAD  # user2 还活跃


# ---------------- 用户手动推进待办状态 ----------------
def test_manual_status_update(setup):
    """用户手动推进自己的待办(接手/完成);他人不能改我的待办。"""
    _, inbox_service = setup
    item = inbox_service.create_item(
        workspace_id=1, user_id=1, source_type=SOURCE_TASK,
        source_id="t1", title="t", visibility=VIS_PERSONAL,
    )
    # 接手
    inbox_service.update_status(item.id, user_id=1, new_status="doing")
    assert _list(inbox_service, 1)[0].inbox_status == "doing"
    # 别人不能改我的待办
    assert inbox_service.update_status(item.id, user_id=2, new_status="done") is None
    # 自己标记完成
    inbox_service.update_status(item.id, user_id=1, new_status="done")
    assert len(_list(inbox_service, 1)) == 0
    assert _list(inbox_service, 1, status=STATUS_DONE)[0].inbox_status == STATUS_DONE
