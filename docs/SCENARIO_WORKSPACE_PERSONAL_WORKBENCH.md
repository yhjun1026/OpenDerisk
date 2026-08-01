# 场景空间 → 个人工作台 改造设计

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-07-28 |
| 作者 | yhjun1026 + Claude |
| 关联文档 | `SCENARIO_WORKSPACE_DESIGN.md`（原设计，本设计反转其 1.1 立场）|
| 关联记忆 | scene-workspace-task-creation-unified / output-delivery-model / multi-agent-async-subagent |

---

## 0. 文档定位

本文档是把"场景空间"从**多人共享工作单元**改造为**个人工作台**的落地设计。目标读者：架构 / 后端 / 前端。读完应能回答：

1. 为什么要反转原设计的立场？
2. "共享"与"个人"的边界划在哪？
3. 待办（inbox）是什么、数据模型怎么设计、多源怎么接？
4. 前端信息架构怎么调？
5. 分几期落地、每期验证什么？

---

## 1. 与原设计的关系：立场反转

`SCENARIO_WORKSPACE_DESIGN.md` 1.1 节原立场：

> **场景空间是组织/团队的工作单元，不是个人的。** OpenDerisk 不把"个人空间"作为产品主轴。

本设计**反转该立场**：

> **场景空间就是个人工作台。** 用户进入某个场景，看到的是"我"在这个场景下的工作台——我的待办、我的工作过程；不同人进入同一场景看到各自的待办，但共享同一套剧本/资源/交付资产。

**反转理由（实践反馈）**：原设计希望"一个场景里大家共享交付结果"，落地后发现"结果共享"是对的，但**工作过程不能共享**——每个人要做的事、发起的任务、待办不同。原模型把任务/工作过程也做成了空间共享，导致"一群人各自在一个共享空间里操作，彼此不可见，也没有'我'的视角"——既不是真正的团队协作空间，也不是个人工作台，是个尴尬的中间态。

**保留原设计的部分**：剧本（怎么干）、资源、触发源作为"场景模板"继续空间共享；交付资产继续空间共享（大家能看到所有交付结果）。

---

## 2. 设计目标与核心立场

### 2.1 一句话立场

**交付资产共享 / 工作过程个人化。**

### 2.2 两条线

| 层 | 内容 | 隔离粒度 |
|---|---|---|
| **共享层（场景模板）** | 剧本 Playbook、资源、触发源 Trigger、交付资产（产出物/交付记录/发布资产）| workspace 级，所有成员相同 |
| **个人层（个人工作台）** | 任务 Task、待办 Inbox、工作对话 | user_id 级，每人独立 |

### 2.3 不做的事

- **不做 `/me` 跨场景聚合页**：场景空间本身就是终点，用户不需要一个跨场景的总入口。
- **不把剧本/资产拆成每人一份**：它们是场景级共享资产，拆了是倒退（冗余、不同步）。
- **不新建一套"待办"实体替代 BAIZE TODO**：BAIZE TODO 是 agent 执行任务时的子步骤拆解（任务内），和个人待办（收件箱）是两个层级，不冲突。

---

## 3. 核心概念模型

### 3.1 场景空间 = 个人工作台

用户进入场景空间，看到的是**自己的**个人工作台：

```
场景空间（workspace）
├── 共享背景（所有成员相同）
│   ├── 剧本 Playbook（怎么干）
│   ├── 资源/知识库
│   ├── 触发源 Trigger（何时干）
│   └── 交付资产（产出物 + 交付记录 + 发布资产）
│
└── 个人工作台（按 user_id 隔离，每人不同）
    ├── 我的待办（Inbox，多源聚合）
    ├── 我发起/指派给我的任务
    └── 我的工作对话（已有 per-user 基础：WorkspaceConversationLink.user_id）
```

### 3.2 待办（Inbox）的本质

**待办 = "需要我干预才能推进"的阻塞事件收件箱。**

关键澄清（避免重蹈"待办=任务"的覆辙）：

- 待办**不是**"我发起的任务"——自己发起的任务可能 agent 后台跑完直接交付，从不需要我干预，**不是待办**。
- 待办**不是**"指派给我的任务"——Task 有 assignee（任务归属）不等于待办（可能自动完成不用干预）。
- 待办是**事件驱动产生**的：阻塞发生时写一条，自动完成的任务一生不产生待办。

### 3.3 待办的两种可见性

