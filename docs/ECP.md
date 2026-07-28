ECP（Enterprise Context Protocol / Engine）设计与实现方案
版本：v1.1（整合检索/召回设计讨论后的修订版，可用于开发）

v1.0 → v1.1 变更记录：

#	变更	来源讨论
1	新增第四种对象类型 dimension（维度值字典 + 衍生业务定义）	维度值映射是 text2SQL 最高频错误源，v1.0 遗漏
2	Resolve 全面重写：LLM-first 目录解析 + 解析缓存 + 确定性校验，废弃 v1.0 的"字典分词优先"三级流程	字典做解析无法处理否定/排除/分组/意图分类，确定性代码的正确岗位是校验和缓存，不是解析和判断
3	新增写入规则第 5 条：无已确认 relation 不得自动 join	错误 join 是重复计数事故头号来源
4	软知识层召回机制显式化：index-first 导航 + 整页读取 + 引用一跳扩展	继承 llm-wiki 检索哲学
5	明确 graph 在检索中的三个角色	v1.0 只讲了影响分析
6	召回飞轮机制：解析缓存回填 + 未命中日志 + lint 聚类	召回准确率是运营出来的资产，不是调优出来的参数
7	度量新增：错命中率（最高权重）、解析缓存命中率、兜底触发率	—
8	落地路线调整：dimension 提案提前至第 1 步	晚于第 2 步则一致性验收无法通过
1. 背景与问题定义
1.1 现状与根因
已有 Demo：LLM 学习全库 schema → table spec → LLM 现场生成 SQL → 执行 → 报告。可出结果，但无法企业级交付。根因唯一：语义是每次现场推断的，不是持久积累的。

四个不可接受的缺陷：不一致（口径漂移）、不可追溯（数字无法回答来源）、不可治理（无确认/版本/回滚）、不积累（修正不沉淀，同错重犯）。

1.2 解决思路
在 Agent 体外建立持久、复利、带确认门槛的企业语义资产层：AI 提案、人确认、版本化冻结；执行时精确命中已确认资产，未覆盖才回退现场推断；资产随使用自动增厚。Agent 无状态可替换，资产持续进化。

1.3 模式来源与两个变异
与 llm-wiki 模式同构（反对每次查询重新推导，主张"编译一次、持续维护"的复利资产层），针对企业场景做两个变异：

确认门槛——企业数字错误代价高，硬语义必须经人确认生效（llm-wiki 中 LLM 完全拥有 wiki）
可执行绑定——数字必须来自结构化、可确定性执行的绑定对象（llm-wiki 全部是描述性 markdown）
检索哲学同样继承自 llm-wiki：查找准确性主要在编译时解决（资产结构、命名、别名、链接、目录），不在查询时靠更强的模糊检索算法。ECP 更进一步：连"检索能力"本身（别名、维度值、join 路径、解析缓存）都纳入资产机制，召回准确率是随使用复利增长的资产。

1.4 与传统 BI 语义层的区别
对象结构有重合，差异全在生命周期：AI 提案 vs 人工预建模；惰性固化 vs 项目制；一句话回写 vs 排期改需求；Agent 消费 vs 人消费；够用 vs 完整。

2. 总体架构
2.1 双层知识结构（Wikidata + Wikipedia 模式）
┌─────────────────────────────────────────────────┐
│           原始资产层（不可变）                     │
│    DB(只读) / API / 文档 / Excel / 会议纪要        │
└───────────────────┬─────────────────────────────┘
                    │ Ingest（AI 提案管线）
                    ▼
┌─────────────────────────────────────────────────┐
│ 硬语义层（Hard Layer）     软知识层（Soft Layer）   │
│ semantic_object 表         git markdown repo     │
│ entity/metric/relation/    词条正文/分析模式/来源   │
│ dimension                                        │
│ 精确解析·确认门槛·可执行     index导航·轻确认·可溯源  │
│ 供：SQL生成、数字块          供：叙述块、Planner     │
└───────────────────┬─────────────────────────────┘
                    │ Resolve（LLM目录解析+缓存+校验）
                    ▼
