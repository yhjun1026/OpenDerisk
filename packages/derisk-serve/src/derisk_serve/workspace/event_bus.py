"""场景空间 workspace 事件总线。

聚合对话(aggregation_chat)按 workspace 注册本回合的事件队列;scene 写工具与
playbook run_task 在产生实体(任务/介入/交付物/投递)时 emit,事件经队列
drain 进 SSE chunk(format_workspace_event),前端 use-chat.ts 白名单消费。

只在做聚合同一个进程/事件循环内有效(run_task 是 detached asyncio task,同进程),
fire-and-forget 且无活跃 SSE 时 emit 自然落空,前端 4s 轮询兜底。
"""
import asyncio
import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)

# workspace_id -> 活跃对话的事件队列集合(通常同时只有 1 个活跃流)
_queues: Dict[int, Set["asyncio.Queue"]] = {}


def register_workspace_queue(workspace_id: int, queue: "asyncio.Queue") -> None:
    _queues.setdefault(workspace_id, set()).add(queue)


def unregister_workspace_queue(workspace_id: int, queue: "asyncio.Queue") -> None:
    qs = _queues.get(workspace_id)
    if not qs:
        return
    qs.discard(queue)
    if not qs:
        _queues.pop(workspace_id, None)


def emit_workspace_event(workspace_id: int, event_type: str, payload: dict) -> None:
    """向该 workspace 所有活跃对话队列广播事件;无活跃流时静默丢弃。"""
    qs = _queues.get(workspace_id)
    if not qs:
        return
    for q in list(qs):
        try:
            q.put_nowait((event_type, payload))
        except asyncio.QueueFull:
            logger.warning(f"workspace event queue full, drop {event_type}")
        except Exception:  # noqa: BLE001 - 事件失败不影响主流程
            logger.warning(f"emit workspace event failed: {event_type}", exc_info=True)
