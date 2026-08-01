"""Proposal runner: drive a standard BAIZE agent to generate ECP proposals.

Replaces the custom httpx ReAct loop (the old EcpProposalAgent). The selected
BAIZE agent (``proposal_agent_id`` in ECP workspace config) is built via
``AgentChat.build_agent_by_app_code`` with an ``EcpProposalCapability`` injected
as a dynamic resource (3 proposal tools + workflow prompt), then run with a
proposal task via ``UserProxyAgent.initiate_chat`` -- the standard agent loop.

Proposals land via the ``propose_semantic`` tool -> ``SemanticObjectDao`` (always
``proposed``; confirmation gate unchanged). Returns counts (new proposed objects
this run).

Mirrors the chat flow's build + initiate_chat pattern (agent_chat.py:3170-3192).
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


async def run_proposal_agent(
    system_app,
    app_code: str,
    datasource_id: int,
    workspace_id: Optional[str] = None,
    domain_hint: Optional[str] = None,
) -> GenerateProposalsVO:
    """Run the selected BAIZE agent as the ECP proposal agent.

    Args:
        system_app: SystemApp (to resolve AgentChat).
        app_code: the selected agent's app_code (proposal_agent_id).
        datasource_id: the datasource to propose for (passed in the task message;
            tools take it as a parameter).
        workspace_id: ECP workspace (bound into the injected capability).
        domain_hint: optional domain context.
    """
    from derisk.agent import AgentContext, UserProxyAgent
    from derisk.agent.resource.base import AgentResource
    from derisk.component import ComponentType
    from derisk.core import HumanMessage
    from derisk_serve.agent.agents.chat.agent_chat import AgentChat, get_app_service

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    result = GenerateProposalsVO(datasource_id=datasource_id)

    # 1. resolve AgentChat
    try:
        agent_chat = system_app.get_component(ComponentType.AGENT_CHAT, AgentChat)
    except Exception as e:  # noqa: BLE001
        result.errors.append(f"AgentChat 组件不可用: {e}")
        return result

    # 2. resolve the selected agent app
    try:
        app = await get_app_service().app_detail(app_code, building_mode=False)
    except Exception as e:  # noqa: BLE001
        result.errors.append(f"找不到提案 Agent {app_code}: {e}")
        return result

    # 3. synthetic context + memory for a batch (no chat UI / real user)
    conv_id = f"ecp_proposal_{datasource_id}_{uuid.uuid4().hex[:8]}"
    context = AgentContext(
        conv_id=conv_id,
        conv_session_id=conv_id,
        gpts_app_code=app_code,
        gpts_app_name=getattr(app, "app_name", app_code) or app_code,
        agent_app_code=app_code,
    )
    agent_memory = agent_chat.get_or_build_agent_memory(conv_id, app.app_name)

    # 4. inject EcpProposalCapability as a dynamic resource
    dyn = AgentResource(
        type="ecp_proposal",
        value={"workspace_id": ws, "domain_hint": domain_hint or ""},
        is_dynamic=True,
    )

    logger.info(
        f"[ecp-proposal-runner] build agent {app_code} for ds{datasource_id} ws={ws} "
        f"conv={conv_id}"
    )
    try:
        recipient = await agent_chat.build_agent_by_app_code(
            app_code, context, agent_memory, dynamic_resources=[dyn]
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[ecp-proposal-runner] build agent failed: {e}")
        result.errors.append(f"构建 Agent 失败: {e}")
        return result

    # 5. count proposed before
    before = _proposed_ids(ws)

    # 6. run the standard agent loop with a proposal task
    user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()
    task = (
        f"为数据源 {datasource_id} 生成企业语义资产提案。"
        f"请用 get_table_spec(datasource_id={datasource_id}, table_name=...) "
        f"逐表读取结构，对低基数文本列用 sample_distinct_values 采样真实值，"
        f"再用 propose_semantic 逐个落地 entity/metric/dimension/relation 提案。"
        f"完成所有表后结束。"
    )
    logger.info(f"[ecp-proposal-runner] initiate_chat task for ds{datasource_id}")
    try:
        await user_proxy.initiate_chat(
            recipient=recipient, message=HumanMessage(content=task)
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[ecp-proposal-runner] agent run failed: {e}")
        result.errors.append(f"Agent 运行失败: {e}")

    # 7. count new proposed objects this run
    after = _proposed_ids(ws)
    new_ids = sorted(after - before)
    result.proposals_created = len(new_ids)
    result.proposal_ids = new_ids
    logger.info(
        f"[ecp-proposal-runner] done ds{datasource_id}: +{result.proposals_created} "
        f"proposals {new_ids}"
    )
    return result