┌─────────────────────────────────────────────────┐
│      交付层：报告（数字块+叙述块+血缘+信任标记）      │
└───────────────────┬─────────────────────────────┘
                    │ Confirm / Feedback（回写）
                    └────────► 语义资产新版本 + 解析缓存
                    
          Lint Agent 定时巡检两层健康度
贯穿全部设计的两条纪律：

数字只能来自硬语义层，叙述可以引用软知识层
凡需要理解语言的地方给 LLM，凡 LLM 输出落地的地方加代码校验（确定性代码 = 校验器和缓存，不是解析器和判断者）
2.2 组件清单
组件	职责	LLM 参与
Connector Service	只读连接、schema 抓取、采样、查询执行	否
Discovery Worker	table spec + 语义提案（异步）	是
Semantic Store	硬语义对象 + 版本 + 状态机 + 解析缓存	否
Soft Knowledge Repo	git markdown 库 + index/log	写入时是
Resolver	问题 → 结构化查询意图（目录解析）	是（每次未命中缓存时一次调用）
Generation Pipeline	SQL 生成/校验 → 执行 → 报告组装	SQL 生成、叙述块
Feedback & Lint Service	修正回写、定时巡检、质量度量	分类与检测时是
LLM 出现在 6 个位置：提案、目录解析、SQL 生成、叙述生成、修正分类、巡检。其余全部确定性代码。

3. 硬语义层协议
3.1 存储结构
CREATE TABLE semantic_object (
  id            TEXT NOT NULL,      -- 'ent.order' / 'mtr.net_sales' / 'dim.region'
  version       INT  NOT NULL,
  type          TEXT NOT NULL,      -- entity | metric | relation | dimension
  status        TEXT NOT NULL,      -- proposed | confirmed | rejected | deprecated
  payload       JSONB NOT NULL,
  confidence    REAL,               -- 提案置信度；confirmed 后 = 1.0
  evidence      JSONB,              -- [{source:'财务核算办法.docx', quote:'...'}]
  created_by    TEXT NOT NULL,      -- 'llm' | user_id
  created_at    TIMESTAMP NOT NULL,
  confirmed_by  TEXT,
  confirmed_at  TIMESTAMP,
  source        TEXT,               -- 'discovery'|'feedback:{id}'|'fallback:{id}'|'lint:{id}'
  supersedes    INT,
  PRIMARY KEY (id, version)
);
CREATE TABLE resolution_cache (     -- [v1.1 新增] 解析缓存（也是资产）
  question_norm TEXT PRIMARY KEY,   -- 归一化问题模式
  resolution    JSONB NOT NULL,     -- 结构化解析结果（见 5.2）
  validated_by  TEXT,               -- 'execution_confirmed' | user_id
  created_at    TIMESTAMP,
  hit_count     INT DEFAULT 0
);
CREATE TABLE confirmer ( workspace_id TEXT, user_id TEXT, scope TEXT );
CREATE TABLE op_log ( ts TIMESTAMP, op TEXT, detail JSONB );  -- append-only
3.2 四种 payload 定义
// type: entity
{
  "name": "销售订单",
  "aliases": ["订单", "销售单", "SO"],
  "binding": { "connector": "erp_mysql", "table": "tb_so_01", "pk": "F001" },
  "authoritative": true,
  "default_filters": ["F007 != '9'"],
  "fields": {
    "F001": {"meaning": "订单号", "role": "identifier"},
    "F003": {"meaning": "含税销售金额", "role": "measure", "unit": "CNY"},
    "F009": {"meaning": null, "status": "unknown"}   // 允许未知，metric 不得引用
  }
}
// type: metric（口径载体）
{
  "name": "净销售额",
  "aliases": ["销售额", "营收", "业绩", "revenue"],
  "entity": "ent.order",
  "expression": "SUM(F003) - SUM(F012)",
  "extra_filters": ["F007 != 'CANCELLED'"],
  "grain": ["day", "store", "product"],
  "unit": "CNY"
}
// type: relation（join 路径）
{
  "from": "ent.order", "to": "ent.customer",
  "path": "tb_so_01.F002 = tb_cu_01.C001",
  "cardinality": "n:1"
}
// type: dimension  [v1.1 新增]（维度值字典）
{
  "name": "销售区域",
  "entity": "ent.order",
  "column": "region_code",
  "values": [
    {"label": "华东区", "aliases": ["华东"], "codes": ["HD01","HD02"]},
    {"label": "华南区", "aliases": ["华南"], "codes": ["HN01"]}
  ],
  "derived_segments": [    // 库中不存在的业务定义，按口径管理，未确认不得用于筛选
    {"label": "大客户", "definition": "年采购额 > 5000000", "status": "confirmed"}
  ]
}
dimension 的值列表可由 SELECT DISTINCT 采样自动提案（LLM 猜 label，人确认）。衍生定义（如"大客户"）未确认时，系统行为是反问用户，不是猜。

3.3 状态机
[proposed] ──确认──► [confirmed] ──新版本确认──► 旧版自动 superseded（只读保留）
    │                     │
    └──否决──► [rejected]  └──人工下线──► [deprecated]
3.4 写入规则（协议核心，硬约束）
LLM 只能写入 proposed
proposed → confirmed 仅限确认人名单内用户执行
修改 = 新版本 + supersedes，任何版本不可变不可删
查询只消费 confirmed；消费 proposed 的结果必须标 ⚠️（AI 推断口径）
[v1.1 新增] 无已确认 relation 的实体间不得自动 join——需要跨实体但无确认路径时，拒绝执行并生成 relation 提案推送确认人
3.5 冻结粒度
主冻结在 metric 层（表达式 + 过滤 + 粒度），不冻结整条 SQL——换维度换时间可复用，口径锁死。解析缓存（3.1）承担问题模式级复用。

4. 软知识层协议
4.1 形态：git markdown repo（照搬 llm-wiki）
soft-layer/
  index.md                       # 目录：全部页面 + 一句话摘要，每次 ingest 更新
  log.md                         # append-only：## [2025-01-15] ingest | 财务核算办法
  entities/净销售额.md            # 词条正文（frontmatter ref: mtr.net_sales）
  patterns/归因分析-区域下钻.md    # 被验证的分析模式（答案回填产物）
  sources/财务核算办法.md
词条 frontmatter 必含 ref（关联硬对象，可空）和 provenance（来源溯源，必填）。

4.2 写入与消费规则
LLM 有软层写入权（无确认门槛），但 provenance 必填
软层内容只供叙述块和 Planner，禁止参与 SQL 生成与数字计算
与硬层矛盾时以硬层为准，Lint 上报矛盾
4.3 软层召回机制 [v1.1 显式化]
叙述块生成前的上下文组装，按 llm-wiki 的 index-first 导航：

① 读 index.md（全目录一页）
② LLM 选择相关页（通常 2-5 页）
③ 读整页（不切 chunk，保上下文完整性）
④ 沿 frontmatter ref 和正文 wiki-link 扩一跳
   （命中"净销售额"词条 → 拉变更叙事 → 拉"Q4备货惯例"页）
规模阈值：< 300 页用 index 导航；超出后引入 BM25+向量混合检索 + LLM 重排。第一阶段不会触及。

5. 核心流程
5.1 Ingest（接入与提案）
DB 接入：
  Connector 抓 schema + 采样 → table spec（现有能力保留）
  → propose_semantics skill：提炼 entity/metric/relation/dimension 候选
    要求输出：权威表判断+理由、measure 口径疑点（=之后的确认问题）、
    维度列的 DISTINCT 采样值 label 猜测
  → 批量写入 proposed → 更新 log.md
