# 场景空间资产管理设计（引用/自持统一入口 + Excel 进 DB 资源管理）

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-07-31 |
| 作者 | yhjun1026 + Claude |
| 关联文档 | `SCENARIO_WORKSPACE_DESIGN.md`（原设计 5.3/6.9 资源引用模型）、`SCENARIO_WORKSPACE_PERSONAL_WORKBENCH.md`（个人工作台） |
| 关联记忆 | scene-workspace-personal-workbench / ecp-module-design-2026-07 / multi-agent-async-subagent |

---

## 0. 文档定位

场景空间在实践中已成为综合管理产品（剧本/任务/触发源/待办/交付都在空间内闭环），但**资产管理仍要求用户跳出空间去专门模块配置**（数据源去 database 模块、知识库去 knowledge-vault、MCP 去 mcp 模块），再回空间绑定。本设计解决两件事：

1. **场景空间统一管理自己的资产范围**：引用资产和自持资产都在空间内配置维护，后端复用各资源模块，不重做一套。
2. **Excel/CSV 升格为 DB 资源（datasource）**：复用 spec 学习链路（schema learning → table_spec/db_spec → 结构化提案），而不是停留在文件工具裸消费。

读完应能回答：

1. 引用资产 vs 自持资产的边界是什么、为什么这样划？
2. Excel 作为文件数据库的完整链路是什么？
3. 空间沙箱工作目录的结构与职责？
4. 全局模块如何不被空间自持资产污染？
5. 分几期落地、每期验证什么？

---

## 1. 背景与问题

### 1.1 现状链路

剧本/空间使用的资产全部来自**全局 serve 模块**，空间只有绑定记录：

- `WorkspaceResourceEntity`（`derisk_serve/workspace/models/models.py:94`）= 绑定记录，`physical_ref` 指向全局资源本体（connect_config.id / knowledge_space_id / mcp_server_id …）。
- 物化分派（`derisk_serve/workspace/materializer.py:113-122`）：`mcp`/`data_source`/`skill`/`knowledge_space`/`app` → 全局模块取本体 → `AgentResource`。
- 剧本 `declaration_dsl_json` 的 `context.resources` 引用经同一分派表物化（`playbook/resource/playbook_resource.py:346-353`）。

**痛点**：用户要配置维护任何新东西，都得离开场景空间去对应专门模块，再回来绑定。空间不是资产的"管理入口"，只是"挂载点"。

### 1.2 Excel 的现状：有消费、无治理

- `DBType` 枚举（`derisk_ext/datasource/schema.py:17-36`）**没有 excel/csv 类型**；已有 sqlite/duckdb 等 `db_path` 文件库先例。
- Excel/CSV 目前只有 ad-hoc 消费：`derisk_ext/agent/agents/open_ta/tools/xls_analysis.py` 载入**临时 DuckDB**（`_chat_excel_tmp/`）用完即弃。
- **spec 学习链路是 datasource 专属能力**，全部 keyed on `datasource_id`：
  - `SchemaLearningService`（`datasource/service/learning_service.py`）：学活库 schema + 采样 → 生成 `db_spec`/`table_spec`；
  - `FileLearningService`（`datasource/file_learning/service.py`）：解析 PDM/DDL/PDMan → 建 spec 并挂到 datasource；
  - `DbSpecService`（`datasource/service/spec_service.py`）：spec 查询/供给（下游 ECP 结构化提案、schema link 注入都消费它）。

**结论**：Excel 不成为 datasource，就永远进不了 spec 学习与结构化提案链路。这不是导入技巧问题，是归属问题。

---

## 2. 核心立场

### 2.1 一句话立场

**场景空间是资产管理的唯一入口。引用资产与自持资产只在"物理本体归属"上有区别，管理面完全统一。**

### 2.2 两类资产

| 类别 | 例子 | 物理本体 | 管理方式 |
|---|---|---|---|
| **引用资产** | MySQL/PG 等服务型数据源、MCP server、LLM Model、知识空间 | 全局 serve 模块（现状不变） | 空间内嵌表单创建/编辑 → 后端调对应模块注册 → 自动写 `workspace_resource` 绑定 |
| **自持资产** | Excel/CSV 数据集、参考对照表、SLO/on-call 等场景专属逻辑资源 | **空间沙箱目录**，记录带 `owner_workspace_id` | 空间内直接维护（上传/追加/覆盖/删除） |

引用型保持全局注册的理由不变（连接池/凭证/健康检查，每空间各持一份是灾难）——变化的是**入口搬进空间**，不是归属。

### 2.3 每空间独立沙箱工作目录

自持资产的物理归属，同时补上 SubAgent 沙箱 workspace key 缺口（见 [[multi-agent-async-subagent]] P2）：

```
data/workspaces/<ws_id>/
├── files/     上传的原始 Excel/CSV 原件
├── db/        文件数据库（一数据集一个 duckdb 文件，见 4.2）
└── runtime/   agent 运行时工作区（后续 SubAgent 沙箱复用）
```

空间归档 → 目录只读保留；空间删除 → 目录随删（先导出提醒）。

### 2.4 不做的事

- **不重做资源模块**：datasource/mcp/knowledge 各 serve 模块一行不重构，空间只是统一入口 + 自动绑定。
- **不把服务型 DB 做成自持**：需要连接凭证/池化的资源永远走引用型。
- **不做 Excel 原生查询引擎**：Excel 一律落 duckdb 文件，上层只看到 duckdb。

---

## 3. 概念模型

```
场景空间（资产管理唯一入口）
└── 资产面板（统一，用户不感知引用/自持之分）
    ├── 引用资产  ──physical_ref──> 全局 connect_config / mcp / knowledge_space …
    ├── 自持资产  ──owner_workspace_id──> 沙箱目录 data/workspaces/<ws_id>/
    └── 交付资产  artifacts / deliveries / assets（已有，不改动）

剧本 declaration 引用（引用/自持一视同仁）
  → materializer 物化（现有分派表零改动）
  → AgentResource → Agent SQL 工具 / spec 注入 / ECP 提案
```

---

## 4. Excel 作为文件数据库

### 4.1 类型设计

新增 `DBType.excel` / `DBType.csv`（`derisk_ext/datasource/schema.py`），标记为文件库（`is_file_db`），**connector 内部委托 DuckDB**。

不直接暴露 duckdb 类型的理由：管理语义不同——excel 类型的"编辑"是重新上传/追加文件，不是改 host/port；列表图标、spec 展示、删除级联（删文件）也不同。但对 `SchemaLearningService`、spec 表、agent SQL 工具而言它就是能跑 SQL 的库，**learning 链路零改造复用**。

### 4.2 一数据集一个文件（已拍板）

每个 Excel/CSV 数据集 = 独立 duckdb 文件：

```
data/workspaces/<ws_id>/db/<asset_name>.duckdb
```

- 隔离好：覆盖/重建某数据集不影响其他；duckdb 单写者竞争按文件粒度收敛。
- 跨数据集查询：duckdb `ATTACH` 支持，后续需要再做，P0 不做。
- 一份 Excel 多 sheet → 同一 duckdb 内多表（sheet=表）。

### 4.3 完整链路

```
上传 Excel/CSV（空间资产面板）
  → files/<原名>.xlsx 存原件
  → pandas 读入 → 写 db/<asset_name>.duckdb（sheet/文件 = 表）
  → connect_config 记录：
      db_type=excel|csv, db_name=<asset_name>,
      db_path=data/workspaces/<ws_id>/db/<asset_name>.duckdb,
      owner_workspace_id=<ws_id>, comment/display_name
  → 自动写 workspace_resource(type=data_source, physical_ref=connect_config.id)
  → 触发 SchemaLearningService → db_spec/table_spec → 结构化提案（ECP）
  → 剧本 declaration 按名字引用 → materializer 物化（零改动）
  → Agent SQL 工具直连查询
```

**重新上传** = 覆盖/追加表 → 触发重学 spec → spec/提案随之更新。这是"在场景空间维护资产数据"的完整闭环。

### 4.4 删除级联

删除自持数据集：删 connect_config 记录 → 删 workspace_resource 绑定 → 删 duckdb 文件与原件 → spec 记录按 datasource_id 级联清理。

---

## 5. 数据模型改动

### 5.1 `connect_config` 加列（`datasource/manages/connect_config_db.py`）

```
owner_workspace_id   Integer  nullable  index   -- 归属空间；NULL=全局资源
```

- 全局数据源列表：**显示但标记"属于 XX 空间"且只读**（已拍板），便于排查；不提供编辑/删除入口。
- 空间资产面板：按 `owner_workspace_id=ws_id`（自持）∪ `workspace_resource` 绑定（引用）过滤。

