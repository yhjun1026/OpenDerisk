# ECP 实施方案（基于 OpenDerisk 现有代码落地设计）

版本：v0.3（2026-07-28，补全 Lint 差距分析与完整交互设计）
对应设计文档：`docs/ECP.md` v1.1 + v1.2 追加讨论（工具面执法、semantic_edge、分层披露）

**模块形态决策（v0.2 定稿）：新建独立 `derisk_serve/ecp` 模块，单向依赖复用
knowledge / datasource / cron 模块。不建在 knowledge 内部（硬层与 vault 粒度、
关切完全不同，会双向污染），也不完全另起炉灶（软层重写是浪费）。
依赖方向：ecp → knowledge/datasource/cron，反向无依赖，knowledge 对 ECP 无感知。**

---

## 0. 核心判断

ECP 不是从零建设。现状盘点后的三个关键事实：

1. **软知识层已经建成**——`derisk_serve/knowledge` 就是 llm-wiki 模式的完整实现
   （wiki/index.md/log.md、L0/L1/L2 三层、ingest LLM 管线、实体归并、graph 检索、
   20 个 Agent 工具、前端页面）。ECP 的软层 = 一个定制 schema 的 knowledge space。
2. **Connector + table spec 已经建成**——`derisk_serve/datasource` 的
   `SchemaLearningService`（含采样、LLM 表描述、Schema Linking）就是 ECP 的 Layer 1，
   文档要求"保留不动"。
3. **硬语义层完全不存在**——这是唯一的核心新建模块，也是本方案的主体。

因此落地策略：**新建一个 `derisk_serve/ecp` serve 模块承载硬语义层与工具面，
软层复用 knowledge、执行复用 datasource、调度复用 cron、交互复用 intervention/Vis 组件。**

## 1. 总体架构映射

```
┌─────────────────────────── 原始资产层 ───────────────────────────┐
│ DB: derisk_serve/datasource (已有, 不动)                          │
│ API: ecp/api_resource (新建, 首期做薄)                            │
│ 文档: knowledge ingest extractors (已有, 补 Excel)                │
└──────────────┬──────────────────────────────────────────────────┘
               │ Ingest (AI 提案管线)
               ▼
┌────────────────────────── 语义资产层 ────────────────────────────┐
│ 硬语义层 [新建 derisk_serve/ecp]      软知识层 [复用 knowledge]    │
│ ecp_semantic_object                 每 workspace 一个 ECP 专用     │
│ entity/metric/relation/dimension    space (定制 schema.md)         │
│ ecp_resolution_cache                sources + index.md/log.md     │
│ ecp_semantic_edge (物化投影)        edges 表 (软层图)              │
│ ecp_op_log / ecp_confirmer                                       │
│                                                                   │
│ 提案来源: propose_semantics skill ← table_spec + 采样 + 文档证据   │
└──────────────┬──────────────────────────────────────────────────┘
               │ Resolve (工具面, v1.2)
               ▼
┌────────────────────────── 执行与交付 ────────────────────────────┐
│ 6 个 ECP 工具注册进 tool_registry, 由现有 Agent 循环消费:          │
│   search_semantics / get_semantic_object                         │
│   execute_metric_query (门禁, 唯一 ✅ 路径)                       │
│   execute_raw_sql (兜底, 包装现有 execute_sql, 永远 ⚠️)           │
│   ask_user (复用 InteractionService) / propose_semantic          │
│ SQL 执行 → ConnectorManager.get_connector().run() (已有只读闸门)  │
└──────────────────────────────────────────────────────────────────┘
```

## 2. 新建模块：derisk_serve/ecp

照 Usage serve 骨架（commit aa3fa198 模板）：

