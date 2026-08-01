# ECP 非结构化资产扩展设计（P0 文档 / P1 小说 / P2 视频）

版本：v1.0（2026-08-01，基于 ECP v1.2 硬层已落地、双轨飞轮已运转的现状）
前置文档：ECP.md（双层知识结构总纲）、ECP-functional-design.md、ECP-implementation-design.md

---

## 0. 一句话

ECP 的协议骨架（状态机 / 契约 / 飞轮 / 降级托管 / 信任三态）是**通用资产治理协议**，结构化数据只是它的第一个 binding kind。本设计把"对象词汇表 + 检索执行器"两个插件点扩展到非结构化资产，**协议本身不动**。

---

## 1. 背景与问题定义

### 1.1 现状

企业内非结构化资产（规章制度、产品手册、合同、会议纪要、小说设定集、培训视频）目前的消费方式是 RAG：切块 → 向量索引 → 检索 → LLM 现场组织答案。这与 text2SQL 的"现场推断语义"犯了**同一组四个病**：

| 缺陷 | 结构化（已有 ECP 解法） | 非结构化（本设计解决） |
|------|------------------------|----------------------|
| 不一致 | 口径每次现场推断漂移 | 同一制度条款，不同次回答措辞/取舍不同 |
| 不可追溯 | 数字无法回答来源 | 答案无法定位到"哪份文档哪一节" |
| 不可治理 | 无确认/版本/回滚 | 文档有新旧版，答案不区分；错误答案无回写 |
| 不积累 | 修正不沉淀，同错重犯 | 被反复追问的概念不沉淀，每次重新检索 |

### 1.2 解决思路（与硬层同构）

**知识口径也是资产**：把"报销审批需要几级签字"这类问题的**权威答案单元**（条款/术语/事实陈述）从文档中提炼为带确认门槛、版本化、带锚点的硬语义对象；执行时精确命中已确认条目并带引用交付，未覆盖才回退临时检索；条目随使用自动增厚。

两条纪律原样沿用：

- **可信事实只能来自硬语义层（已确认条目+锚点），叙述可以引用软知识层（整页 markdown）**
- **凡需要理解语言的地方给 LLM，凡 LLM 输出落地的地方加代码校验**

### 1.3 与软知识层的关系（关键边界，防止重复建设）

| | 硬语义层（本设计扩展） | 软知识层（已有 WikiTab） |
|---|---|---|
| 形态 | 口径化条目：claim/terminology/policy + anchor | 整页 markdown 文档、分析模式、叙述块 |
| 粒度 | 一条可确认的陈述/定义/规则 | 一个完整主题页 |
| 确认门槛 | 重（人 confirm，契约校验） | 轻（lint 巡检） |
| 消费方式 | 事实型问题的唯一 ✅ 来源 | 报告叙述、Planner 上下文、探索轨素材 |
| 关系 | **硬层条目经 anchor 指向软层页面**，不复制全文 | 软层是硬层条目的证据来源 |

一句话：软层管"完整叙述"，硬层管"可信事实点"。硬层不是软层的摘要，是软层的**可确认锚点集合**。

---

## 2. 对象类型设计（P0 文档）

### 2.1 新增三种 obj_type

复用 `derisk_serve_ecp_semantic_object` 表（状态机/版本/op_log/契约/飞轮全部直接生效），`OBJECT_TYPES` 扩展为 `("entity", "metric", "relation", "dimension", "claim", "terminology", "policy")`。

#### claim（事实陈述）— 最小可信单元

一条可被确认"准确反映原文"的事实陈述，带出处锚点。

```json
{
  "name": "报销审批级数",
  "text": "单笔报销金额超过 5000 元须经三级审批（部门负责人→财务→分管副总）",
  "binding": {
    "kind": "doc",
    "space": "hr-policies",
    "doc_id": "expense-policy-v3",
    "anchor": "sec:4.2#p3"
  },
  "source_quote": "……报销金额超过5000元的，依次由部门负责人、财务部门、分管副总经理审批……",
  "effective_from": "2026-01-01",
  "superseded_text": null
}
```

#### terminology（术语口径）

企业黑话/缩写/同名歧义的唯一权威定义。

```json
{
  "name": "周报口径",
  "aliases": ["weekly report", "周度经营报表"],
  "definition": "指《经营分析周报（2026版）》，统计区间为自然周周一至周日，数据源为财务中台 T+1 快照",
  "binding": {"kind": "doc", "space": "ops-handbook", "doc_id": "weekly-report-spec", "anchor": "sec:1#p1"},
  "source_quote": "……"
}
```