| 可见性 | 来源 | 行为 |
|---|---|---|
| **个人待办** | 别人转交/指派给我（人转人）| 进一个人待办，转交后换人 |
| **共享待办** | Intervention（agent 请求介入）、ECP 提案待确认 | 进多人待办，**一人完成即全员消除** |

InboxItem 统一吸收这两种：个人待办写 1 条，共享待办写 N 条（每个相关人一条），完成事件按 `source_id` 批量标 done。

---

## 4. 数据模型

### 4.1 新增：InboxItem（统一收件箱项）

位置：`packages/derisk-serve/src/derisk_serve/workspace/inbox/`（新建子包，含 models / service / api）

```
derisk_serve_workspace_inbox_item
├── id              Integer PK
├── workspace_id    Integer  index     -- 所属场景空间
├── user_id         Integer  index     -- 收件人（谁的待办）
├── source_type     String(32)         -- task / intervention / ecp_proposal / manual
├── source_id       String(128)        -- 原实体 id（指针）
├── title           String(256)        -- 冗余展示字段
├── summary         Text  nullable     -- 摘要
├── inbox_status    String(32) index   -- unread / doing / done / archived
├── visibility      String(16)         -- personal / shared（决定完成时是否批量消除）
├── created_at      DateTime
├── resolved_at     DateTime nullable
└── gmt_create / gmt_modified
```

**设计原则**：
- InboxItem 是**索引/指针**，业务状态回指原实体（任务进度、介入审批结果、提案状态仍以原表为准）。
- InboxItem 只管收件箱视角（未读/处理中/已处理）+ 指针，**不双写业务状态**。
- 原实体状态变更通过事件同步 InboxItem（Task 完成 / Intervention 审批 / 提案确认 → InboxItem 标 done）。

### 4.2 Task 加 assignee（归属，≠ 待办）

`derisk_serve/task/models/models.py` TaskEntity 加：

```
assignee_user_id   Integer  nullable  index   -- 任务负责人（归属）
```

- 默认 = `created_by_user_id`（自己发起的自己负责）。
- 转交任务 = 改 `assignee_user_id` + 给新负责人写一条 InboxItem。
- **Task 有 assignee 不代表那人有待办**——任务可能自动跑完无阻塞。

### 4.3 Intervention 加 assignee（该谁处理）

`derisk_serve/intervention/models/models.py` InterventionEntity 加：

```
assignee_user_id   Integer  nullable  index   -- 该谁来处理这个介入
```

- 现有 `resolved_by_user_id` 是"谁实际确认的"（事后），`assignee_user_id` 是"该谁来确认"（事前，决定进谁的待办）。
- Intervention 创建时若不指定 assignee，默认走 workspace owner 或 confirmer 白名单逻辑。

### 4.4 ECP 不改，事件订阅

`derisk_serve/ecp/` 模块**一行不动**。理由：
- ECP 设计文档明确"语义确认是版本治理，不同于任务审批"——给提案加 assignee 会破坏其边界。
- ECP 的 confirmer 白名单（`ecp_confirmer` 表）已表达"谁该确认"，inbox 层只需投影成 per-user 收件箱项。

**接入方式**：ECP 提案进 `proposed` 状态时，给白名单里每个 confirmer 各写一条 `InboxItem(source=ecp_proposal, visibility=shared)`；任一 confirmer 确认后，ECP 发 confirm 事件，按 `source_id` 把所有相关 InboxItem 标 done。

**实现状态(P1)**:遇到 id 体系不匹配障碍--ECP 的 `workspace_id`/`confirmer.user_id` 是 string(`"default"` 或 user 标识),而 InboxItem 的是 int。强行 `int()` 转换脆弱(confirmer.user_id 可能是 username 非数字)。**ECP 接入暂缓为 P1.5**,需先统一 ECP 与 workspace 的 workspace_id/user_id 类型(或建映射层)。Intervention 接入已完成(同体系,int,测试通过)。

---

## 5. 待办来源与事件流

### 5.1 产生时机（事件驱动，非创建驱动）

| 来源 | 产生事件 | 写 InboxItem | 可见性 |
|---|---|---|---|
| Intervention 创建 | agent 请求人介入 | `assignee_user_id` 的人写一条 | shared（若多人可确认则多人各一条）|
| 任务转交/指派 | 人转人接手 | 新 `assignee` 写一条 | personal |
| ECP 提案 proposed | AI 提案待确认 | 每个 confirmer 各写一条 | shared |
| 手动待办 | 用户自己加"要做的事" | 自己写一条 | personal |

### 5.2 消除时机