```
packages/derisk-serve/src/derisk_serve/ecp/
├── config.py            # ServeConfig + @auto_register_resource
├── serve.py             # Serve(BaseServe): init_app/on_init/before_start
├── models/models.py     # 5 张表 Entity + DAO
├── service/
│   ├── service.py       # Service(BaseService): 对象 CRUD + 状态机
│   ├── catalog.py       # 目录编译 (confirmed 对象 → 目录文本/检索)
│   ├── resolver.py      # 解析缓存查找/回填 + 确定性校验器
│   ├── executor.py      # execute_metric_query 门禁核心 (SQL 组装+校验+执行)
│   ├── propose.py       # propose_semantics 管线 (DB/API/文档三路)
│   ├── confirm.py       # 确认/否决/supersede + 缓存失效 + 影响分析
│   └── lint.py          # 巡检项实现 (挂 cron)
├── tools/               # 6 个 Agent 工具 (注册 tool_registry)
└── api/
    ├── endpoints.py     # 管理 API (对象列表/确认 inbox/版本历史/目录)
    └── schemas.py
```

注册点：`derisk_app/initialization/serve_initialization.py` 扫描列表 + `register_serve_apps`；
表模型加入 `db_model_initialization.py` 的 `_MODELS`；MySQL 同步 `assets/schema/derisk.sql`。

### 2.1 数据表（5 张，SQLite create_all 自动建）

| 表 | 对应 ECP 文档 | 说明 |
|---|---|---|
| `ecp_semantic_object` | 3.1 semantic_object | 主键 (id, version)；type∈entity/metric/relation/dimension；status∈proposed/confirmed/rejected/deprecated；payload JSON；workspace_id 隔离 |
| `ecp_resolution_cache` | 3.1 resolution_cache | question_norm 主键；value = **工具调用参数**（v1.2 定义，不是解析 JSON）；hit_count |
| `ecp_semantic_edge` | v1.2 边表 | (src, edge_type, dst) 主键；由对象写入/版本变更时**增量重算出边**，不手工编辑 |
| `ecp_confirmer` | 3.1 confirmer | (workspace_id, user_id, scope) 确认人名单 |
| `ecp_op_log` | 3.1 op_log | append-only；未命中/兜底/确认/版本操作全记录，Lint 原料 |

**状态机与写入规则**（协议核心，在 `service.py` 单点执法）：
- LLM 写入只允许 `proposed`；`proposed→confirmed` 校验 confirmer 名单
- 修改 = 新版本 + supersedes，任何版本不可变不可删
- 查询只消费 confirmed；消费 proposed 的结果标 ⚠️
- 规则 5：无 confirmed relation 的跨实体查询 → 拒绝执行 + 自动生成 relation 提案

### 2.2 四类 payload 与扩展点设计

按 ECP 3.2 节原样实现（entity/metric/relation/dimension）。三个面向未来的扩展点
从 P0 就位，保证"新资产类型/新对象类型接入时不动协议"：

1. **binding 多态 + 执行器策略注册表**：
   `entity.binding.kind ∈ {"db", "api"}`（可扩展）
   - db: `{connector: <datasource_id>, table, pk}` — 引用现有 `connect_config`
   - api: `{api_resource: <api_resource_id>, endpoint, root_path}` — 引用 2.4 API 资产

   executor 内部为 `BindingExecutor` 接口（`assemble_query / execute / validate`），
   按 kind 注册实现。未来加 Excel 资产、外部指标平台等绑定源 = 新增一个
   executor 实现 + 一个 proposer 插件，表结构与状态机不动。

2. **提案管线插件化**：`propose.py` 中 `Proposer` 接口按资产类型注册
   （DB proposer 消费 table_spec + 采样；API proposer 消费 response_schema + 试调用；
   文档 proposer 走 evidence 提取）。新资产类型 = 新 proposer 插件。

3. **对象信封通用化**：`(id, version, type, status, payload, evidence)` 信封不假设
   只有 4 种 type。ECP 第 9 节"Intent/Decision 高频后冻结"是既定方向，届时只是
   新增 type 枚举值 + payload 校验 schema，状态机、版本、确认机制全部复用。

metric payload 预留 v1.2 追加的 `scope / owner_domain / default_for` 字段（首期可空）。

### 2.3 Resolver：工具面实现（v1.2 形态，不做单次 prompt 解析）