#### policy（规则条款）

带适用条件的规则（比 claim 多条件结构）。

```json
{
  "name": "差旅住宿标准",
  "condition": "职级 <= M2 且出差城市为一线城市",
  "rule": "住宿标准不超过 500 元/晚",
  "binding": {"kind": "doc", "space": "hr-policies", "doc_id": "travel-policy-2026", "anchor": "sec:2.1#p2"},
  "source_quote": "……",
  "exceptions": ["总监及以上不受此限"]
}
```

### 2.2 binding 协议（kind=doc）

```json
{"kind": "doc", "space": "<knowledge space slug>", "doc_id": "<文档标识>", "anchor": "<定位符>"}
```

- `space`：知识空间 slug（与 asset_ref kind=space 的 ref_id 对齐）
- `doc_id`：空间内文档唯一标识（verbat_id 或文档 slug）
- `anchor`：定位符，P0 支持两级：`sec:<章节号>` / `sec:<章节号>#p<段落序>`。视频扩展时支持 `t:<开始秒>-<结束秒>`（见 §7）
- `source_quote`：确认时冻结的原文摘录——**确认的判据**（确认人比对 quote 与 text 是否一致），也是 anchor 失效后的重建线索

### 2.3 契约扩展（contracts.py，单一事实来源原则不变）

```python
_REQUIRED_EXECUTABLE 增加:
  "claim":       [("text", "claim 缺少陈述文本"),
                  ("binding", "claim 缺少 binding"),
                  ("binding.doc_id", "claim binding 缺少 doc_id"),
                  ("source_quote", "claim 缺少 source_quote(确认判据)")]
  "terminology": [("definition", "术语缺少 definition"),
                  ("binding.doc_id", "术语 binding 缺少 doc_id")]
  "policy":      [("rule", "policy 缺少 rule"),
                  ("binding.doc_id", "policy binding 缺少 doc_id"),
                  ("source_quote", "policy 缺少 source_quote")]
```

`_REQUIRED_PROPOSAL` 对应减配（提案允许 anchor 待定，confirm 前必须补齐）。`normalize_payload` 增加文档侧机械升级：`section` → `binding.anchor`、`doc`/`document` → `binding.doc_id`、`quote` → `source_quote`（对齐提案 agent 常见漂移，照 entity_bindings 先例）。

### 2.4 执行器：DocBindingExecutor

`get_executor("doc")` 注册到现有执行器注册表（与 DbBindingExecutor 平级，协议不动）。

```
DocBindingExecutor.execute_claim_query(daos, claim_ids, workspace_id):
  ① 所有 claim_id 必须 confirmed(同 metric 门禁)
  ② binding 完整性校验(契约)
  ③ 经 anchor 从软层/文档存储取回原文段落,与 source_quote 做一致性校验
     (anchor 漂移检测:原文与冻结 quote 不匹配 → GateError ANCHOR_DRIFT,
      自动提案 anchor 修正,同 relation 自动提案先例)
  ④ 返回 {answers: [{text, quote, citation}], trust: "verified",
          lineage: {claim_id@version, doc_id, anchor}}
```

**"可执行"的语义**：DB 侧是 SQL 确定性组装；文档侧是**证据确定性回放**——答案的每个事实可定位到 confirmed 条目 + 冻结 quote + 可校验锚点。信任强度低于 SQL（文本理解有弹性），远高于临时 RAG（有确认、有版本、有出处、有漂移检测）。

---

## 3. 工具面（agent 可见）

### 3.1 工具清单

| 工具 | 轨道 | 说明 |
|------|------|------|
| `search_semantics` | 共用 | 扩展到文档类对象（obj_type 过滤参数已有） |
| `get_semantic_object` | 共用 | 不变 |
| **`query_canon`** | 可信轨 ✅ | 唯一产出 ✅ 可信文本答案的路径。参数：question + claim_ids（从 search 来）。走 DocBindingExecutor，返回答案+引用+trust=verified+血缘 |
| **`explore_docs`** | 探索轨 ⚠️ | 托管空间内的自由检索（软层向量检索/全文），返回段落+文档名。⚠️ inferred 标记，op_log 记 miss（飞轮原料），reasoning 写概念发现 |
| `propose_semantic` | 共用 | 新增 claim/terminology/policy 类型（契约校验同上） |
| `get_miss_report` | 学习 | 聚类扩展到文档 miss（见 §5） |

### 3.2 降级托管（完全体/降级体模型扩展）

与 DB 门禁同构，扩展 `asset_gate`：