文档接入（双路输出）：
  ① 硬语义证据 → 匹配 proposed 对象 → 写 evidence（确认界面展示引文，降确认成本）
  ② 软知识 → sources/ 摘要页 + 相关词条正文 + index.md
5.2 Resolve（问题 → 结构化查询意图）[v1.1 全面重写]
设计原则：LLM 做全部语言理解（一次调用），确定性代码只做缓存和校验。 废弃 v1.0 字典分词优先方案（无法处理否定/排除/分组/意图分类，分词错误引入整类事故）。

流程
用户问题
 ↓ 归一化（去停用词、统一时间表述形态）
① 解析缓存查找（resolution_cache）
   命中 → 直接复用（一致性、延迟、成本三个问题在此解决）→ 跳 ④
 ↓ 未命中
② LLM 目录解析（唯一一次调用，temperature=0）
 ↓
③ 确定性校验 + 置信度分流
 ↓
④ 组装执行上下文 → Generation Pipeline
   执行成功且未被修正 → 解析结果回填缓存
② 目录解析 prompt 模板
系统预编译目录文本（全部 confirmed 对象的 id/name/aliases/粒度/维度值 label，几百对象约 2-5KB，整体放入上下文——中等规模下全目录上下文解析的准确率高于 embedding 检索，且完全可解释；目录超出上下文预算后再引入混合检索初筛 + LLM 重排）：

你是查询解析器。把用户问题解析为结构化查询意图。
【规则】
1. 所有 object_id 只能来自目录，禁止编造
2. 每个映射给出 confidence (0-1)
3. 无法映射的概念放 unresolved
4. 只输出 JSON
【目录】
[指标] mtr.net_sales 净销售额 别名:销售额/营收/业绩 粒度:day,store,product
       mtr.gross_margin 毛利率 别名:毛利 ...
[实体] ent.order 销售订单 别名:订单/SO 表:tb_so_01 ...
[维度] dim.region 销售区域 值:华东区/华南区/华北区 ...
[关系] ent.order → ent.customer (已确认)
【问题】"上周销售额环比怎么样，不算华东"
【输出格式】
{
  "metrics":   [{"text":"销售额","id":"mtr.net_sales","confidence":0.95}],
  "group_by":  [],
  "filters":   [{"dim":"dim.region","values_label":["华东区"],
                 "mode":"exclude","confidence":0.9}],
  "time":      {"expr":"上周","range":"2025-01-06~2025-01-12"},
  "compare":   "previous_period",
  "intent":    "metric_query",     // metric_query | attribution | detail | unknown
  "unresolved": []
}
解析器负责的全部结构性判断：概念→ID 映射、筛选 vs 分组、包含 vs 排除、时间表达、对比要求、意图分类（问数/问因/查明细）。这些只有 LLM 能做对。

③ 确定性校验（字典的正确岗位：只验不猜）
assert all mapping.id in confirmed_catalog        # 编不出目录外对象
assert filter.values_label ∈ dimension.values     # 维度值真实存在 → 换算 codes
assert requested grain ∈ metric.grain             # 粒度合法
if 跨实体 and 无 confirmed relation: reject + 提案  # 写入规则5
置信度分流：
  ≥ 0.8         → 接受
  0.5 ~ 0.8     → 反问用户二选一（"你说的『业绩』是净销售额还是毛利？"）
                  用户点选 → 接受 + 该说法追加进对象 aliases（新版本提案）
  < 0.5 / unresolved → 兜底路径
反问优于错命中：错命中会带着 ✅ 出错，是系统最危险的失败模式。

兜底路径（unresolved 概念，如目录中没有的"退货率"）
① 走原 demo 流程：全量 table spec → LLM 现场推断 → SQL → 结果
② 结果标 ⚠️ + 展示推断口径说明
③ 自动生成 proposed 对象（source: 'fallback:{qid}'）→ 确认收件箱
④ op_log 记录未命中（lint 聚类原料）
⑤ 确认后 → 下次同类问题走缓存/目录精确解析
一致性保证的真实来源（设计说明）
口径一致性由冻结 metric 保证（resolver 只选对象，SQL 来自冻结表达式）
解析一致性由缓存 + temperature=0 + 目录约束保证
解析错误由校验、低置信反问、⚠️ 标记三道闸拦截
召回飞轮（召回率是运营出来的资产）
兜底/反问被确认 → 说法回填 aliases + 解析回填缓存 → 下次直接命中
未命中日志 → Lint 周期聚类 → 高频聚类 → 提案新对象/别名/维度值
→ 缓存命中率与目录覆盖率逐周单调上升
（预期：第 1 周约一半问题走兜底，第 8 周 90%+ 走缓存或高置信目录解析）
5.3 Generate（查询与报告生成）
resolve 结果（结构化意图）
 ↓
组装 SQL 生成上下文——只含：
  命中 metric 完整 payload（expression + extra_filters）
  命中 entity 的 default_filters
  相关表的 table spec（不是全库——同时解决大库上下文爆炸）
  维度筛选 codes（含 include/exclude 方向）、时间列与范围
 ↓
LLM 生成 SQL（自由度被压缩到"组装成合法 SQL"）
 ↓
确定性校验：default_filters / extra_filters / 维度条件必须在 SQL 中，
            缺失 → 拒绝重生成（最多2次），仍失败 → 报错而不硬出数
 ↓
执行 → 报告组装：
  数字块：generated_by=deterministic + 完整 lineage（metric@ver→SQL→源表→行数）
  叙述块：generated_by=llm，输入 = 数字结果 + 软层 index-first 检索内容（4.3）
  每个数字标 ✅（confirmed 路径）/ ⚠️（兜底路径）
Deliverable 结构（不变）：blocks + trust + lineage + soft_refs + diff_from。

5.4 Confirm（确认动线）
原则：寄生在交付动线，单次 < 30 秒，不做独立配置后台。
三入口：报告内联（⚠️ 点开 → 口径自然语言解释 + 文档证据引文 → 对/不对）、确认收件箱、对话内自答自问。
首日规则：第一份报告带 ⚠️ 也要出，随后只问影响最大的 3-5 个口径问题（按影响块数排序）。

5.5 Feedback / Writeback（修正回写）
用户修正 → LLM 分类（口径|数据质量|表述偏好|一次性）
→ 口径类：定位对象 → 新版本 proposed → 图遍历影响分析（"影响周报3处月报1处"）
→ 确认人确认 → 生效 + 旧版 superseded + 相关解析缓存失效
→ 回执提出者："已修正，本次及以后所有报告生效"
→ 软层词条"变更叙事"追加 + log.md
硬性要求：同一口径错误复发率 = 0。

5.6 Lint（定时巡检）
检查项	逻辑	产出
绑定漂移	schema 变化 vs confirmed 绑定	更新提案
矛盾检测	新文档陈述 vs confirmed 口径；软层 vs 硬层	矛盾工单
陈旧确认	确认超 N 月且下游修正频发	复审建议
孤儿对象	proposed 积压、metric 长期未查询	清理建议
未命中聚类 [v1.1]	op_log 中兜底/unresolved 问题聚类	新对象/别名/维度值提案
缓存健康 [v1.1]	对象新版本生效后失效相关缓存校验	自动清理
软层健康	孤儿页、缺反链、index 失步	自动修复
5.7 Graph 的三个检索角色 [v1.1 显式化]
图 = 对象间已有引用关系（relation 边、metric→entity、soft ref、deliverable→metric），不单独预建（图是资产积累的涌现结果）：