6 个工具，继承 `ToolBase`，模块加载时注册 `tool_registry`：

```python
# ── 读取类 ──
search_semantics(query) -> [{id, type, name, aliases, one_line}]
    # 只搜 confirmed。实现: ecp_semantic_object 表 LIKE/FTS;
    # 小目录时 Agent prompt 直接注入全目录 (见 3.1), 工具仍保留
get_semantic_object(id) -> full_payload

# ── 执行类 (协议的家) ──
execute_metric_query(metric_id, group_by, filters, time, compare)
    -> {rows, lineage, trust: "verified"}
    # executor.py 内部确定性逻辑 (Agent 不可见不可绕):
    #   ① 所有 ID 存在且 confirmed
    #   ② filter label ∈ dimension.values → 换算 codes
    #   ③ group_by ∈ metric.grain
    #   ④ 跨实体必须有 confirmed relation (规则5), 否则报错+自动提案
    #   ⑤ 冻结 expression + default/extra_filters 组装 SQL
    #   ⑥ SQL 校验: 冻结过滤条件必须在 SQL 中, 缺失→重生成(≤2次)→报错
    #   ⑦ ConnectorManager.get_connector().run() 执行 (复用只读闸门+脱敏)
    #   ⑧ 记录 lineage + op_log, 回填 resolution_cache
execute_raw_sql(sql, reasoning) -> {rows, trust: "inferred"}
    # 包装现有 db_tools.execute_sql 逻辑, 永远 ⚠️
    # 副作用: op_log 未命中记录 + 自动生成 proposed 提案 (source=fallback:{qid})

# ── 交互与回写类 ──
ask_user(question, options) -> choice
    # 复用 InteractionService / VisConfirmCard 通道; 确认后追加 alias 提案
propose_semantic(payload) -> proposal_id
    # 只进 proposed
```

**信任标记由工具返回值决定，不由 Agent 声明**——这是 v1.2 的核心纪律，
实现上就是 `trust` 字段硬编码在两个执行工具的返回构造里。

**解析缓存**：缓存 value = 成功且未被修正的 `execute_metric_query` 入参。
命中时跳过整个 Agent 循环直接重放（定时交付场景也靠它：报告模板绑定的
每个数字块 = 一组冻结工具入参）。

### 2.4 API 资产（首期做薄）

ECP 文档未展开 API 资产细节，首期目标：**API 能被注册、被提案为 entity、可执行**。

新建 `ecp_api_resource` 表 + 管理 API：

```
id / name / description / base_url / path / method /
params_schema (JSON) / response_schema (JSON, JSONPath 取数路径) /
auth_type + auth_secret_ref (复用现有密钥管理或环境变量) / status
```

- ingest：`propose_api_semantics` 读 response_schema + 一次真实采样调用 → LLM 提案 entity
  （binding.kind=api）+ dimension 候选
- 执行：`executor` 遇到 binding.kind=api 时走 HTTP 调用 + JSONPath 取数，
  首期只支持无 join 的单 API 查询（跨资产 join 明确不做）
- 前端：管理表单页（首期可以只做 API，UI 后补）

### 2.5 文档资产：双路 ingest（复用 knowledge 管线）

文档接入 = knowledge ingest 的扩展，两处改动：

1. **补 Excel extractor**：`derisk_ext/knowledge/extractors/builtin.py` 加 `ExcelExtractor`
   （openpyxl，按 sheet 抽取为 markdown 表格）——当前缺口，文档明确 Excel 是一期资产
2. **双路输出（在 ecp 侧编排，不改 IngestOrchestrator）**：文档经 ECP 入口上传到
   ECP 专用 space 后，ecp 轮询 `ingest-jobs` 确认软路（wiki 页、index.md、实体归并）
   完成，然后触发自己的 `extract_evidence`：LLM 从文档 verbat 抽取口径陈述 →
   匹配 proposed 对象 → 写入 `ecp_semantic_object.evidence`（确认界面展示引文，
   降低确认成本）。软路处理完全委托 knowledge 原有管线，硬路是 ecp 的独立后处理步骤。

