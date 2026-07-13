"""KnowledgeCapability —— 知识库自管理资源能力(RFC-006 Stage 7)。

知识库是 Consumer:declare 库列表 SYSTEM + consume 检索结果回注(TURN)。

**架构约束(facade 时序锁)**:facade._build_static_bundle 时序是 declare 先于
prepare(declare→collect requires→acquire prepare→fetch)。Knowledge 的 declare
依赖 knowledge_spaces 元数据(由 get_knowledge_space I/O 得),无法用 DataRequirement
占位(_spaces 是对象非 str)。故 KnowledgeCapability 不自管 prepare 的重 I/O——
from_legacy 复用旧 KnowledgePackSearchResource 实例(构造期已泄水合 spaces),
declare 读其 description 属性。prepare no-op(仅校验)。真正泄水合自管理需待
facade 时序改造(prepare 先于 declare 或引入数据查找阶段),本轮不做。

execute 不收编:knowledge_search 是 v1 KnowledgeSearch action(_init_actions 派发,
经 retriever.retrieve I/O),与 DB 同属 Route A builtin 形态,收编需改 v1/v2
shadowing + Action 派发,风险高。本轮 KnowledgeCapability 自管 declare + consume,
execute 保持 v1 action。

双轨:register_wrappers(旧 wrapper)与 register_capability(legacy provider→
KnowledgeCapability)并存,Stage 9 删前者。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

logger = logging.getLogger(__name__)


class KnowledgeCapability(Capability):
    """知识库自管理能力:declare 库列表 + consume 检索回注。

    capability_id="knowledge";executor_id="knowledge"(单例,无 live 实例自管)。
    """

    capability_id = "knowledge"

    def __init__(self, spaces: Optional[List[dict]] = None, description: str = ""):
        # spaces: [{name, knowledge_id, desc}](显式);description: 旧实例渲染好的描述串
        self._spaces = spaces
        self._description = description
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "KnowledgeCapability":
        value = value or {}
        knowledges = value.get("knowledges") or []
        spaces = [
            {
                "name": k.get("name", ""),
                "knowledge_id": k.get("knowledge_id"),
                "desc": k.get("description") or k.get("desc") or "",
            }
            for k in knowledges
        ]
        # config 若已带 name/desc,declare 可纯配置态;否则需 from_legacy 或 prepare 泄水合
        return cls(spaces=spaces or None)

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "KnowledgeCapability":
        """从旧 RetrieverResource/KnowledgePackSearchResource 实例构造(过渡期)。

        优先读 description(已渲染好的库列表串);回退读 knowledge_spaces 元数据。
        旧实例构造期已泄水合(get_knowledge_spaces_info),无新增 I/O。
        """
        desc = getattr(legacy_instance, "description", "") or ""
        if not isinstance(desc, str):
            desc = ""
        # 尝试提取 spaces 元数据(供 _render_spaces 显式路径)
        spaces = None
        kspaces = getattr(legacy_instance, "knowledge_spaces", None)
        if kspaces:
            spaces = []
            for ks in kspaces:
                spaces.append(
                    {
                        "name": getattr(ks, "name", "") or "",
                        "knowledge_id": getattr(ks, "knowledge_id", None),
                        "desc": getattr(ks, "desc", "") or "",
                    }
                )
        return cls(spaces=spaces, description=desc)

    @property
    def executor_id(self) -> str:
        return "knowledge"

    # ----------------------------- 输入投影(declare 纯) ------------------ #
    def declare(self, config: Any = None) -> List[Contribution]:
        text = self._render_spaces()
        if not text:
            return []
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.SYSTEM,
                content=text,
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.USER,
                order=50,
            )
        ]

    def _render_spaces(self) -> str:
        if self._spaces is not None:
            lines = []
            for i, sp in enumerate(self._spaces):
                lines.append(
                    f"{i+1}. name:{sp.get('name','')}, "
                    f"knowledge_id:{sp.get('knowledge_id','')}, "
                    f"知识库描述:{sp.get('desc','')}"
                )
            return "\n".join(lines) if lines else ""
        return self._description or ""

    def requires(self, config: Any = None) -> List[str]:
        # 真检索 executor(retriever/rag_service)本轮不走 registry(走 v1 action + legacy retriever)。
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        """检索结果回注输入(chunks/summary → USER_PART/TURN)。"""
        if not call_result:
            return []
        content = call_result if isinstance(call_result, str) else str(call_result)
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.USER_PART,
                content=f"<knowledge-context>\n{content}\n</knowledge-context>",
                lifetime=Lifetime.TURN,
                cache_scope=CacheScope.NONE,
            )
        ]

    # ----------------------------- 生命周期(无自管 I/O) ------------------- #
    async def prepare(self) -> None:
        # 水合 spaces 由旧实例构造期完成(from_legacy 复用);prepare 仅就绪标记。
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # knowledge_search 暂走 v1 KnowledgeSearch action(Route A 形态)。
        raise NotImplementedError(
            "KnowledgeCapability.execute 未收编 —— knowledge_search 暂走 v1 action"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED