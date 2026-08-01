"""EcpProposalAgent -- BAIZE 子类代码模板(约束角色/工作流/输出烤进代码)。

不是 GptsApp 数据实例,而是继承 ``ReActMasterAgent`` 的 Python 类:profile.system_prompt_template
写死提案角色/工作流/输出约束;``preload_resource`` 把 3 个提案工具注入 available_system_tools。
用户在 Agent 编辑器基于此模板建 app(提供 LLM 配置),约束全来自本类。

注册后(type_key/role="ECP_PROPOSAL_AGENT"),``create_agent_from_gpt_detail`` 经
``agent_manager.get_by_name`` 取本类实例化。runner build 该 app + initiate_chat 即跑。
"""

from __future__ import annotations

import logging

from derisk.agent import ProfileConfig
from derisk.agent.expand.react_master_agent.react_master_agent import ReActMasterAgent

logger = logging.getLogger(__name__)


ECP_PROPOSAL_SYSTEM_PROMPT = """你是 ECP 企业语义资产分析师,基于数据库表结构多轮探索并生成语义资产提案。

【角色】
你只做一件事:为指定数据源提炼 entity/metric/dimension/relation 语义资产提案。不回答业务数字、不执行业务查询、不写代码文件。

【工作流】
1. get_table_spec(datasource_id, table_name) 逐表读取结构(列/注释/采样/外键)
2. 对低基数文本列用 sample_distinct_values(datasource_id, table_name, column) 采样真实值,据此猜维度 label<->code 映射
3. propose_semantic(object_id, obj_type, payload, confidence, workspace_id) 逐个落地提案(唯一写入口,结构校验由系统执行,不合规会被拒)
4. 完成所有表后结束,给出已提案清单

【输出约束】
- 所有提案必须且只能经 propose_semantic 落地(它会校验 obj_type/payload)。不要在回复正文里编造 JSON 提案。
- id 约定:ent.<名> 实体 / mtr.<名> 指标 / rel.<a>__<b> 关系 / dim.<名> 维度
- relation 优先依据外键;非外键 join 不要凭空造
- metric.expression 必须用真实列名(如 SUM(F003)-SUM(F012));粒度 grain 用真实列
- entity 标 authoritative=true 的权威表;dimension.values 的 codes 用采样真实值、label 用业务语言猜测
- 拿不准的口径不要提,宁少不可编造;可疑点可放进后续 questions
- datasource_id / workspace_id 按任务消息传入,不要臆造

【payload 契约(严格遵守,确认时按此校验)】
- entity.payload: {"name": "中文名", "binding": {"kind": "db", "table": "表名", "datasource_id": <数据源ID>, "pk": "主键列"}}
- metric.payload: {"name": "中文名", "entity": "ent.xxx(单值字符串,关联已提案/已确认实体)", "expression": "SUM(列名)", "grain": ["可下钻维度列名"], "unit": "单位"}
- dimension.payload: {"name": "中文名", "entity": "ent.xxx", "column": "列名", "values": [{"label": "显示名", "codes": ["原始值"]}]}
- relation.payload: {"from": "ent.a", "to": "ent.b", "path": "表1.列 = 表2.列"}
- 禁止自造字段名(如 entity_bindings/table 包装),拿不准的结构以 propose_semantic 返回的 contract_gaps 提示为准修正

【边界】
所有提案只进确认收件箱(status=proposed),确认前不影响任何查询。你不是确认人,只产出候选。
"""


class EcpProposalAgent(ReActMasterAgent):
    """ECP 语义提案 Agent(BAIZE 子类,约束烤进代码)。

    profile.system_prompt_template 写死提案角色/工作流/输出约束;
    preload_resource 注入 3 个提案工具(get_table_spec/sample_distinct_values/
    propose_semantic)到 available_system_tools。无 GptsApp 级 prompt/资源依赖。
    """

    profile: ProfileConfig = ProfileConfig(
        name="EcpProposalAgent",
        role="EcpProposalAgent",
        goal="企业语义资产分析师:探索数据源表结构,多轮分析生成语义资产提案",
        system_prompt_template=ECP_PROPOSAL_SYSTEM_PROMPT,
        # 别名用于历史/兼容:ECP_PROPOSAL_AGENT 是旧注册名(已建 app 的 agent_name 可能仍是它),
        # 经 AgentAliasManager 仍能 resolve 到本类
        aliases=["ecp_proposal_agent", "ECP_PROPOSAL_AGENT"],
    )

    # 提案是批处理任务,不需要 BAIZE 的报告特性(降噪)
    # NOTE: work_log 必须开启 -- 它是工具返回结果传递回 LLM 消息历史的通道,
    # 关闭会导致 LLM 看不到工具执行结果,陷入无限重试循环
    enable_auto_report: bool = False
    enable_work_log: bool = True

    async def preload_resource(self) -> None:
        """注入 3 个提案工具到 available_system_tools(照 _inject_todo_tools 模式)。"""
        await super().preload_resource()
        await self._inject_proposal_tools()

    async def _inject_proposal_tools(self) -> None:
        """注入 sample_distinct_values / propose_semantic。

        工具经 ``build_proposal_tools`` 构造为 FunctionTool;datasource_id 与
        workspace_id 都是工具参数(Agent 按任务消息传入),不在类层绑定。

        注意: get_table_spec 由 DBCapability 提供,不需要重复定义。
        DBCapability 的 get_table_spec 已支持 datasource_id 参数。
        """
        try:
            from ..tools.proposal_tools import build_proposal_tools

            for tool in build_proposal_tools():
                if tool.name not in self.available_system_tools:
                    self.available_system_tools[tool.name] = tool
            logger.debug(
                f"[EcpProposalAgent] injected proposal tools: "
                f"{list(self.available_system_tools.keys())}"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[EcpProposalAgent] inject proposal tools failed: {e}")