### 2.6 软层：knowledge 模块的单向消费方（不改造 knowledge）

落地形态：**每个 workspace 一个 ECP 专用 knowledge space**，差异全部收敛在
`schema.md` 内容里（定制 Page Types: entities/patterns/sources；Relation Types:
ref/provenance/supersedes；写入 ECP 的 Ingest Workflow 与 Lint Rules）。
space_type 复用现有 `personal` 枚举，**不新增类型、不动 knowledge 核心**。

集成方式（全部走 knowledge 既有 Service/API，ecp 是调用方）：

- **文档入口统一在 ECP**：`POST /ecp/assets/documents` → ecp service 调用
  knowledge 的 `POST /spaces/{slug}/files` 上传 → 轮询 `ingest-jobs` 完成 →
  触发 `extract_evidence`（见 2.5）。用户感知的是一个资产入口，软层处理全委托
- **硬→软关联**：词条 frontmatter `ref: mtr.net_sales` ↔ 硬对象 id；
  ecp 解析软页 frontmatter，把 ref 边投影进 `ecp_semantic_edge`（一跳扩展用）
- **软层消费**：Agent 直接用 knowledge 现有 20 个工具（doc_search/graph_traverse/
  doc_read 等），零新建；叙述块上下文组装走 index-first（读 index.md → 选页 →
  整页读 → ref/wiki-link 一跳扩展）
- **全局图视图**：首期管理员可直接用 Obsidian 打开软层 vault 目录（文档既定方案），
  不开发全局图 UI

knowledge 侧唯一改动：**补 `ExcelExtractor`**（见 2.5）——这是 knowledge 自身
一直以来的格式缺口，ECP 只是触发补齐的契机。

### 2.7 用户交互设计（完整版）

ECP 的交互哲学是"寄生在交付动线，不做独立配置后台"（ECP 5.4），但确认人需要
一个集中处理入口。共五个交互面：

#### ① 确认收件箱（`/ecp` 主 tab，P0）

确认人的默认工作界面。数据源：`ecp_semantic_object` 中 status=proposed 的对象。

- 列表按**影响面排序**（该对象被多少解析/报告引用，首期按 source 类型 + 创建时间近似）
- 每条提案卡片展示：对象类型徽章、name/aliases、**自然语言口径解释**（LLM 把
  payload 翻译成人话）、**证据引文**（evidence 中的文档原文 quote + 来源）、
  binding 目标（哪张表/哪个 API）、置信度
- 操作：✅ 确认 / ❌ 否决 / ✏️ 改后确认（编辑 payload 后以新版本确认，
  created_by 记为用户）/ ⏸ 搁置
- 首日规则：只推送影响最大的 3-5 个口径问题，其余静默躺在收件箱
- 维度值提案是特殊卡片：值映射表（label ↔ aliases ↔ codes）逐行可编辑确认

#### ② 语义资产目录浏览（`/ecp` 第二 tab，P0 简版 → P2 完整）

- 按 type（entity/metric/relation/dimension）× status 二维过滤 + 关键词搜索
- 对象详情页（drawer）：完整 payload、绑定信息、维度值表、粒度、
  **版本历史**（supersedes 链，相邻版本 diff）、evidence 引文、
  lineage（被哪些报告块引用，P2 建边表后可用）、局部图（一跳邻域，P2）
- confirmed 对象标 ✅，proposed 标 🟡——目录页本身就是"资产固化程度"的可视化

#### ③ 对话内交互（P1-P2，复用现有组件）

| 场景 | 机制 | 复用 |
|---|---|---|
| 歧义反问（"业绩是净销售额还是毛利？"） | `ask_user` 工具 → InteractionService | `VisConfirmCard` |
| ⚠️ 结果内联确认 | 报告块上 ⚠️ 徽章可点 → 展开口径解释+证据 → 对/不对 | 新增 `VisEcpTrustCard`（P2） |
| 用户修正（"要剔税"） | 对话中直接说 → writeback 流程 → 回执"已修正，本次及以后生效" | 现有对话流 |
| 反问后别名回填 | 用户点选 → alias 追加提案进收件箱（静默，不打断） | ① |

