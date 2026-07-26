"""Todo reminder 构建 - 把当前 todo 状态渲染成 system-reminder 文本注入 LLM 上下文。

这是 claude-code 式 TODO 闭环的核心：todowrite 写入后，每轮 thinking() 调用本函数
把进度注入 llm_messages，让 LLM 始终看到当前任务状态并自行推进。

V1（react_master_agent.thinking）和 V2（default_thinking_fn）共用此函数，
避免两套注入逻辑、便于日后 V2 切换零返工。
"""
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# 单次注入的最大条数，超过则把已完成项折叠为计数，避免 reminder 膨胀上下文
_MAX_INLINE_ITEMS = 20

_STATUS_ICON = {
    "in_progress": "🔄",
    "pending": "⏳",
    "completed": "✅",
    "cancelled": "❌",
}

# 渲染顺序：进行中置顶，其次待处理，再已完成，最后已取消
_STATUS_ORDER = {"in_progress": 0, "pending": 1, "completed": 2, "cancelled": 3}


async def build_todo_reminder(memory: Any, conv_id: str) -> Optional[str]:
    """读取当前会话的 todo 列表，渲染成 <system-reminder> 文本。

    Args:
        memory: Agent memory（需有 gpts_memory 属性，实现 read_todos）
        conv_id: 会话 ID

    Returns:
        reminder 文本；todos 为空或读取失败时返回 None（不注入噪音）。
    """
    if not memory or not getattr(memory, "gpts_memory", None):
        return None
    try:
        todos: List[Any] = await memory.gpts_memory.read_todos(conv_id)
    except Exception as e:
        logger.debug(f"build_todo_reminder read_todos failed: {e}")
        return None

    if not todos:
        return None

    sorted_todos = sorted(todos, key=lambda t: _STATUS_ORDER.get(t.status, 99))

    # 概览行：各状态计数
    counts = {s: sum(1 for t in todos if t.status == s) for s in _STATUS_ORDER}
    overview = " / ".join(f"{counts[s]} {s}" for s in _STATUS_ORDER if counts[s] > 0)

    lines = [
        "当前任务进度（由你用 todowrite 自行维护，推进后请及时更新状态）：",
        f"共 {len(todos)} 项：{overview}",
    ]

    completed = [t for t in sorted_todos if t.status == "completed"]

    # 条数过多时折叠已完成项，只完整渲染未完成项
    if len(sorted_todos) <= _MAX_INLINE_ITEMS:
        render = sorted_todos
    else:
        render = [t for t in sorted_todos if t.status != "completed"]
        if completed:
            lines.append(f"  ✅ 已完成 {len(completed)} 项（已折叠）")

    for t in render:
        icon = _STATUS_ICON.get(t.status, "•")
        lines.append(f"  {icon} [{t.status}] {t.content}")

    return "<system-reminder>\n" + "\n".join(lines) + "\n</system-reminder>"


def build_todolist_fence(todos: List[Any], conv_id: str) -> Optional[str]:
    """构建 d-todo-list VIS 围栏字符串。

    修复 vis_tag 断点：用 TodoList Vis 实例（vis_tag=d-todo-list）生成正确围栏，
    而非依赖 render_protocol.sync_display(vis_tag=...)（Vis.sync_display 忽略 vis_tag
    kwarg，取 self.vis_tag()，且原调用返回值被丢弃）。

    同时把 file_base.TodoStatus 映射到 derisk_todo_list.TodoStatus
    （in_progress->working, cancelled->failed）。
    """
    from derisk.vis import Vis
    from derisk.agent.core.memory.gpts import TodoStatus

    _STATUS_MAP = {
        TodoStatus.IN_PROGRESS.value: "working",
        TodoStatus.PENDING.value: "pending",
        TodoStatus.COMPLETED.value: "completed",
        TodoStatus.CANCELLED.value: "failed",
    }
    current_index = 0
    items = []
    for i, todo in enumerate(todos):
        if todo.status == TodoStatus.IN_PROGRESS.value:
            current_index = i
        items.append(
            {
                "id": todo.id,
                "title": todo.content,
                "status": _STATUS_MAP.get(todo.status, "pending"),
                "index": i,
            }
        )
    vis_content = {
        "uid": f"todo_list_{conv_id}",
        "type": "all",
        "mission": "",
        "items": items,
        "current_index": current_index,
        "total_count": len(todos),
    }
    vis = Vis.of("todo_list")
    if vis is None:
        return None
    return vis.sync_display(content=vis_content)