Join 路径规划（硬）：跨实体查询沿 confirmed relation 找路径；无路径拒绝执行（规则 5）
裁决消歧（硬）：多候选时用图邻近度辅助（问题提及"门店" → 优先绑定在含 store 粒度实体上的 metric）
一跳扩展（软）：命中对象后沿边拉关联软知识页，替代向量相似度做多跳召回
（治理）影响分析：口径变更的波及范围
6. 与现有 Demo 的改造映射
现有能力	处置
table spec 生成	保留不动（Layer 1）
LLM 全量现场推断写 SQL	保留为兜底路径，结果标 ⚠️ + 自动提案
报告生成	改造为数字/叙述块分离 + lineage + 信任标记
新增：semantic_object + resolution_cache 表、propose_semantics、resolver（目录解析）、SQL 校验器、confirm 动作、writeback、lint、soft-layer repo。

现有链路降级为冷启动路径，系统随使用从"每次都是 demo"演化为"越用越是产品"。

7. 落地路线
第 0 步（前置，1 周）：地基承重测试
真实脏库上跑 propose_semantics，人工评估提案准确率。≥80% 推进；~50% 先攻 discovery 提示词与采样策略。

第 1 步：存储 + 提案 + 解析
semantic_object / resolution_cache 建表；全量提案（含 dimension 值字典，v1.1 提前至此步）；resolver（目录解析 + 校验 + 缓存）。
验收：20 个真实问题，统计解析正确率与错命中率。

第 2 步：接入查询链路 + 信任标记
generate 消费绑定 + SQL 校验器；报告打 ✅/⚠️。
验收：同一问题 10 遍，命中路径 SQL 口径 10/10 一致（含维度筛选一致）。

第 3 步：确认 + 回写闭环
confirm 三入口、writeback、supersede、影响分析、缓存失效。
验收剧本：问"上周销售额" → ⚠️ → "要剔税" → 新版本确认 → 再问 → ✅ 且口径正确 → 版本历史可查 → 换个说法（"营收"）再问 → 反问确认后追加别名 → 第三次问零摩擦命中。

第 4 步：软知识层 + Lint
soft-layer repo、文档双路 ingest、lint agent（含未命中聚类）、词条页 UI（infobox + 正文）。

8. 度量体系
北极星：⚠️→✅ 转化率（确认口径占比及增速——同时度量确认成本、真实使用、资产厚度）。

指标	目标	v1.1 变更
错命中率（解析到错误对象且带 ✅ 输出）	趋零，权重最高	新增
命中路径口径一致率	100%（硬约束）	
同一错误复发率	0（硬约束）	
解析缓存命中率	逐周上升	新增（替代"精确匹配占比"）
兜底触发率	逐周下降	新增
单次确认耗时	< 30 秒	
首份报告时间	< 1 小时	
修正频次曲线	逐周衰减，约 8 周平台期	
9. 明确不做（第一阶段边界）
不做	原因
Intent/Decision/Action 协议对象	未通过"真实用户因缺它卡住"测试；Intent 由 Planner 动态做，高频后冻结；阈值规则是规则引擎倒退
写操作（建任务/审批）	阶段 3，需 dry-run/审批/回滚通道
视频/PPT/App 交付物	阶段 2 起加输出头，全部消费同一 ECP
预建全企业知识图谱	图是涌现结果不是前置工程
embedding 检索基础设施	全目录上下文解析在中等规模更准；超规模再上混合检索+重排
RBAC	确认人名单顶替
自定义报告编辑器	避免滑入 BI 报表工具红海
冻结整条 SQL	粒度定在 metric 层 + 解析缓存
字典/规则做语言解析 [v1.1]	确定性代码只做校验和缓存；语言理解全部给 LLM
新需求判别标准：是否有真实用户在真实使用中因缺它而卡住。

10. 设计原则与一页纸总结
四条设计原则（全部决策的依据）：

