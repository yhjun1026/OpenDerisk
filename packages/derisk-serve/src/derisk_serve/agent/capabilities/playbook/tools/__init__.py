"""Playbook capability 自管工具(RFC-005,serve 层)。

5 个剧本内置工具(get_playbook_info/get_playbook_text_content/
get_playbook_skills/get_playbook_resources/get_playbook_deliverables)。

从 resource.py 内联拆出 tools/ 自管目录。工具实现在本目录,通过
build_playbook_tools(config) 返回 List[FunctionTool] 供 declare 注入 TOOLS 槽。
"""

from .playbook_tools import build_playbook_tools  # noqa: F401

__all__ = ["build_playbook_tools"]
