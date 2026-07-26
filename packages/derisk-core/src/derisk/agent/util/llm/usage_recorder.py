"""LLM 调用 usage 记录注册表。

derisk-core 侧只定义记录结构与注册表，不感知存储（避免 derisk-core -> derisk-serve 依赖）。
derisk-serve 在启动时通过 ``register_llm_usage_recorder`` 注册一个写 DB 的回调。

设计要点：
- ``AIWrapper.create`` 是 V1/V2 所有 LLM 调用的唯一咽喉点，在 ``finally`` 里调用 ``record_llm_usage``。
- fire-and-forget：任何 recorder 抛错只 warning，绝不影响 LLM 调用主路径。
- 未注册 recorder 时（derisk-core 单跑 / 测试）``record_llm_usage`` 空转，零侵入。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMUsageRecord:
    """单次 LLM 调用的 usage 记录。"""

    model_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    stream: bool = True
    error_code: int = 0
    started_at: int = 0  # epoch ms

    # 可选上下文（来自 root_tracer，可能为空）
    conv_id: Optional[str] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None

    # 可选性能明细
    first_token_ms: Optional[int] = None  # 首 token 耗时（ms）
    tokens_per_sec: Optional[float] = None


# 已注册的 recorder 回调列表
_recorders: List[Callable[[LLMUsageRecord], Awaitable[None]]] = []


def register_llm_usage_recorder(
    fn: Callable[[LLMUsageRecord], Awaitable[None]],
) -> None:
    """注册一个 async recorder 回调。derisk-serve 启动时调用。"""
    _recorders.append(fn)


def clear_llm_usage_recorders() -> None:
    """清空已注册的 recorder（测试用）。"""
    _recorders.clear()


async def record_llm_usage(record: LLMUsageRecord) -> None:
    """将一次 LLM 调用 usage 分发给所有已注册 recorder。

    fire-and-forget：单个 recorder 异常只 warning，不阻断其余 recorder，也不影响调用方。
    """
    if not _recorders:
        return
    for fn in _recorders:
        try:
            await fn(record)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[usage] recorder failed model={record.model_name}: {e}")