#### ④ 版本历史与影响确认（P2）

- 修正触发的变更在确认前展示**影响分析**："此口径变更影响周报 3 处、月报 1 处"
  （`ecp_semantic_edge` 反向遍历）
- 确认人确认 → 新版本生效 + 旧版 superseded + 相关解析缓存失效 + 软层词条
  "变更叙事"追加（走 knowledge `doc_edit` 工具，不可直接改文件，防 drift 拒写）

#### ⑤ 管理面（P3）

- Lint 报告 tab（硬层巡检结果 + 软层 doc_lint 结果聚合展示）
- confirmer 名单管理（`/ecp` settings tab）
- 全局图视图：首期用 Obsidian 打开 vault 顶替，不做 UI

### 2.9 提案的触发路径与行业适配（设计澄清，v0.3）

**不是"每次资产变化全量重新提案"**。ECP 哲学是"编译一次、持续维护"，
提案有三条增量触发路径：

| 触发路径 | 时机 | 产出 |
|---|---|---|
| Ingest 全量提案 | 初次接入/新数据源接入 | 批量 proposed |
| Lint 绑定漂移 | 定期巡检：schema 重抓 vs confirmed binding | 定向更新提案 |
| 运行时未命中 | 兜底路径执行后 | 单点 proposed（source=fallback:{qid}） |

三条路径都只进 proposed，不改变任何查询行为——确认门槛兜住一切。

**初次提案：手动触发 + 就绪检查**（不自动）。资产陆续到位（DB 配置 →
schema 学习 → 文档 ingest），自动触发会在材料不全时产生低质量提案：
- `GET /ecp/readiness?datasource_id=X`：schema learning 完成？关联文档
  ingest 完成？返回就绪状态与缺项清单（P1 补，P0 前端按钮先行）
- 提案**可重入**：材料后补则再跑，已确认目录回注保证只增量、不重复
- 演进方向：新资产接入后提示确认人"材料已齐可生成提案"，但触发权始终在人

**提案管线的两种形态**：
- **批处理管线（P0 已实现，冷启动快速路径）**：`DbSemanticsProposer`，
  无人值守批量提案，输入 table spec + DISTINCT 采样 + 已确认目录回注
- **ECP 提案 Agent（P1，完整形态）**：标准 ReAct Agent + 工具集——
  读（get_table_spec / sample_distinct_values / doc_search 软层文档）+
  写（propose_semantic 唯一写入口）。多轮探索（看 spec → 发现疑点 →
  主动采样/查文档 → 再提案）；结构约束由工具 schema + service 校验执法，
  不靠 prompt。新资产类型 = 给 Agent 加读工具，不动协议

**行业场景适配**（不是按行业写生成代码）：
1. 确认门槛本身是行业适配器——改后确认，行业口径由此进入系统
2. 软层行业文档：行业口径文档 ingest 进 ECP space，提案 Agent 自行阅读
   获得领域知识（`domain_hint` 降级为批处理管线的可选覆盖项）
3. **已确认目录回注提案上下文**：增量提案基于已确认资产，口径一致、
   不重复——召回飞轮的一部分

**初次生成的逻辑单元**：以数据源为单元，输入 Layer 1 table spec +
低基数字段 SELECT DISTINCT 真实值，LLM 沿四个对象维度提炼（entity
权威表判断 / metric 可聚合 measure / relation 外键推 join / dimension
维度值字典）。

**原资产边界与引用模型**（v0.3 明确）：
ECP 不拥有任何原始资产，它是现有资源模块之上的**引用层**：

