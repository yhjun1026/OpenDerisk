"""RFC-005 注解式 args_model 测试。

ToolBase 支持可选 args_model(pydantic BaseModel),自动生成 parameters JSON Schema。
新工具用注解式(声明即定义),旧工具不改(覆盖 _define_parameters)。
execute 仍收 dict(不破坏),工具内部可选转强类型。
"""

from typing import Any, Dict, Optional

import pytest
from pydantic import BaseModel, Field

from derisk.agent.tools.base import ToolBase, ToolCategory, ToolRiskLevel
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult


# --------------------------------------------------------------------------- #
# 注解式工具(用 args_model 替代 _define_parameters)
# --------------------------------------------------------------------------- #
class _SearchArgs(BaseModel):
    query: str = Field(description="搜索查询")
    top_k: int = Field(default=5, description="返回数")


class _AnnotatedTool(ToolBase):
    """注解式工具:声明 args_model,不写 _define_parameters。"""

    args_model = _SearchArgs

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="annotated_search",
            description="annotated search tool",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
            requires_permission=False,
        )

    # 不写 _define_parameters——框架从 args_model 自动生成

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        # 可选:转入强类型对象(有补全/校验)
        typed = _SearchArgs(**args)
        return ToolResult.ok(
            output=f"searched: {typed.query} top_k={typed.top_k}",
            tool_name=self.name,
        )


# --------------------------------------------------------------------------- #
# 旧式工具(覆盖 _define_parameters,无 args_model)
# --------------------------------------------------------------------------- #
class _LegacyTool(ToolBase):
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(name="legacy_tool", description="legacy")

    def _define_parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}

    async def execute(self, args, context=None):
        return ToolResult.ok(output="legacy", tool_name=self.name)


# --------------------------------------------------------------------------- #
# args_model 自动生成 parameters
# --------------------------------------------------------------------------- #
def test_annotated_tool_generates_schema_from_args_model():
    """工具声明 args_model → parameters 自动从 pydantic schema 生成。"""
    tool = _AnnotatedTool()
    params = tool.parameters
    assert params["type"] == "object"
    assert "query" in params["properties"]
    assert "top_k" in params["properties"]
    # required 字段(query 无默认值)
    assert "query" in params.get("required", [])


def test_annotated_tool_execute_with_typed_args():
    """execute 仍收 dict,工具内部可转强类型(有补全/校验)。"""
    tool = _AnnotatedTool()
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute({"query": "hello", "top_k": 3})
    )
    assert result.success
    assert "hello" in result.output
    assert "top_k=3" in result.output


def test_annotated_tool_execute_uses_defaults():
    """top_k 有默认值,不传也能执行。"""
    tool = _AnnotatedTool()
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        tool.execute({"query": "test"})
    )
    assert result.success
    assert "top_k=5" in result.output


# --------------------------------------------------------------------------- #
# 旧工具不受影响(无 args_model,走 _define_parameters)
# --------------------------------------------------------------------------- #
def test_legacy_tool_still_uses_define_parameters():
    """旧工具无 args_model → parameters 来自 _define_parameters(兼容)。"""
    tool = _LegacyTool()
    params = tool.parameters
    assert params["properties"]["q"]["type"] == "string"
    assert "query" not in params["properties"]  # 不是 args_model 的query


def test_legacy_tool_without_args_model_no_crash():
    """旧工具不声明 args_model,_resolve_parameters 不报错。"""
    tool = _LegacyTool()
    assert tool.parameters is not None
    assert tool.name == "legacy_tool"


# --------------------------------------------------------------------------- #
# args_model 优先于 _define_parameters(若同时存在)
# --------------------------------------------------------------------------- #
class _BothTool(ToolBase):
    args_model = _SearchArgs

    def _define_metadata(self):
        return ToolMetadata(name="both", description="both")

    def _define_parameters(self):
        return {"type": "object", "properties": {"legacy_field": {"type": "string"}}}

    async def execute(self, args, context=None):
        return ToolResult.ok(output="", tool_name=self.name)


def test_args_model_takes_priority_over_define_parameters():
    """同时有 args_model 和 _define_parameters → args_model 优先。"""
    tool = _BothTool()
    params = tool.parameters
    # args_model 的 query 出现,legacy_field 不出现
    assert "query" in params["properties"]
    assert "legacy_field" not in params["properties"]