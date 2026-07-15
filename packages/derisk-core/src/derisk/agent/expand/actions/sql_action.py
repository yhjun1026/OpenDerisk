"""SQL Action Module —— execute_sql 专用 Action。

背景:`execute_sql` 工具的返回值是 `d-sql-query` vis 组件渲染成的 markdown
(``` ```d-sql-query\n{json}\n``` ```)。通用 ToolAction 把这段 vis markdown 同时
塞进 ActionOutput.content(给模型)和 view(给前端),导致模型看到的工具结果不是
干净的查询数据,而是 vis 包裹体。

SqlAction 只接管 execute_sql(parse_action 按工具名命中),在 ToolAction.run 之后
做 content/view 职责分离:
- content:从 vis markdown 提取出的结构化 JSON(给模型,含 sql/columns/rows/分页等)
- view  :原 `d-sql-query` vis markdown(给前端,继续由 vis 组件渲染)
"""

import json
import logging
import re
from typing import Any, Optional

from ...core.action.base import ToolCall

from .tool_action import ToolAction, ToolInput

logger = logging.getLogger(__name__)

# 复用 derisk_vis_manus_converter._VIS_SQL_QUERY_RE 的模式:
#   ```d-sql-query
#   {json}
#   ```
_VIS_SQL_QUERY_RE = re.compile(r"```d-sql-query\s*\n(.*?)\n```", re.DOTALL)


def extract_sql_json(vis_text: str) -> Optional[dict]:
    """从 `d-sql-query` vis markdown 中提取结构化结果 dict。

    输入形如:
        ```d-sql-query
        {"sql": ..., "columns": [...], "rows": [...], ...}
        ```

    Returns:
        解析后的 dict;若输入不含合法 d-sql-query 块则返回 None。
    """
    if not isinstance(vis_text, str) or not vis_text:
        return None
    match = _VIS_SQL_QUERY_RE.search(vis_text)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"[SqlAction] extract_sql_json parse failed: {e}")
    return None


class SqlAction(ToolAction):
    """execute_sql 专用 Action:content 给模型结构化 JSON,view 给前端 d-sql-query vis。"""

    # 本 Action 仅接管存在"vis 污染 content"问题的工具;
    # get_table_spec 返回的是 schema 纯文本,无此问题,仍走通用 ToolAction。
    _SQL_TOOL_NAMES = ("execute_sql",)

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional["Action"] = None,
        resource: Optional[Any] = None,
        **kwargs,
    ) -> Optional["SqlAction"]:
        """只对 execute_sql 命中;其他工具返回 None 落到 ToolAction。"""
        if tool_call.name in cls._SQL_TOOL_NAMES:
            return cls(
                action_uid=tool_call.tool_call_id,
                action_input=ToolInput(
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.tool_call_id,
                    thought=tool_call.thought,
                    args=tool_call.args,
                ),
            )
        return None

    async def run(self, *args: Any, **kwargs: Any):
        """复用 ToolAction.run 完成执行/截断/归档/view 生成,再就地分离 content/view。

        super().run 返回的 ActionOutput.content 此刻是 d-sql-query vis markdown(因为
        execute_sql 工具就返回这个)。我们把它拆成:content=结构化 JSON(给模型),
        view=原 vis markdown(给前端)。提取失败时不劣化,原样返回。
        """
        out = await super().run(*args, **kwargs)
        if out is None:
            return None

        structured = extract_sql_json(out.content)
        if structured is not None:
            # content:结构化 JSON 给模型(不含 ```d-sql-query 包裹)。
            out.content = json.dumps(structured, ensure_ascii=False)
            # view 不动:super().run 已通过 gen_view 把原 d-sql-query vis markdown 包进
            # VisTool 壳写入 out.view,供前端渲染。前端结构化数据由 converter 从 content
            # 提取,改后走其 fallback(纯 JSON 分支)仍可拿到。
        return out