| 原资产 | 持有模块 | ECP 引用方式 |
|---|---|---|
| DB 连接（只读） | datasource/connect_config | `binding.datasource_id`（table spec 同属 datasource，实时引用，不复制） |
| 文档 | knowledge space 的 **raw 文件（L0/verbat）** | `space_slug + verbat_id`（evidence/provenance 的溯源终点） |
| API | 无持有模块 | `api_resource_id`（唯一需要新建的资产注册，见 2.4） |

知识空间对 ECP 是**双重角色**：raw 文件（L0）是原资产（不可变）；
ECP 专用 space 的 wiki 页（L1）不是原资产，是 LLM 可写的软知识层产出。

**`ecp_asset_ref` 资产引用注册表（第 6 张表，P1）**：统一登记"本 workspace
的 ECP 关注哪些原资产"——只存引用不存内容：
`id / workspace_id / kind(db|api|document|space) / ref_id / ref_meta JSON /
status / last_checked_at`。
它是三个机制的统一锚点：readiness 检查（遍历 refs 问各持有模块材料是否齐）、
Lint 漂移监控（遍历 refs 对比引用 vs 现状）、证据溯源（ref_id 解析回持有模块）。

**spec 漂移原则**：spec 更新 → ECP **不主动同步**；由 Lint 绑定漂移检查（P3）
对比 confirmed binding vs 重抓 schema，产出定向更新提案，人确认后语义资产
才跟随变化。物理层变化永远不自动改变已确认语义

**与 Agent 的结合形态**（P1，详见 §3）：ECP 是绑定到 Agent 的 capability
资源（参考 KnowledgeCapability 双轨模式）。绑定后 prepare 注入 confirmed
目录摘要（L0 热层），Agent 获得 §2.3 的 6 个工具；execute_metric_query 是
唯一 ✅ 门禁，execute_raw_sql 是永远 ⚠️ 的兜底。

### 2.10 Lint（挂 cron serve）—— 与现有 knowledge lint 的差距分析

**现状核查结论**：knowledge 的 `BaseVaultFS.doc_lint`（base.py:1037-1227）只实现了
6 项**软层结构性检查**（orphan_doc / broken_wikilink / verbat_without_wiki /
stale_edge / frontmatter_missing / contradiction 结构代理），且**无定时调度、
无 LLM 参与、结果不落库**。另发现 bug：`lint_run` 工具调用 `vault.lint()` 但
实际方法名是 `doc_lint()`，当前必然返回 NOT_IMPLEMENTED（tools/space.py:70-113），
P0 顺手修复。

对照 ECP 5.6 的落地分工：

| ECP 检查项 | 实现位置 | 说明 |
|---|---|---|
| 绑定漂移 | **ecp/lint.py 新建** | 重抓 datasource schema（ConnectorManager）对比 confirmed binding 的表/列，漂移 → 更新提案 |
| 矛盾检测 | **ecp/lint.py 新建（LLM）** | 新文档陈述 vs confirmed 口径；软层词条 vs 硬层 payload。LLM 语义级检测，现有结构代理只是补充 |
| 陈旧确认 | **ecp/lint.py 新建** | confirmed_at 超 N 月且下游修正频发 → 复审建议 |
| 孤儿对象 | **ecp/lint.py 新建** | proposed 积压超期、metric 长期未命中（op_log 统计）→ 清理建议 |
| 未命中聚类 [v1.1] | **ecp/lint.py 新建（LLM）** | op_log 中 fallback/unresolved 问题 LLM 聚类 → 高频聚类生成新对象/别名/维度值提案。**召回飞轮的核心** |
| 缓存健康 [v1.1] | **ecp/lint.py 新建** | 对象新版本生效后校验相关 resolution_cache 已失效 |
| 软层健康 | **复用并修复 knowledge doc_lint** | 现有 6 项直接用；**knowledge 模块内修复两项**：① `lint_run` 工具方法名 bug；② 补 "index 失步" 检查（index.md 目录条目 vs 实际页面集合双向比对） |