- ECP 绑定时，其 workspace 的 asset_ref 中 **kind=space/document 且 active** 的空间 → 直接绑定的 `knowledge_pack` 资源降级：
  - 降级注入：空间基本信息 + ECP 文档工具（search/query_canon/explore_docs）
  - **不降级移除 `knowledge_search`**？——不。照 execute_sql 先例：`knowledge_search` 对托管空间**硬门禁**（`ecp_gate_message` 扩展 kind=space 判定），返回引导文案："该空间已由 ECP 托管，事实型问题走 query_canon（✅），探索用 explore_docs（⚠️）"
- DB 直绑非托管空间 → 完全体，knowledge_search 照常用

### 3.3 双轨行为约定扩展（BEHAVIOR_GUIDE 增补）

```
【文档类问题】
事实型问题(制度/条款/定义/标准):
  可信轨: search_semantics 找 claim/terminology/policy → query_canon 带引用回答(✅)
  探索轨: 目录未覆盖时 explore_docs 自由检索(⚠️ 须声明未验证口径),
          发现可复用口径用 propose_semantic 提案(带 anchor 和原文摘录)
  锚定优先条款同 DB: 已确认条目不许绕过。
创作型任务(写报告/方案/小说章节):
  软层整页阅读不受限(knowledge_search 对非托管空间全开),
  但涉及"口径性事实"的引用必须回溯可信轨条目。
```

---

## 4. 飞轮映射（与 DB 完全同构）

```
用户问"报销审批要几级签字?"
  → search_semantics 未命中
  → explore_docs 临时检索回答 ⚠️
      └ op_log 记 miss {space, question, retrieved_docs, reasoning}【已有机制】
  → miss_report 聚类(按归一化问题模式,复用 cluster_fallbacks,
     只是 entry 形态从 SQL 换成问题+文档)
  → learn_from_misses / 每日 04:00 cron(已有机制,零改动)
      └ 提案 agent 读高频 miss + 对应文档 → claim/terminology 提案(带 anchor+quote)
  → 人 confirm(契约门禁: quote 必填,anchor 有效性巡检)
  → 下次同类问题 → query_canon ✅
  → 成功回答 backfill 解析缓存 → 重复问题直接回忆(cache_hit)
```

**零新机制**：状态机/op_log/聚类/cron/confirm 门禁/缓存回忆全部复用，只是对象类型和执行器不同。

### 4.1 文档侧特有的飞轮增强：anchor 巡检（lint 扩展）

文档会改版。`source_quote` 冻结摘录 + anchor 使漂移可检测：

- LintTab 硬层巡检（原 P3 规划，本设计提前）：定期对每个 confirmed 文档条目回放 anchor → 比对 quote
- 不一致 → 标记 `anchor_drift` 状态 + 自动提案修正（新 anchor/新 quote）
- 这是文档版的"口径漂移检测"，与 DB 的 schema 漂移检测（asset readiness）对称

---

## 5. 数据模型与 API 变更

### 5.1 表结构

**零新表**。`semantic_object` 的 payload 是 JSON，新类型只是新 obj_type 值。`asset_ref` 已有 kind=document/space。索引无需变更。

### 5.2 API

| 端点 | 变更 |
|------|------|
| `/objects` `/inbox` `/catalog` | obj_type 过滤自动支持新类型（现有参数） |
| `/admin/miss_report` | 返回增加 `kind` 字段（db/doc），聚类键按 kind 分流 |
| `/admin/learn_from_misses` | miss 上下文构建按 kind 分流（SQL 示例 vs 问题+文档） |
| 新增 `POST /objects/query_canon` | 管理面直调可信回答（测试/验收用） |

### 5.3 UI（/ecp 页）

| Tab | 变更 |
|-----|------|
| SemanticsTab | obj_type 过滤器增加 claim/terminology/policy，卡片渲染按类型展示 text/quote/anchor |
| InboxTab | 提案卡片增加 quote 与 anchor 展示（确认人比对用，confirm 的判据可视化） |
| MissTab | 聚类列表增加 kind 列（db/doc 分流展示） |
| 对象详情 vis | `d-ecp-object` 组件增加文档类字段渲染（text/quote/anchor 跳转软层页面） |

---

## 6. 提案管线（写侧）

### 6.1 文档提案 agent（复用提案助手 + 文档 prompt）

`DbSemanticsProposer` 有表结构批处理器；文档侧对应 **`DocSemanticsProposer`**：