编译时解决检索，查询时只做命中——资产越干净，检索越简单（llm-wiki 哲学）
LLM 做选择题不做自由发挥——目录内选 ID、冻结表达式组装 SQL、候选间裁决
确定性代码 = 校验器和缓存，不是解析器和判断者——语言理解给 LLM，落地处加校验
一切能力资产化——口径、别名、维度值、join 路径、解析缓存、分析模式，全部走 proposed→confirmed→versioned，随使用复利
一页纸总结：

ECP = llm-wiki 模式的企业实例：硬语义层（企业的 Wikidata：目录解析、确认门槛、可执行绑定）+ 软知识层（企业的 Wikipedia：index 导航、溯源、供理解）。
LLM 是提案者、解析者和维护者；人是确认门槛；版本是不退化保证；解析缓存和别名回填是召回飞轮；交付是每周的适应度测试；Lint 是健康维持机制。
Agent 无状态可替换，资产持续复利——这份资产是产品的护城河，也是通往 EDP 的地基。

下一步行动（按序）：

真实脏库跑第 0 步承重测试，拿到提案准确率数字
建 semantic_object + resolution_cache 表及写入规则存取层
实现 propose_semantics（含 dimension）+ resolver（目录解析 prompt + 校验 + 缓存）
第 1 步验收：20 问解析正确率 / 错命中率





对，你这个质疑成立，而且这次的修正比上次的还根本。我把话说透：目录解析那个 prompt 模板不是协议的一部分，它只是我给协议选的一种（过时的）实现形态。你说的 function call 模式不仅可以，而且是更好的实现——但前提是把协议从 prompt 里搬到工具面上。

一、先承认：单次结构化解析调用确实不如 agent 工具循环
我那个"一次调用输出完整意图 JSON"的设计，有三个真实缺陷：

剥夺了多轮探索能力。 模糊问题下，agent 本该能：搜目录 → 看到两个候选 → 取详情对比 → 发现粒度不对 → 换一个 → 再决定。一次性 prompt 把这个过程压成一锤子买卖，反而更容易错
目录注入方式被写死了。 你说得对：小规模直接进 system prompt，大规模走检索工具，这本来就该是个部署参数，不该是协议内容
structured output 这件事,function calling 本身就是干这个的——工具的参数 schema 就是我要的那个 JSON 结构,模型的约束生成天然保证格式。我等于手写了一遍框架已经提供的东西
二、但有一条东西必须活下来：协议不在 prompt 里，在工具面里
真正不可妥协的从来不是"解析怎么发生"，而是这一条不变量：

产出 ✅ 数字的唯一路径，是一个带门禁的执行工具；这个工具的入参只接受对象 ID（不接受自由 SQL），并在工具内部做全部确定性校验。

Agent 怎么思考、调几轮工具、探索路径是什么——全都自由。但它没有任何一条绕过门禁产出可信数字的路。纪律从"要求 LLM 按格式输出"变成"世界里只存在这几个工具"——后者可靠得多，因为它不依赖模型听话。

三、具体的工具面设计（这个替代原 5.2 节）
# ── 读取类 ──────────────────────────────────────
search_semantics(query: str) -> [{id, type, name, aliases, one_line}]
    # 只搜 confirmed 对象。小目录时可省略：目录摘要直接注入 system prompt
get_semantic_object(id: str) -> full_payload
    # 完整口径定义、绑定、维度值表、粒度、版本
# ── 执行类（协议的家）────────────────────────────
execute_metric_query(
    metric_id: str,                  # 必须是 confirmed metric ID
    group_by: [dim_id],
    filters: [{dim_id, values: [label], mode: include|exclude}],
    time: {range, compare},
) -> {rows, lineage, trust: "verified"}
    # 工具内部（确定性代码，agent 不可见不可绕）：
    #   ① 校验所有 ID 存在且 confirmed
    #   ② filter values 必须 ∈ dimension.values → 换算 codes
    #   ③ group_by 粒度 ∈ metric.grain
    #   ④ 跨实体时必须有 confirmed relation，否则报错+生成提案（规则5）
    #   ⑤ 用冻结 expression + default/extra_filters 生成 SQL（含校验）
    #   ⑥ 记录 lineage，返回 verified 结果