**knowledge 模块自身的 Lint 修复（P0 同期完成，属于 knowledge 的独立完善，不依赖 ECP）**：
1. 修复 `lint_run` 工具调用不存在的方法 `vault.lint()` → 改为 `vault.doc_lint()`；
2. `doc_lint` 新增 `index_drift` 检查项：wiki/index.md 中列出但磁盘/库中不存在的页面
   （幽灵条目），以及存在但未进 index 的页面（漏收条目），severity=info；
3. lint 结果追加写 `log.md`（每次巡检一行摘要），让巡检历史可追溯。

运行机制：ecp/lint.py 实现全部硬层检查项，注册为 cron serve 的 toolCall 定时任务
（默认每日）；产出三路——写 `ecp_op_log`、自动生成 proposed 提案进收件箱、
聚合报告供 `/ecp` Lint tab 展示。软层 doc_lint 结果一并聚合展示。

## 3. 与现有 Agent 链路的集成点

### 3.1 目录注入（L0 热层）

`resource_injector.py` 增加 `_format_ecp_catalog`：当 Agent 绑定了 ECP 资源时，
注入 confirmed 目录摘要（id/name/aliases/粒度，几百对象约 2-5KB）+ 行为约定：

> 回答数字问题：先 search/get 找 confirmed 指标 → execute_metric_query 执行。
> 找不到才允许 execute_raw_sql，并告知用户该结果为未验证口径。歧义用 ask_user，不要猜。

目录超阈值（默认 500 对象）后降级为只注入 scope 路由 + search_semantics 工具检索
（v1.2 分层披露的 L0/L1 切换，做成配置项，首期不会触及）。

### 3.2 DBCapability 协同

`DBCapability` 不动。ECP 作为一种新 capability 资源（`ECPCapability`，
参考 `agent/capabilities/knowledge/` 的双轨包装模式）：
prepare 时加载目录 + 绑定 workspace 的 ECP 工具集。

### 3.3 execute_sql 的处置

现有 `execute_sql` 保留给未绑 ECP 的 Agent 场景，行为不变。
绑了 ECP 的 Agent 暴露的是 `execute_raw_sql`（⚠️ 兜底版）——
工具面纪律：世界里只存在这几个工具，不依赖模型听话。

## 4. 分期落地路线（对齐 ECP 文档第 7 节，映射到代码）

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0 地基** | ecp serve 骨架 + 5 表 + `propose_semantics`（DB 路：table_spec+采样→提案，含 dimension DISTINCT 值猜测）+ 确认 inbox API + 前端 `/ecp`（①确认收件箱 + ②目录浏览简版 + 版本历史）+ **修复 knowledge `lint_run` 工具方法名 bug** | 真实脏库提案准确率 ≥80%（文档第 0 步承重测试）；提案→确认→版本历史全链路可走通 |
| **P1 查询链路** | 6 工具 + resolver 缓存 + executor 门禁（sqlglot 组装/校验/relation 规则5）+ 目录注入 + execute_raw_sql 兜底 + ⚠️/✅ 标记 + ③对话内 ask_user 反问卡片 + **ECP 提案 Agent（ReAct+工具集）+ `ecp_asset_ref` 注册表 + readiness API** | 20 个真实问题：解析正确率/错命中率；同一问题 10 遍命中路径 SQL 10/10 一致 |
| **P2 闭环** | confirm 三入口（含 ⚠️ 内联确认 VisEcpTrustCard）+ writeback（新版本/supersede/缓存失效/影响分析）+ `ecp_semantic_edge` + ask_user 别名回填 + ②目录页 lineage/局部图 | 文档验收剧本：⚠️→修正→确认→✅→换说法→反问→别名→零摩擦命中 |
| **P3 软层+多资产+Lint** | ECP space schema 定制 + 文档双路 ingest + Excel extractor + API 资产（注册/提案/单点执行）+ **ecp/lint.py 硬层 6 项检查上 cron**（含 LLM 未命中聚类、语义矛盾检测）+ ⑤管理面（Lint tab 聚合软硬层结果、confirmer 管理） | 文档证据引文出现在确认界面；API entity 可查询；Lint 日报产出提案 |