```
输入: space slug(或 doc_id 列表) + 已确认目录 + 高频 miss(可选)
流程:
  ① 软层 index-first 导航(继承 llm-wiki 检索哲学)定位候选页面
  ② LLM 逐页提炼: claim(事实陈述)/terminology(术语)/policy(规则)
  ③ 每条必须带 anchor + source_quote(从原文摘,不许改写)
  ④ 确定性校验(代码): obj_type/契约/anchor 存在性/quote 是原文子串
     (quote ∉ 原文 → 拒收,这是文档侧最强的防幻觉闸)
  ⑤ create_proposal 落收件箱(normalize 自愈)
```

**quote ∈ 原文的代码校验是文档侧的精髓**——LLM 可以写错 text，但 quote 必须是原文真实子串，这把提案的"证据真实性"从 LLM 自觉变成代码保证。

### 6.2 双形态提案入口

- **冷启动**（schema 驱动对称物）：`POST /proposals/generate {space}` → DocSemanticsProposer 全量提炼
- **使用中**（miss 驱动）：飞轮自学（已有 cron，prompt 按 kind 分流）

---

## 7. P1 小说 / P2 视频（预览，不在本期实施）

### P1 小说/剧本（设定集管理）

- 对象：`character`/`location`/`timeline`/`event`。**entity/relation 可直接复用**（角色=实体，人物关系=relation），新增 `timeline`（时间线锚点集合）
- 执行器：`CanonBindingExecutor`——创作前注入已确认设定；创作后**设定一致性校验**（新文本 vs confirmed canon，矛盾点标出）
- 信任语义：✅ 符合设定集 / ⚠️ 即兴发挥（用户可选"宽松模式"关闭校验）
- 飞轮：写作中被反复纠正的设定错误 → miss → 设定提案

### P2 视频

- 前置摄取管道（转写/场景检测/抽帧）→ 产出 transcript（文档形态）+ scene index（结构化形态）
- 然后**退化为 P0+P1 的组合**：transcript 走文档对象，scene 走实体对象，anchor 扩展 `t:<秒>-<秒>` 时间段定位
- 摄取管道是独立工程，语义层本身零新增

---

## 8. 分期路线

| 期 | 内容 | 验收标准 |
|----|------|---------|
| **P0**（本设计主体） | claim/terminology/policy 三类型 + 契约 + DocBindingExecutor + query_canon/explore_docs 工具 + 空间降级门禁 + DocSemanticsProposer + anchor quote 子串校验 | 一份制度文档入库：事实型问题 ✅ 带引用回答；未覆盖问题 ⚠️；miss 聚类可见；学习产出提案；confirm 后转 ✅ |
| **P0.5** | anchor 漂移巡检（lint 硬层）+ UI 三处（SemanticsTab/InboxTab/MissTab kind 分流） | 文档改版后漂移条目被标记+自动提案修正 |
| **P1** | 小说设定集（character/timeline + CanonExecutor + 创作一致性校验） | 设定矛盾被检出 |
| **P2** | 视频摄取管道 + 时间段 anchor | 视频问答带时间段引用 |

### P0 实施顺序（建议）

1. contracts 扩展（新类型校验/归一化）+ OBJECT_TYPES
2. DocBindingExecutor + get_executor("doc") 注册
3. query_canon / explore_docs 工具 + BEHAVIOR_GUIDE 增补
4. asset_gate 空间降级（knowledge_search 门禁）
5. DocSemanticsProposer + quote 子串校验
6. miss 聚类 kind 分流 + UI 三处
7. 端到端验收（用真实制度文档走一遍飞轮）

---

## 9. 设计决策记录（与现状的对齐说明）

| 决策 | 理由 |
|------|------|
| 复用 semantic_object 表不建新表 | 状态机/版本/契约/飞轮/op_log 全部零成本继承；payload JSON 本就按类型分形 |
| anchor + source_quote 双锚定 | anchor 定位会随文档改版漂移，quote 是确认判据+漂移检测器+重建线索，缺一不可 |
| quote 必须是原文子串（代码校验） | 文档侧防幻觉的唯一硬闸，与 DB 侧"frozen expression"对称 |
| 硬层条目不复制全文，只存口径+锚点 | 防止与软层重复建设；软层管叙述，硬层管事实点 |
| knowledge_search 对托管空间硬门禁而非移除 | 与 execute_sql 门禁同构（完全体/降级体模型）；保留探索轨 explore_docs，不堵死泛化 |
| miss 学习 cron 零改动复用 | 飞轮机制是资产无关的，只换对象词汇表和执行器——这正是本设计的核心论点 |
