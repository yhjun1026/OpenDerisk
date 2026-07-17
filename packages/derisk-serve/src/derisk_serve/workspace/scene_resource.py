"""WorkspaceSceneResource — RFC-005 资源协议实现(场景空间 lobby 资源)。

包含:
- SYSTEM 槽:静态框架(workspace_name + 四类管理工具使用引导),零 I/O
- TOOLS 槽:任务/剧本/介入/产物交付资产 管理工具全集(读+写)

设计:declare 纯函数;workspace_name 由装配器查 DB 填入 config;实时数据靠工具查。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

from derisk.agent.resource.tool.base import FunctionTool
from derisk.core.interface.resource.bundle import (
    CacheScope, Contribution, Lifetime, Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

from derisk_serve.workspace.agent_tools.read_tools import build_read_tools
from derisk_serve.workspace.agent_tools.write_tools import build_scene_write_tools


@dataclass
class WorkspaceSceneConfig:
    workspace_id: int
    conv_uid: str
    workspace_name: str


def build_scene_management_tools(workspace_id: int, conv_uid: str) -> List[FunctionTool]:
    """四类管理工具全集:读(build_read_tools,10)+ 写(build_scene_write_tools,10)。

    system_app 取自全局 Config —— 此函数在请求上下文外(资源协议 declare)被调用,
    无法从请求取 system_app,故走全局单例 Config().SYSTEM_APP(运行时由 SystemApp
    初始化设置,见 derisk_app.base)。工具仅在此绑定闭包,不发起服务调用;真正调用
    工具时 system_app 已就绪。
    """
    from derisk._private.config import Config
    system_app = Config().SYSTEM_APP
    reads = build_read_tools(system_app, workspace_id)
    writes = build_scene_write_tools(
        system_app, workspace_id, user_id=None, conv_uid=conv_uid, task_id=None,
    )
    return reads + writes


class WorkspaceSceneResource(ResourceProtocol):
    capability_id: str = "workspace_scene"

    @classmethod
    def declare(cls, config: WorkspaceSceneConfig) -> List[Contribution]:
        contributions: List[Contribution] = []
        contributions.append(Contribution(
            capability_id="workspace_scene:system",
            slot=Slot.SYSTEM,
            content=cls._render_system_framework(config),
            lifetime=Lifetime.SESSION, cache_scope=CacheScope.USER, order=0,
        ))
        for tool in build_scene_management_tools(config.workspace_id, config.conv_uid):
            contributions.append(Contribution(
                capability_id=f"workspace_scene:tool:{tool.name}",
                slot=Slot.TOOLS, content=tool,
                lifetime=Lifetime.CONFIG_STATIC, cache_scope=CacheScope.NONE, order=0,
            ))
        return contributions

    @staticmethod
    def _render_system_framework(config: WorkspaceSceneConfig) -> str:
        # Tool names below MUST exist in build_scene_management_tools output
        # (reads: list_tasks, get_task_info, list_artifacts, list_deliveries,
        # list_assets, get_workspace_memory, list_workspace_members,
        # list_playbooks, get_playbook_detail, list_interventions;
        # writes: start_task, close_task, publish_asset, create_delivery,
        # update_workspace, create_playbook, update_playbook,
        # delete_playbook, resolve_intervention, abort_intervention).
        # Do NOT reference tools the agent doesn't have (e.g. create_task).
        return (
            f"# 场景空间:{config.workspace_name}\n"
            "你是场景空间助手。可管理任务、剧本、介入、产物/交付/资产。\n"
            "- 看任务:list_tasks(可按状态过滤);细节 get_task_info。发起:start_task;关闭:close_task。\n"
            "- 看剧本:list_playbooks;细节 get_playbook_detail。管理:create_playbook/update_playbook/delete_playbook。\n"
            "- 介入:list_interventions 看待介入;处理:resolve_intervention/abort_intervention。\n"
            "- 产物/交付/资产:list_artifacts/list_deliveries/list_assets。\n"
            "实时数量与详情通过上述工具按需查找,不在此列出。\n"
        )

    @staticmethod
    def to_agent_resource(config: "WorkspaceSceneConfig"):
        """序列化 WorkspaceSceneConfig 为 AgentResource(type="workspace_scene")。

        RFC-006 SSR Task 5:供 SceneResourceAssembler 装配 lobby 资源,并由
        CapabilityFactoryRegistry.build_pack 还原为 Contribution。

        序列化 config(workspace_id / conv_uid / workspace_name),使 factory
        反序列化时零 I/O(无需 DB refetch)。与 PlaybookResource.to_agent_resource
        (Task 4)对齐同模式。

        Args:
            config: 场景空间配置

        Returns:
            AgentResource(type="workspace_scene", value=<config JSON>)
        """
        import json as _json

        from derisk.agent.resource.base import AgentResource

        value = _json.dumps({
            "workspace_id": config.workspace_id,
            "conv_uid": config.conv_uid,
            "workspace_name": config.workspace_name,
        }, ensure_ascii=False)
        return AgentResource(
            type="workspace_scene",
            name=f"workspace_scene_{config.workspace_id}",
            value=value,
        )