**顺序说明**：文档把 semantic_edge 提前到第 3 步（影响分析依赖），本方案 P2 建边表，一致。
API 资产放在 P3 是因为硬层协议需要先在 DB 场景跑稳，API 只是 binding 多一个 kind——
若业务上 API 更急，可将 P3 的 API 子项提到 P1 后单独插一个迭代，不影响其他项。

## 5. 明确不做（首期，继承 ECP 第 9 节并结合现状）

| 不做 | 原因 |
|---|---|
| embedding 检索基础设施 | 目录注入 + SQL LIKE 足够；knowledge 的向量检索只服务软层，已是现成能力 |
| 图数据库 | `ecp_semantic_edge` 物化边表 + 应用层遍历，万级节点绰绰有余 |
| RBAC | confirmer 名单顶替；复用现有 `get_user_from_headers` 鉴权即可 |
| 跨资产 join（DB×API、API×API） | 首期 executor 只支持单实体 + confirmed relation 的 DB join |
| 冻结整条 SQL / 字典分词解析 | 粒度定在 metric 层 + 解析缓存；语言理解全给 LLM（工具面） |
| 写操作类工具（建任务/审批业务） | 阶段 3 |
| Excel 之外的复杂文档结构抽取（表格跨页合并等） | 够用原则 |

## 6. 风险与已决事项

### 6.1 风险

1. **提案准确率是最大风险**（文档第 0 步已识别）。缓解：P0 只做提案不做查询，
   先在真实脏库上人工评估；`SchemaLearningService` 已有的 LLM 表描述是免费的高质量输入。
2. **两套"语义"的命名冲突**：knowledge 的 `semantic search`（向量检索）与 ECP 的
   semantic object 无关，代码与文案中注意区分，避免后续维护混淆。
3. **knowledge 的 drift 检测与 ECP 回写**：软层词条"变更叙事"由 ecp 的 writeback
   流程追加写入，必须通过 vault 工具（doc_edit）而非直接改文件，
   否则触发 `DocDriftError` 拒写。

### 6.2 已决事项（v0.2 定稿）

| 问题 | 决策 | 理由 |
|---|---|---|
| 模块形态 | **独立 `derisk_serve/ecp` 模块，单向依赖 knowledge/datasource/cron** | 硬层与 vault 粒度/关切不同，内建会双向污染；软层重写是浪费；单向依赖保证两模块独立演进 |
| 硬层表存储位置 | **主 meta 库**（Usage serve 模式），不放 vault 的 per-space SQLite | 确认 inbox/Lint/跨 workspace 聚合需要主库粒度 |
| 确认 inbox | **ecp 自建存储**，交互复用 `InteractionService`/`VisConfirmCard` | intervention 是任务审批，语义确认是版本治理，字段与生命周期不同 |
| SQL 组装 | **sqlglot 确定性拼接**，LLM 只做目录选择题 | 冻结 expression 已是 SQL 片段，组装是 AST 操作；无法确定性组装时才回退 LLM（仍过校验闸） |
| workspace 隔离 | `workspace_id` TEXT 列 + 索引，对齐发起对话的 app/workspace 上下文，缺省 `default` | 兼容现有 gpts app 体系，不绑死 |
| space_type | 复用 `personal`，差异全在 schema.md | 不动 knowledge 核心；若未来需 ECP 专属 ingest 钩子再评估加枚举 |
| API 资产时序 | 维持 P3，但 binding/executor/proposer 多态从 P0 就位 | 协议先支持，资产后接入，接入时不动协议 |
| 全局图视图 | 首期用 Obsidian 打开 vault 目录顶替 | 文档既定方案，避免提前建 UI |

## 7. 下一步行动（按序）

1. ~~设计评审~~ → 已定稿（v0.2）
2. P0 开工：ecp serve 骨架 + 建表 + propose_semantics（DB 路）+ BindingExecutor/Proposer 接口
3. 真实脏库承重测试，拿提案准确率数字
4. 数字达标 → P1；不达标 → 先攻 discovery 提示词与采样策略（文档既定预案）
