"""KnowledgeSearchTool —— 知识库 capability 自管工具(RFC-005)。

权威的 knowledge_search 工具(ToolBase 形态),从旧 tools/builtin/agent/agent_tools.py
迁入 capability 自管目录。淘汰旧 KnowledgeSearch(AgentAction 旧 v1)。
归属 capability_id="knowledge",由 KnowledgeTool 通过 knowledge_client
(ToolContext 注入)检索,结果可经 KnowledgeCapabilityResource.consume 回注输入。
"""

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from derisk.agent.tools.base import ToolBase, ToolCategory, ToolRiskLevel
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult

logger = logging.getLogger(__name__)


class KnowledgeSearchArgs(BaseModel):
    """knowledge_search 工具参数(注解式,RFC-005)。"""

    query: str = Field(description="Search query for the knowledge base")
    top_k: int = Field(default=5, description="Number of results to return")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Optional filters for knowledge search")


class KnowledgeSearchTool(ToolBase):
    """知识检索工具(知识库 capability 自管,注解式 args_model)。

    通过 ToolContext.get_resource("knowledge_client") 拿检索客户端执行 search,
    结果交由 KnowledgeCapabilityResource.consume 回注输入(RAG 语义)。
    注解式:args_model 声明参数,parameters 自动生成,不写 _define_parameters。
    """

    args_model = KnowledgeSearchArgs

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="knowledge_search",
            display_name="Knowledge Search",
            description="Search the knowledge base for relevant information",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
            tags=["knowledge", "search", "rag", "retrieval"],
            timeout=60,
            capability_id="knowledge",
        )

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        # 注解式:工具内部可选转强类型(有补全/校验)
        typed = KnowledgeSearchArgs(**args)
        query = typed.query
        top_k = typed.top_k
        filters = typed.filters

        if not query:
            return ToolResult.fail(error="Search query cannot be empty", tool_name=self.name)

        try:
            knowledge_client = None
            if context:
                knowledge_client = context.get_resource("knowledge_client")

            if not knowledge_client:
                return ToolResult.fail(
                    error="Knowledge base not available", tool_name=self.name
                )

            results = await knowledge_client.search(
                query=query, top_k=top_k, filters=filters
            )

            if not results:
                return ToolResult.ok(
                    output="No relevant results found",
                    tool_name=self.name,
                    metadata={"query": query, "results_count": 0},
                )

            formatted = []
            for i, result in enumerate(results, 1):
                score = result.get("score", 0)
                content = result.get("content", "")
                source = result.get("source", "unknown")
                formatted.append(f"[{i}] (score: {score:.2f}) [{source}]\n{content}")

            return ToolResult.ok(
                output="\n\n".join(formatted),
                tool_name=self.name,
                metadata={"query": query, "results_count": len(results)},
            )

        except Exception as e:
            logger.error(f"[KnowledgeSearchTool] Search failed: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)