| 来源 | 消除事件 | InboxItem 动作 |
|---|---|---|
| Intervention | 被确认/拒绝 | 标 done（shared：同 source_id 全部标 done）|
| 任务转交 | 接手并开始处理 / 完成 | 标 done |
| ECP 提案 | 被确认（任一人）| 同 source_id 全部标 done |
| 手动待办 | 用户标记完成 | 标 done |

### 5.3 事件接入点

复用现有 `workspace/event_bus.py` 的 `emit_workspace_event`，新增事件类型 `inbox_created` / `inbox_resolved`。各来源在产生/消除点 emit，inbox service 订阅写 InboxItem。同步加 `agent_chat.py` 的 `WORKSPACE_EVENT_TYPES` 白名单 + 前端 `use-chat.ts` 白名单（见 [[scene-workspace-event-bus]] 的四处同步要求）。

---

## 6. 前端信息架构

### 6.1 主界面（三列布局保持）

进入场景空间 = 个人工作台主页，三列布局不变：

```
┌─────────────┬──────────────────────────┬──────────────┐
│ 左栏 rail   │ 中列 space               │ 右列 agent   │
│             │                          │              │
│ [待办][资产]│  打开待办: 任务详情/工作过程│  Agent 对话   │
│  tab        │  打开资产: 资产预览       │  驱动待办     │
│             │  空: 我的工作台概览       │  发起新任务   │
│ 待办列表     │                          │              │
│ (我的)      │                          │              │
│ 资产列表     │                          │              │
│ (共享)      │                          │              │
└─────────────┴──────────────────────────┴──────────────┘
```

**左栏双 tab**（替换现有 scene-task-rail 的"全部/运行中/待介入/已完成/失败"状态 tab）：
- **待办 tab**：`InboxItem where user_id=me`，按 inbox_status 分组（未读/处理中）。
- **资产 tab**：workspace 级共享交付资产（合并视图，见 6.2）。

### 6.2 资产 tab 范围（分叉点决策）

合并视图：产出物（artifacts）+ 交付记录（deliveries）+ 发布资产（assets）统一成"共享资产"列表，带类型筛选。理由：用户立场是"大家能看到所有交付资产"，一个入口最直接；三种东西分三个 tab 反而割裂。

### 6.3 二级页面：任务

"任务"从主界面左栏移出，作为独立二级页面（`/workspaces/detail/tasks`，已有路由）：
- 内容：**我的任务**（`created_by=me` 或 `assignee=me`），不再是空间内所有人任务的全集。
- 保留现有双 tab（执行记录 / 触发规则），但执行记录默认过滤为"我的"。
- 管理性内容（剧本、触发规则）仍在此入口可达。

### 6.4 对话框入口

右列 Agent 对话框是万能入口：
- **驱动待办**：打开待办后，对话框聚焦该任务（workbench 模式），可让 agent 做。
- **从零发起新任务**：无待办时在对话框发起 adhoc 任务，`assignee` 默认 = 当前用户（我发起的我负责，但不一定产生待办——只有阻塞时才产生）。
- 契合现有 `lobby`（无 task_id）/ `workbench`（有 task_id）模式，后端已支持。

### 6.5 "自己做"形态（分叉点决策）

打开待办不委派 agent 时，给待办加**手动状态推进**动作（接手 / 标记完成 / 关闭），不强制走 agent runtime。理由：待办是"需要我干预"的事项，用户可能自己处理完直接标记完成，不必拉起 agent。

---

## 7. 协作原语

### 7.1 任务转交

- 动作：改 `Task.assignee_user_id` → 给新负责人写 InboxItem（personal）→ 原 assignee 的待办标 done。
- UI：任务详情页"转交"按钮，选空间成员。

### 7.2 交付转发

- 把一条共享交付资产转发给空间内某人，对方待办出现一条（source=task 或独立 source=delivery_share）。
- 最小实现可先不做，P3 视情况。

### 7.3 @mention

- 在任务备注/对话里 @user，触发通知（写一条 InboxItem source=mention）。
- 最小实现可先不做，P3 视情况。

---

## 8. 分叉点决策（已拍板）

| 分叉点 | 决策 | 理由 |
|---|---|---|
| 触发源归属 | **共享（属场景模板）+ 指派策略字段** | 触发源是"何时干"的方法论，应共享。fire 出的 Task 按指派策略设 assignee（默认 owner，可配特定人/广播）。TriggerSource 加 `assignee_strategy` 字段。 |
| 资产 tab 范围 | **合并视图**（artifacts + deliveries + assets，类型筛选）| 用户要"看到所有交付资产"，一个入口最直接。 |
| "自己做"形态 | **手动状态推进**（接手/完成/关闭，不强制 agent）| 待办是"需要我干预"，用户可自己处理完标记。 |

