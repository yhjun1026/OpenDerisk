"""build_todo_reminder + _inject_todo_tools 单测。

验证 claude-code 式 TODO 闭环的核心环节：
- build_todo_reminder: todo 状态 -> <system-reminder> 文本（V1/V2 共用）
- _inject_todo_tools: todowrite/todoread 始终注入 available_system_tools
"""
from derisk.agent.core.memory.gpts.file_base import TodoItem, TodoStatus
from derisk.agent.tools.builtin.todo.todo_reminder import build_todo_reminder


class _FakeGptsMemory:
    def __init__(self, todos):
        self._todos = todos

    async def read_todos(self, conv_id):
        return self._todos


class _FakeMemory:
    def __init__(self, todos):
        self.gpts_memory = _FakeGptsMemory(todos)


async def test_none_when_memory_none():
    assert await build_todo_reminder(None, "c1") is None


async def test_none_when_no_gpts_memory():
    class M:
        gpts_memory = None

    assert await build_todo_reminder(M(), "c1") is None


async def test_none_when_empty_todos():
    assert await build_todo_reminder(_FakeMemory([]), "c1") is None


async def test_reminder_contains_states_counts_and_order():
    todos = [
        TodoItem(id="1", content="任务A", status=TodoStatus.COMPLETED.value),
        TodoItem(id="2", content="任务B", status=TodoStatus.IN_PROGRESS.value),
        TodoItem(id="3", content="任务C", status=TodoStatus.PENDING.value),
    ]
    r = await build_todo_reminder(_FakeMemory(todos), "c1")
    assert r is not None
    assert "<system-reminder>" in r and "</system-reminder>" in r
    # 各状态都渲染
    assert "[in_progress] 任务B" in r
    assert "[pending] 任务C" in r
    assert "[completed] 任务A" in r
    # in_progress 置顶（渲染顺序）
    assert r.index("in_progress") < r.index("pending") < r.index("completed")
    # 计数概览
    assert "1 in_progress" in r
    assert "1 completed" in r


async def test_reminder_collapses_completed_over_limit():
    todos = [
        TodoItem(id=str(i), content=f"任务{i}", status=TodoStatus.COMPLETED.value)
        for i in range(25)
    ]
    todos.append(TodoItem(id="x", content="进行中", status=TodoStatus.IN_PROGRESS.value))
    todos.append(TodoItem(id="y", content="待办", status=TodoStatus.PENDING.value))
    r = await build_todo_reminder(_FakeMemory(todos), "c1")
    assert r is not None
    assert "已完成 25 项（已折叠）" in r
    assert "[in_progress] 进行中" in r
    assert "[pending] 待办" in r
    assert "[completed] 任务0" not in r


async def test_inject_todo_tools_populates_available_system_tools():
    """_inject_todo_tools 应把 todowrite/todoread 注入 available_system_tools。"""
    from derisk.agent.expand.react_master_agent.react_master_agent import ReActMasterAgent
    from derisk.agent.tools.registry import register_builtin_tools, tool_registry

    if not tool_registry._initialized:
        register_builtin_tools()

    class _FakeAgent:
        available_system_tools: dict = {}

    agent = _FakeAgent()
    # _inject_todo_tools 只依赖 self.available_system_tools，不碰其它属性
    await ReActMasterAgent._inject_todo_tools(agent)
    assert "todowrite" in agent.available_system_tools
    assert "todoread" in agent.available_system_tools


def test_build_todolist_fence_correct_tag_and_status_mapping():
    """build_todolist_fence 应产出 d-todo-list 围栏 + 状态映射。"""
    from derisk.agent.tools.builtin.todo.todo_reminder import build_todolist_fence

    todos = [
        TodoItem(id="1", content="任务A", status=TodoStatus.COMPLETED.value),
        TodoItem(id="2", content="任务B", status=TodoStatus.IN_PROGRESS.value),
        TodoItem(id="3", content="任务C", status=TodoStatus.CANCELLED.value),
    ]
    fence = build_todolist_fence(todos, "c1")
    assert fence is not None
    assert fence.startswith("```d-todo-list\n")
    assert fence.endswith("\n```")
    # 状态映射：in_progress->working, cancelled->failed（orjson 无空格）
    assert '"status":"working"' in fence
    assert '"status":"failed"' in fence
    assert '"status":"completed"' in fence
    # 不应出现未映射的 in_progress/cancelled
    assert '"status":"in_progress"' not in fence
    assert '"status":"cancelled"' not in fence
