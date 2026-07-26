"""GptsTodoDao + MetaDerisksTodoStorage 持久化 round-trip 测试.

验证 P1-6 修复：
1. todos 不再被 _from_kanban_data 丢弃，write -> read 拿回
2. 独立 gpts_todos 表，写 todo 不再覆盖同 conv 的 kanban 行
"""
import pytest

from derisk.storage.metadata import db
from derisk_serve.agent.db.gpts_todos_db import GptsTodoDao


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    with db.session() as session:
        yield session


@pytest.mark.asyncio
async def test_dao_round_trip(db_session):
    dao = GptsTodoDao()
    todos_data = [
        {"id": "1", "content": "任务A", "status": "completed"},
        {"id": "2", "content": "任务B", "status": "in_progress"},
    ]
    rid = await dao.save_todos_async("conv1", "conv1", "todo", todos_data)
    assert rid > 0

    got = await dao.get_todos_async("conv1", "conv1")
    assert got is not None
    assert len(got) == 2
    assert got[0]["content"] == "任务A"
    assert got[1]["status"] == "in_progress"

    # 更新（覆盖）
    todos_data[1]["status"] = "completed"
    await dao.save_todos_async("conv1", "conv1", "todo", todos_data)
    got2 = await dao.get_todos_async("conv1", "conv1")
    assert got2[1]["status"] == "completed"

    # 删除
    await dao.delete_todos_async("conv1", "conv1")
    assert await dao.get_todos_async("conv1", "conv1") is None


@pytest.mark.asyncio
async def test_dao_empty_when_not_exists(db_session):
    dao = GptsTodoDao()
    assert await dao.get_todos_async("nope", "nope") is None


@pytest.mark.asyncio
async def test_storage_round_trip(db_session):
    """MetaDerisksTodoStorage 端到端：write -> read 拿回.

    修复前 todos 被丢弃，read 恒为 []。
    """
    from derisk.agent.core.memory.gpts.file_base import TodoItem, TodoStatus
    from derisk_serve.agent.agents.derisks_memory import MetaDerisksTodoStorage

    storage = MetaDerisksTodoStorage()
    todos = [
        TodoItem(id="1", content="任务A", status=TodoStatus.COMPLETED.value),
        TodoItem(id="2", content="任务B", status=TodoStatus.IN_PROGRESS.value),
    ]
    await storage.write_todos("conv1", todos)
    got = await storage.read_todos("conv1")
    assert len(got) == 2
    assert got[0].content == "任务A"
    assert got[1].status == "in_progress"

    await storage.clear_todos("conv1")
    assert await storage.read_todos("conv1") == []


@pytest.mark.asyncio
async def test_storage_does_not_collide_with_kanban(db_session):
    """独立表：写 todo 不再覆盖同 conv 的 kanban 行。"""
    from derisk.agent.core.memory.gpts.file_base import TodoItem, TodoStatus
    from derisk_serve.agent.agents.derisks_memory import MetaDerisksTodoStorage
    from derisk_serve.agent.db.gpts_kanban_db import GptsKanbanDao

    kanban_dao = GptsKanbanDao()
    await kanban_dao.save_kanban_async(
        "conv1",
        "conv1",
        "agent1",
        {
            "kanban_id": "k1",
            "mission": "m",
            "current_stage_index": 0,
            "stages": [{"s": 1}],
        },
    )

    storage = MetaDerisksTodoStorage()
    await storage.write_todos(
        "conv1", [TodoItem(id="1", content="t", status=TodoStatus.PENDING.value)]
    )

    kanban = await kanban_dao.get_kanban_async("conv1", "conv1")
    assert kanban is not None
    assert kanban["mission"] == "m"
    assert kanban["stages"] == [{"s": 1}]

    # todo 也独立可读
    got = await storage.read_todos("conv1")
    assert len(got) == 1
    assert got[0].content == "t"