---

## 9. 分期实现计划

### P0：数据模型 + 待办最小闭环（后端）

- 新建 `workspace/inbox/` 子包：InboxItem Entity + DAO + Service（create/resolve/list_by_user）
- Task 加 `assignee_user_id` + alembic migration
- Intervention 加 `assignee_user_id` + migration
- 任务转交 endpoint + service：改 assignee → 写 InboxItem
- 待办列表 endpoint：`GET /workspaces/{ws_id}/inbox?user_id=me`
- 事件：`inbox_created` / `inbox_resolved` 接入 event_bus + 白名单
- **验证**：后端 pytest——转交任务后 assignee 待办出现一条；自动完成任务不产生待办；Intervention 创建产生待办。

### P1：Intervention / ECP 接入待办

- Intervention 创建时写 InboxItem（shared，按 confirmer/assignee）
- Intervention 确认/拒绝时 resolve InboxItem（同 source_id 批量）
- ECP propose 时给 confirmer 白名单写 InboxItem（不改 ECP，在 inbox 层订阅 ECP 事件或轮询）
- ECP confirm 时 resolve InboxItem
- **验证**：pytest——Intervention 创建/确认 → 待办出现/消除；ECP 提案 proposed/confirmed → 待办出现/消除。

### P2：前端左栏双 tab + 待办/资产视图

- `scene-task-rail.tsx` 改造：双 tab（待办 / 资产）
- 待办 tab：拉 `/inbox?user_id=me`，按状态分组渲染
- 资产 tab：合并 artifacts + deliveries + assets，类型筛选
- 任务卡片显示 assignee 头像
- lobby 个人化：进行中任务 → 我的待办概览
- **验证**：tsc + 手动——转交任务后对方待办 tab 出现；资产 tab 显示共享资产。

### P3：二级任务页个人化 + 协作原语

- `/workspaces/detail/tasks` 默认"我的任务"过滤
- 任务详情页"转交"按钮 + 选人
- 待办"自己做"手动状态推进（接手/完成/关闭）
- （视情况）@mention / 交付转发
- **验证**：tsc + 手动——转交 UI 闭环；手动完成待办。

### P4：端到端测试验证

- 场景 1：A 发起任务自动完成 → A 无待办，资产 tab 出现交付物
- 场景 2：A 转交任务给 B → B 待办出现，A 待办消除
- 场景 3：agent 任务触发 Intervention → assignee 待办出现 → 确认后消除
- 场景 4：ECP 提案 proposed → confirmer 待办出现 → 确认后全员消除
- 场景 5：A 在对话框发起新任务 → assignee=A，无阻塞则无待办
- **验证**：全部场景通过；后端 pytest 全过；前端 tsc/build 无新增错误。

---

## 10. 测试策略

- **后端**：每期 pytest，重点测 InboxItem 产生/消除的事件驱动逻辑、多源聚合、shared/personal 可见性。
- **前端**：每期 tsc + build，无新增类型错误；关键路径手动验证。
- **端到端**：P4 按场景 1-5 全量验证。
- **回归**：现有 scene-workspace 测试不回归（test_agent_tools 有 10 个存量失败、test_builtin_playbooks 3 个存量失败，属预存，不在此改造范围）。

---

## 11. 风险与备注

- **DB 迁移**：Task / Intervention 加列，走 alembic。注意 [[alembic-precheck-blocks-startup]] 的预检陷阱——半应用迁移别重跑 upgrade，手动盖版本。
- **InboxItem 与原实体状态同步**：必须事件驱动，不能轮询为主。漏掉 resolve 事件会导致待办僵尸（已处理但不消失）。P1 接入 Intervention/ECP 时重点测。
- **ECP 接入不改 ECP**：在 inbox 层订阅 ECP service 的事件或在 ECP propose/confirm endpoint 后调 inbox service。不引入 ECP → inbox 的反向依赖（ECP 不感知 inbox）。
- **共享待办的一致性**：shared InboxItem 多人各一条，必须按 source_id 批量 resolve，否则会出现"A 确认了 B 的待办还显示"。
- **BAIZE TODO 不动**：那是任务内 agent 子步骤，和个人待办（收件箱）是两个层级，不要合并。
