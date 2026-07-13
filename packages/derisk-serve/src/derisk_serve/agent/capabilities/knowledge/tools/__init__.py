"""Knowledge capability 自管工具(RFC-005)。

knowledge_search 权威实现在此(capability_id="knowledge"),
淘汰旧 KnowledgeSearch(AgentAction v1)和旧 agent_tools.KnowledgeTool。
"""

from .search import KnowledgeSearchTool  # noqa: F401

__all__ = ["KnowledgeSearchTool"]


def register_tools(registry) -> None:
    """注册 knowledge capability 的工具到 ToolRegistry。"""
    from .search import KnowledgeSearchTool
    from derisk.agent.tools.base import ToolSource
    registry.register(KnowledgeSearchTool(), source=ToolSource.CORE)