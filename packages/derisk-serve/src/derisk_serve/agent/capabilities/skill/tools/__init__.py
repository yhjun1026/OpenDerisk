"""Skill capability 自管工具(RFC-005,serve 层)。

Skill 工具只有两个:
- Skill(read_skill): 读取技能的 SKILL.md 内容
- skill_list: 列出所有可用技能

注:skill_exec(在技能目录执行脚本)是沙箱执行能力(SandboxToolBase),
归 sandbox capability,不在此目录。
"""

from .read_skill import ReadSkillTool  # noqa: F401
from .list_skills import ListSkillsTool  # noqa: F401

__all__ = ["ReadSkillTool", "ListSkillsTool"]


def register_tools(registry) -> None:
    """注册 skill capability 工具(capability_id="skill")。"""
    from .read_skill import ReadSkillTool
    from .list_skills import ListSkillsTool
    from derisk.agent.tools.base import ToolSource
    for tool_cls in [ReadSkillTool, ListSkillsTool]:
        registry.register(tool_cls(), source=ToolSource.SYSTEM)