**注意**：走 `_add_missing_columns_sqlite` 自动加列时，`ConnectConfigEntity` 必须在 `_migration_db_storage`（app.py）之前完成 import（见 [[scene-workspace-personal-workbench]] 记录的 import 时机坑；当前 connect_config 是否已在早期 import 链上需落地时验证）。

### 5.2 `DBType` 枚举扩展（`derisk_ext/datasource/schema.py`）

```python
excel = "excel", "Excel", True   # is_file_db
csv   = "csv",   "CSV",   True
```

connector 层：excel/csv 类型委托 duckdb connector（`db_path` 连接），改动集中在 derisk-ext connector 工厂。

### 5.3 不改动

- `workspace_resource` 表：复用现有 type=data_source 绑定机制。
- `materializer` 分派表：excel/csv 归并到现有 `data_source` 物化分支。
- ECP / spec 各表：天然按 datasource_id 工作，无感知。

---

## 6. 前端信息架构

现有 `web/src/app/workspaces/detail/resources/` 页面升级为**统一资产面板**并进主导航：

```
资产面板（/workspaces/detail/assets 或复用 resources 路由）
├── 数据资产 tab
│    ├── 自持：Excel/CSV 数据集（上传/追加/覆盖/删除/spec 状态/预览）
│    └── 引用：服务型数据源（内嵌创建表单 → 后端注册+自动绑定）
├── 能力资产 tab：MCP / Skill / Model / 知识空间（引用型，内嵌挂载表单）
└── 交付资产 tab：artifacts / deliveries / assets（已有视图并入）
```

原则：用户**不需要知道**某个资产是引用还是自持——创建/编辑表单按类型分发到对应后端链路。

---

## 7. 分期实现计划

### P0：Excel/CSV 自持数据集闭环（后端）

- `DBType.excel/csv` + connector 委托 duckdb
- `connect_config.owner_workspace_id` 加列 + DAO/列表过滤
- 空间沙箱目录初始化（`data/workspaces/<ws_id>/{files,db,runtime}`）
- 上传 endpoint：Excel → duckdb → connect_config → workspace_resource 绑定
- 验证 `SchemaLearningService` 在 excel 类型 datasource 上跑通 → 生成 table_spec
- **验证**：pytest——上传 xlsx → 可 SQL 查询 → spec 生成 → 剧本 declaration 引用物化成功。

### P1：统一资产面板（前端）+ 引用资产内嵌创建

- resources 页升级统一资产面板（三类资产）
- 引用资产内嵌创建/编辑表单（调现有 datasource/mcp/knowledge API + 自动绑定）
- 全局 datasource 列表显示空间自持资产（只读 + 归属标记）
- **验证**：tsc + 手动——空间内完成"新建 MySQL 数据源并绑定"全程不跳模块。

### P2：自持资产维护能力

- 重新上传（覆盖/追加）+ 触发重学 spec
- 数据集预览（表结构/采样数据/spec 展示）
- 删除级联清理
- **验证**：pytest + 手动——覆盖上传后 spec 更新、旧 duckdb 文件清理。

### P3：场景专属逻辑资源 + 沙箱 runtime

- SLO/on-call 等第 ③ 类逻辑资源以 `workspace_resource(category=scenario_owned)` 承载（原设计 6.9 欠账）
- `runtime/` 目录接 SubAgent 沙箱工作区（呼应 [[multi-agent-async-subagent]] P2）
- **验证**：pytest——逻辑资源创建/引用；SubAgent 任务在空间沙箱内运行。

---

## 8. 风险与备注

- **duckdb 单写者**：agent 查询与覆盖上传并发时，按文件粒度加写锁或 copy-on-write（写临时文件再 rename）。P0 先写锁，简单可靠。
- **spec 重学时机**：覆盖上传后必须失效旧 spec 再重学，否则提案基于旧 schema。重学失败要保留旧 spec 并告警，不能清空。
- **全局列表性能**：`owner_workspace_id` 需索引；全局列表 join workspace 取名称时注意 N+1。
- **原件留存**：`files/` 原件不删（重新导入/审计依据），空间删除时才级联。
- **路径安全**：`asset_name` 入库前规范化（防路径穿越），文件名与实际 db_name 解耦。
- **存量 `xls_analysis.py` 工具**：P0 后保留兼容（会话级临时分析仍可用），但剧本/空间场景一律走自持数据集链路，后续逐步收敛。
