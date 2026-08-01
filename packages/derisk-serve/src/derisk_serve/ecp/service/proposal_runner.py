"""Proposal runner: workspace-level, all registered assets as dynamic resources.

Trigger proposal generation for a workspace: gather all registered asset refs
(``ecp_asset_ref``), convert them to dynamic resources (db -> ``datasource`` so
``DBCapability`` materializes and injects db info + table list into the prompt;
doc/space -> ``knowledge_pack``), pass them to ``build_agent_by_app_code``, then
run the BAIZE proposal Agent (``EcpProposalAgent`` template) via
``UserProxyAgent.initiate_chat``.

The Agent discovers tables via the injected DBCapability (not a hardcoded list),
explores each (get_table_spec -> sample_distinct_values -> propose_semantic) in
its ReAct loop until all assets are done. Mirrors chat flow build + initiate_chat
(agent_chat.py:3170-3192).
"""

import logging
import uuid
from typing import Optional

from ..api.schemas import GenerateProposalsVO
from ..config import DEFAULT_WORKSPACE_ID, STATUS_PROPOSED

logger = logging.getLogger(__name__)


def _proposed_ids(workspace_id: str) -> set:
    """Return the set of proposed object ids in a workspace (best-effort)."""
    from ..models.models import SemanticObjectDao

    try:
        vo = SemanticObjectDao().list_latest(
            workspace_id=workspace_id, status=STATUS_PROPOSED, page=1, page_size=1000
        )
        return {it.id for it in (vo.items or [])}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp-proposal-runner] count proposed failed: {e}")
        return set()


def _assets_to_dynamic_resources(workspace_id: str, result: GenerateProposalsVO):
    """Convert registered asset refs into dynamic AgentResources.

    db -> ``datasource`` (DBCapability injects db info + table list);
    doc/space -> ``knowledge_pack`` (KnowledgeCapability injects space list);
    api -> skipped (P3). db assets whose db_name can't be resolved are skipped
    with an error recorded.
    """
    from derisk.agent.resource.base import AgentResource

    from ..models.models import AssetRefDao

    dyn = []
    try:
        assets = AssetRefDao().list(workspace_id) or []
    except Exception as e:  # noqa: BLE001
        result.errors.append(f"读取登记资产失败: {e}")
        return dyn

    for a in assets:
        if a.kind == "db":
            try:
                ds_id = int(a.ref_id)
            except (TypeError, ValueError):
                result.errors.append(f"db 资产 ref_id 非法: {a.ref_id}")
                continue
            try:
                from derisk_serve.datasource.manages.connect_config_db import (
                    ConnectConfigDao,
                )

                cfg = ConnectConfigDao().get_one({"id": ds_id})
                db_name = getattr(cfg, "db_name", None)
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"db 资产 {a.ref_id} 查询失败: {e}")
                continue
            if not db_name:
                result.errors.append(f"db 资产 {a.ref_id} 无 db_name(未就绪),跳过")
                continue
            dyn.append(
                AgentResource(
                    type="datasource",
                    value={"db_id": ds_id, "db_name": db_name},
                    is_dynamic=True,
                )
            )
        elif a.kind in ("document", "space"):
            name = (a.ref_meta or {}).get("name") or a.ref_id
            dyn.append(
                AgentResource(
                    type="knowledge_pack",
                    value={"knowledges": [{"name": name, "knowledge_id": a.ref_id}]},
                    is_dynamic=True,
                )
            )
        # api: P3, skipped
    return dyn


async def run_proposal_agent(
    system_app,
    app_code: str,
    workspace_id: Optional[str] = None,
    domain_hint: Optional[str] = None,
) -> GenerateProposalsVO:
    """Run the BAIZE proposal Agent over ALL registered assets of a workspace.

    Args:
        system_app: SystemApp (to resolve AgentChat).
        app_code: the selected proposal agent app (proposal_agent_id); should be
            based on the ECP_PROPOSAL_AGENT template.
        workspace_id: ECP workspace whose registered assets to propose for.
        domain_hint: optional domain context (prepended to the task message).
    """
    from derisk.agent import AgentContext, UserProxyAgent
    from derisk.component import ComponentType
    from derisk.core import HumanMessage
    from derisk_serve.agent.agents.chat.agent_chat import AgentChat, get_app_service

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    # datasource_id=0 marks a workspace-level (multi-asset) run
    result = GenerateProposalsVO(datasource_id=0)

    dyn = _assets_to_dynamic_resources(ws, result)
    if not dyn:
        if not result.errors:
            result.errors.append(f"工作空间 {ws} 无可用登记资产")
        return result

    try:
        # AgentChat is NOT a registered component (it's an attribute of the
        # AgentsController / MULTI_AGENTS). build_agent_by_app_code uses the
        # global resource_manager + get_app_service, so a fresh SimpleAgentChat
        # instance works (its init_app is idempotent).
        from derisk_serve.agent.agents.chat.agent_chat_simple import SimpleAgentChat

        agent_chat = SimpleAgentChat(system_app)
    except Exception as e:  # noqa: BLE001
        result.errors.append(f"AgentChat 不可用: {e}")
        return result

    try:
        app = await get_app_service().app_detail(app_code, building_mode=False)
    except Exception as e:  # noqa: BLE001
        result.errors.append(f"找不到提案 Agent {app_code}: {e}")
        return result

    conv_id = f"ecp_proposal_ws{ws}_{uuid.uuid4().hex[:8]}"
    context = AgentContext(
        conv_id=conv_id,
        conv_session_id=conv_id,
        gpts_app_code=app_code,
        gpts_app_name=getattr(app, "app_name", app_code) or app_code,
        agent_app_code=app_code,
        extra={"dynamic_resources": dyn},  # Pass dynamic resources via extra
    )
    agent_memory = agent_chat.get_or_build_agent_memory(conv_id, app.app_name)

    logger.info(
        f"[ecp-proposal-runner] build agent {app_code} ws={ws} "
        f"assets={len(dyn)} conv={conv_id}"
    )
    try:
        # dynamic_resources now passed via context.extra, no need to pass here
        recipient = await agent_chat.build_agent_by_app_code(
            app_code, context, agent_memory
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[ecp-proposal-runner] build agent failed: {e}")
        result.errors.append(f"构建 Agent 失败: {e}")
        return result

    before = _proposed_ids(ws)

    user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()

    task = (
        f"为工作空间 {ws} 的所有登记资产生成企业语义资产提案。"
        f"已为你注入所有登记资产(库/文档)为资源。"
        f"请逐库逐表用 get_table_spec(datasource_id=<database.datasource_id>, table_name='表名') 读取结构，"
        f"对低基数文本列用 sample_distinct_values 采样，"
        f"用 propose_semantic(..., workspace_id={ws}) 逐个落地 "
        f"entity/metric/dimension/relation 提案。所有资产全部完成后结束。"
    )
    if domain_hint:
        task = f"【领域背景】{domain_hint}\n\n{task}"
    logger.info(f"[ecp-proposal-runner] initiate_chat task for ws={ws}")
    try:
        await user_proxy.initiate_chat(
            recipient=recipient, message=HumanMessage(content=task)
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[ecp-proposal-runner] agent run failed: {e}")
        result.errors.append(f"Agent 运行失败: {e}")

    after = _proposed_ids(ws)
    new_ids = sorted(after - before)
    result.proposals_created = len(new_ids)
    result.proposal_ids = new_ids
    logger.info(
        f"[ecp-proposal-runner] done ws={ws}: +{result.proposals_created} "
        f"proposals {new_ids}"
    )
    return result
