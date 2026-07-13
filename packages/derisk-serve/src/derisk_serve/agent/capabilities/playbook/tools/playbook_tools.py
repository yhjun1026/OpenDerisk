"""Playbook capability 自管工具实现(RFC-005,serve 层)。

5 个剧本内置工具:让 Agent 读取当前绑定的剧本信息。
从 resource.py 内联拆出 tools/ 自管目录。
"""

from typing import Any, Dict, List

from derisk.agent.resource.tool.base import FunctionTool


def _get_playbook_info(config) -> Dict[str, Any]:
    """获取当前剧本的基本信息。"""
    return {
        "playbook_id": config.playbook_id,
        "playbook_name": config.playbook_name,
        "has_text_content": bool(config.text_content.to_dict()),
        "skills_count": len(config.skills),
        "resources_count": len(config.resources),
        "deliverables_count": len(config.deliverables),
    }


def _get_playbook_text_content(config) -> Dict[str, Any]:
    """获取剧本的独立文本部分。"""
    return {
        "playbook_id": config.playbook_id,
        "playbook_name": config.playbook_name,
        "text_content": config.text_content.to_dict(),
    }


def _get_playbook_skills(config) -> Dict[str, Any]:
    """获取剧本定义的技能列表。"""
    return {
        "playbook_id": config.playbook_id,
        "playbook_name": config.playbook_name,
        "skills": config.skills,
    }


def _get_playbook_resources(config) -> Dict[str, Any]:
    """获取剧本定义的资源列表。"""
    return {
        "playbook_id": config.playbook_id,
        "playbook_name": config.playbook_name,
        "resources": config.resources,
    }


def _get_playbook_deliverables(config) -> Dict[str, Any]:
    """获取剧本定义的产出物列表。"""
    return {
        "playbook_id": config.playbook_id,
        "playbook_name": config.playbook_name,
        "deliverables": config.deliverables,
    }


def build_playbook_tools(config) -> List[FunctionTool]:
    """构建剧本内置工具列表。

    这些工具让 Agent 能够读取当前绑定的剧本信息:
    - get_playbook_info: 获取剧本基本信息
    - get_playbook_text_content: 获取剧本文本内容
    - get_playbook_skills: 获取剧本技能列表
    - get_playbook_resources: 获取剧本资源列表
    - get_playbook_deliverables: 获取剧本产出物列表
    """
    specs = [
        ("get_playbook_info", "获取当前剧本的基本信息", _get_playbook_info),
        ("get_playbook_text_content", "获取剧本的独立文本部分（workflow, role 等）", _get_playbook_text_content),
        ("get_playbook_skills", "获取剧本定义的技能列表", _get_playbook_skills),
        ("get_playbook_resources", "获取剧本定义的资源列表", _get_playbook_resources),
        ("get_playbook_deliverables", "获取剧本定义的产出物列表", _get_playbook_deliverables),
    ]

    tools: List[FunctionTool] = []
    for name, desc, fn in specs:
        def make_tool(fn=fn, name=name, desc=desc):
            def _wrapped(**kwargs):
                return fn(config)

            _wrapped.__name__ = name
            return FunctionTool(name, _wrapped, description=desc)

        tools.append(make_tool())
    return tools