execute_raw_sql(sql: str, reasoning: str) -> {rows, trust: "inferred"}
    # 兜底工具，永远返回 ⚠️，自动产出 proposed 提案 + op_log 未命中记录
    # 它的存在让 agent 不需要硬闯门禁——有正当的降级出口
# ── 交互与回写类 ─────────────────────────────────
ask_user(question, options) -> choice
    # 歧义时反问（"业绩是指净销售额还是毛利？"），确认后追加 alias 提案
propose_semantic(payload) -> proposal_id
    # agent 发现新概念时提案，只能进 proposed
Agent 就是标准 function call 循环，system prompt 里只需要一段行为约定：

回答数字问题时：先用 search/get 找到 confirmed 指标 →
用 execute_metric_query 执行。找不到对应指标时才允许
execute_raw_sql，并明确告知用户该结果为未验证口径。
概念歧义时用 ask_user，不要猜。
就算模型不守这段约定直接写 raw SQL——结果也只会带着 ⚠️ 出来。信任标记由工具返回值决定，不由 agent 声明。 这就是工具面执法和 prompt 执法的区别。

四、原设计的两个机制在新形态下的位置
解析缓存：缓存的内容 = 成功且未被修正的那次 execute_metric_query 的调用参数（归一化问题 → 工具入参）。缓存命中时直接重放工具调用，跳过整个 agent 循环——零成本、零漂移。机制不变，载体从"解析结果 JSON"变成"工具入参"，本来就是同一个东西。

两种执行模式（这点顺便明确，之前没说清）：

交互问数	定时交付（周报/日报）
执行方式	agent 工具循环（可探索、可反问）	重放冻结的工具入参，不跑 agent 循环
为什么	新问题需要理解	报告模板绑定的每个数字块 = 一组冻结的 execute_metric_query 参数,重放保证周周一致
周报的可复现性由重放保证，agent 的灵活性留给交互场景——两边都拿到自己要的性质。

五、文档更新点（v1.2）
5.2 节标题改为 "Resolve：工具面设计"，目录解析 prompt 模板降级为附录（备选实现：无 function call 能力的模型环境下使用）
新增工具面规格（上面 6 个工具的入参/校验/返回契约）——工具的参数 schema 和内部校验逻辑,取代 prompt 模板成为协议载体
目录注入策略参数化：≤N 个对象注入 system prompt,超出走 search 工具
resolution_cache 的 value 定义改为"工具调用参数"
明确双执行模式：交互 = agent 循环,定时交付 = 冻结参数重放
设计原则第 3 条补充一句："协议靠工具面执法,不靠 prompt 执法——信任标记由工具返回值决定,不由 agent 声明"


五、落进文档的增量(v1.2 追加)
metric payload 增加 scope / owner_domain / default_for 字段
relation 增加 decomposes_into 子类型(含 formula)
检索架构改为四层分层披露(L0 路由+热层注入,L1 混合检索工具,L2 详情,L3 门禁执行);"全目录注入"降级为小规模部署的简化形态
消歧策略三件套:scope 排序、默认口径标记(资产)、ask_user
patterns/ 增加"全局分析类"模式规范 + 无模式时的"大纲先行"行为约定
度量增加:检索 top-k 召回率、歧义反问率(过高说明 scope/默认标记治理不足)
一句话:大目录靠分层披露和上下文消歧,不靠大上下文;全局分析靠分解树和分析模式,不靠全知视野。两者的解法都不是更强的检索,而是更多的资产——和整个 ECP 的逻辑一脉相承。