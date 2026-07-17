# 场景空间资源协议化 — 设计稿

- 日期: 2026-07-17
- 分支: `feat/scene-agent-workspace-input`
- 范围: 把场景空间的工具/资源注入从"agent 代码内造 toolkit agent 塞 extra_agents"的崩坏旁路,迁移到"独立资源装配器在对话前装配 → 标准 dynamic_resources → CapabilityPack"的资源协议正道。修复场景空间 Agent(lobby + workbench)对话崩溃。
- 关联: RFC-005 资源协议(`docs/rfc/RFC-005-resource-protocol.md`)、`PlaybookResource`(`playbook/resource/playbook_resource.py`)。

## 1. 背景与问题

### 1.1 崩溃现象
场景空间 Agent 对话发起即崩,日志(`logs/derisk_default.log`):
```
agent_chat.py:1646 _build_agent_by_gpts
  [agent_to_resource(extra) for extra in employees]
agent_chat.py:2341 agent_to_resource
  "name": f"{agent.name}({agent.agent_context.agent_app_code})"
AttributeError: 'NoneType' object has no attribute 'agent_app_code'
```
即某个注入的 agent 的 `agent_context` 为 None。

### 1.2 根因链(已查证)
1. 场景空间 Agent 走标准对话接口 `/v1/chat/completions` → `aggregation_chat`,非独立接口。`scene-workspace-agent` 是 SINGLE_AGENT 模式。
2. `ext_info.workspace_id` 存在时,`aggregation_chat:1096` 调 `_inject_workspace_context`,其中 `build_workspace_toolkit`(lobby 12 工具 / workbench 11 工具 + 剧本内置工具)造一个 `WorkspaceControlAgent`(只挂工具的壳子),塞进 `extra_agents`(241)。
3. `WorkspaceControlAgent.__init__`(`toolkit.py:43`)调 `super().__init__(profile=, llm_config=)` **没传 agent_context**,`ConversableAgent.agent_context` 默认 None(`agent.py:291`)。
4. `_build_agent_by_gpts:1645-1646` 把 `employees` 里每个 agent 经 `agent_to_resource` 转 `AgentResource` 塞 `app.all_resources`,`agent_to_resource:2341` 取 `agent.agent_context.agent_app_code` → None 崩 → 整个 chat 异常终止。
5. 即使不崩,SINGLE_AGENT + `len(employees)==1`(1674)会让 toolkit agent **顶替主 agent** `scene-workspace-agent`,主 agent 不构建、CapabilityPack 不绑定。
6. lobby 和 workbench 两种模式都走 `build_workspace_toolkit`,**两种模式都崩**。

### 1.3 设计层根因
场景空间的工具注入走的是**与资源协议并行的旧旁路**:在 agent 代码(`aggregation_chat`/`_inject_workspace_context`)内按 mode 选工具集、造 ConversableAgent、塞 extra_agents。这与 RFC-005 资源协议(资源作为 `AgentResource` 进 `dynamic_resources` → `CapabilityPack` 自动注入主 agent)的设计正道冲突,且造出的 toolkit agent 不符合主干 agent 约定(缺 `agent_context`)。

### 1.4 PlaybookResource 现状(纠错记录)
- `agent_chat.py:85` import 的 `build_workspace_context` 指向 `workspace/agent_tools/context_builder.py:77`,返回 `WorkspaceContextSnapshot` 对象(带 `playbook_resource` 属性),**非** `workspace/context_builder.py:24` 那个返回 dict 的(后者仅以 `_legacy_build_workspace_context` 在 171 行用)。
- 故 `_inject_workspace_context:209` `getattr(ctx, "playbook_resource")` 真有值,workbench 任务对话的 `PlaybookResource.declare` SYSTEM contribution 会执行进 system_prompt。**剧本资源注入是活代码,任务对话确有剧本资源**;但其工具部分仍经 `build_workspace_toolkit`(playbook 内置工具经 toolkit agent)走崩路径。

## 2. 设计原则

- **Agent 架构 = 通用骨架**:只做(1)资源协议(`CapabilityPack`/`Contribution`)→ LLM 输入转换;(2)LLM 结果 → 输出事件执行。**不含任何业务逻辑,不感知 workspace/lobby/workbench/task/playbook**。
- **场景空间业务代码在 Agent 对话前自行解决**:`SceneResourceAssembler` 是场景空间业务代码(在 `workspace/` 域,非 `agent/` 包),在请求进入 Agent 前装配好该场景该注入的资源。
- **契约 = 标准 `dynamic_resources`**:装配器产出 `List[AgentResource]`,经 `chat_completions` 端点预处理层并进 `dialogue.ext_info["dynamic_resources"]`;agent 主流程走标准 `kwargs["dynamic_resources"]` → `real_all_resources` → `build_pack` → 绑主 agent。
- **declare 纯函数零 I/O**:资源的 SYSTEM 文本是静态框架,实时数据(任务/交付数量等)由 TOOLS 槽的 `list_*`/`get_*` 工具按需查,不进 SYSTEM。实时数据走资源协议 Executor 执行投影(`data_requirement` 回填)留作后续,本期不做。

## 3. 架构

```
请求: POST /v1/chat/completions (dialogue.ext_info 含 workspace_id/task_id, dialogue.chat_in_params)
  │
  ├─ chat_completions 端点 (api_v1.py:394)
  │    └─ 预处理 (446 后, app_chat_v2/v3 前):
  │         if ext_info.get("workspace_id"):
  │             scene_res = SceneResourceAssembler.assemble(
  │                 system_app, workspace_id, task_id, conv_uid)
  │             merge scene_res → ext_info["dynamic_resources"]
  │
  └─ aggregation_chat (agent 主流程, 通用, 不出现 workspace/lobby/workbench 字样)
       └─ dynamic_resources = kwargs["dynamic_resources"]  ← 含场景资源, 标准消费
            └─ real_all_resources → build_pack(CapabilityPack) → bind 主 agent
```

与旧路径对比:旧在 `_inject_workspace_context`(agent 代码内)按 mode 造 `WorkspaceControlAgent` 塞 `extra_agents` → 崩。新把场景判断+资源生产全挪到 `SceneResourceAssembler`(agent 之外),agent 只走标准 `dynamic_resources` 消费。

## 4. 组件

### 4.1 SceneResourceAssembler(场景空间业务代码)
- **位置:** `packages/derisk-serve/src/derisk_serve/workspace/scene_resource_assembler.py`(`workspace/` 域,不进 `agent/` 包)。
- **职责:** 接 `system_app`/`workspace_id`/`task_id`/`conv_uid`,按场景产出 `List[AgentResource]`。所有 lobby/workbench 判断收敛此处。
- **逻辑:**
  ```python
  class SceneResourceAssembler:
      @staticmethod
      def assemble(system_app, workspace_id, task_id, conv_uid) -> List[AgentResource]:
          mode = "workbench" if task_id else "lobby"
          resources = []
          if mode == "lobby":
              ws = ws_service.get_by_id(workspace_id)   # 装配器查 DB
              resources.append(WorkspaceSceneResource.to_agent_resource(
                  WorkspaceSceneConfig(workspace_id, conv_uid, ws.name)))
          else:  # workbench
              task = task_service.get_by_id(task_id)
              if task and task.playbook_id:
                  resources.append(PlaybookResource.to_agent_resource(
                      PlaybookConfig(playbook_id=task.playbook_id, playbook_name=...)))
          return resources
  ```
- lobby 注入 `WorkspaceSceneResource`;workbench 注入 `PlaybookResource`(从 task 找回 playbook)。装配器只产 `List[AgentResource]`,不碰 agent、不造 ConversableAgent。

### 4.2 WorkspaceSceneResource(lobby 场景空间资源,资源协议实现)
- **位置:** `packages/derisk-serve/src/derisk_serve/workspace/scene_resource.py`(类比 `playbook/resource/playbook_resource.py`)。
- **继承:** `ResourceProtocol`,实现 `declare()`。
- **Config:** `WorkspaceSceneConfig(workspace_id: int, conv_uid: str, workspace_name: str)` —— `workspace_name` 由装配器查 DB 填入,declare 零 I/O 只用 config。
- **declare() 产出:**
  - **SYSTEM 槽(1 个 Contribution):** 静态框架文本,含 `workspace_name`(来自 config)+ 工具使用引导(任务/剧本/介入/产物交付资产分别调哪个工具)。实时数量/详情不列,靠工具查。`lifetime=SESSION, cache_scope=USER, order=0`。
    - 示例结构(措辞以实现期为准):
      ```
      # 场景空间:{workspace_name}
      你是场景空间助手。可管理任务、剧本、介入、产物/交付/资产。
      - 看任务:list_tasks(可按状态过滤);细节 get_task_info。
      - 看剧本:list_playbooks;细节 get_playbook_detail。
      - 发起任务:start_task/create_task;管理剧本:create_playbook/update_playbook/delete_playbook。
      - 介入:list_interventions 看待介入;resolve_intervention/abort_intervention 处理。
      - 产物/交付/资产:list_artifacts/list_deliveries/list_assets。
      实时数量与详情通过上述工具按需查找。
      ```
  - **TOOLS 槽(每个工具 1 个 Contribution):** 四类管理工具全集(读+写):
    - 任务:`list_tasks`/`get_task_info`/`start_task`/`create_task`/`close_task`/`archive_task`
    - 剧本:`list_playbooks`/`get_playbook_detail`/`create_playbook`/`update_playbook`/`delete_playbook`(后三个**新增**)
    - 介入:`list_interventions`/`resolve_intervention`/`abort_intervention`(补全审批动作)
    - 产物/交付/资产:`list_artifacts`/`list_deliveries`/`list_assets`
    - 工具函数体复用 `read_tools.py`/`write_tools.py` 已实现(对接 task/playbook/artifact/delivery/intervention service),补齐缺失的剧本写工具/介入审批工具。`lifetime=CONFIG_STATIC, cache_scope=NONE, order=0`。
- **to_agent_resource()**:把 `WorkspaceSceneResource` 包成 `AgentResource`(RFC-005:`ResourceBinding` 与 `AgentResource` 同构零迁移),供 `build_pack` 消费。

### 4.3 PlaybookResource 资源化(workbench 剧本资源迁移)
- `PlaybookResource.declare` 已能产 SYSTEM(剧本文本)+ TOOLS(剧本内置工具 + 子资源引用)contribution —— 本就是资源协议实现。
- 现状被 `_inject_workspace_context:204-223` 只取 SYSTEM 塞 system_prompt,TOOLS 部分靠 `build_workspace_toolkit`(playbook 内置工具经 toolkit agent)走崩路径。
- 新版:装配器把 `PlaybookResource` 包成 `AgentResource` 进 `dynamic_resources`,`build_pack` 消费其 SYSTEM **和** TOOLS contribution,剧本内置工具走资源协议 TOOLS 槽注入主 agent,不再经 toolkit agent。
- **to_agent_resource()**:`PlaybookResource` 新增静态方法,把 config 包成 `AgentResource`。

### 4.4 注入点(chAT_completions 端点预处理层)
- **位置:** `packages/derisk-app/src/derisk_app/openapi/api_v1/api_v1.py`,`chat_completions`(394)内,446 后(`dialogue.ext_info` 准备好后)、调 `multi_agents.app_chat_v2/v3`(546/565/585)前。
- **逻辑:** `ext_info.get("workspace_id")` 存在 → 调 `SceneResourceAssembler.assemble(...)` → 产出并进 `dialogue.ext_info["dynamic_resources"]`。`app_chat_v2/v3(**dialogue.ext_info)` 把 `dynamic_resources` 传进 `aggregation_chat`,agent 走标准消费路。

### 4.5 旧路径移除
- **`_inject_workspace_context`(agent_chat.py:147-243)重构**,逐段裁决:
  1. `ext_info["workspace_context"] = _legacy_build_workspace_context(...)`(171-180)+ `render_workspace_context_summary` 塞 system_prompt(195-197)+ `render_scene_dynamic_context` 塞 system_prompt(199-202):**保留**(给 agent 实时 workspace 摘要数据,不崩,无害;实时数据不走资源协议 declare 零 I/O,留待 Executor 后续)。
  2. `PlaybookResource.declare` SYSTEM 进 system_prompt(204-223):**移除**(装配器改走 `dynamic_resources`,`build_pack` 消费 PlaybookResource SYSTEM)。
  3. `build_workspace_toolkit` + `extra_agents.append`(229-241):**移除**(工具改走资源协议 TOOLS 槽)。
- **`build_workspace_toolkit`/`WorkspaceControlAgent`(`toolkit.py`):移除**(无其他调用者,grep 已证)。
- **`agent_chat.py:88` 的 `build_workspace_toolkit` import、`workspace/agent_tools/__init__.py` 导出:清。**
- **`agent_chat.py:1640-1647` extra_agents 分支:留着不动**(移除 toolkit 后 `extra_agents` 为空,分支自然不走;机制保留供将来动态子 agent)。

## 5. 数据流

1. 前端场景空间发对话 → `POST /v1/chat/completions`,`dialogue.ext_info` 含 `workspace_id`(lobby)/`workspace_id`+`task_id`(workbench)。
2. `chat_completions` 端点预处理:有 `workspace_id` → `SceneResourceAssembler.assemble` → lobby 产 `WorkspaceSceneResource` AgentResource / workbench 产 `PlaybookResource` AgentResource → 并进 `ext_info["dynamic_resources"]`。
3. `app_chat_v2/v3(**ext_info)` → `aggregation_chat`:标准 `kwargs["dynamic_resources"]` → `real_all_resources` → `build_pack` 产 `CapabilityPack`,其 Contribution 的 SYSTEM 拼进 system、TOOLS 工具挂主 agent。
4. `_build_agent_by_gpts`:SINGLE_AGENT,`len(employees)==0`(extra_agents 空)→ 走 1676 else 正道,构建主 agent `scene-workspace-agent`(1720-1753),绑 `cap_pack`。场景管理工具/剧本工具经 cap_pack 自动注入主 agent。
5. 主 agent 对话:LLM 可调 `list_tasks`/`create_playbook` 等工具。结果经标准结果→事件链路输出。

## 6. 错误处理与边界

- 装配器查 DB 失败(workspace不存在/task不存在/playbook不存在):`assemble` 返回空列表(记日志),对话不崩,只是该模式没场景资源注入。
- `build_pack` 对单个 resource 构建失败:记 warning,其余 resource 继续(现有 1737-1738 已有 try/except)。
- 无 `workspace_id`(非场景空间对话):预处理跳过,标准对话不受影响。
- `extra_agents` 移除 toolkit 后为空,SINGLE_AGENT 走 else 正道;team 模式不受影响(extra_agents 分支与 app.details 分支独立)。

## 7. 测试

- `WorkspaceSceneResource.declare`:断言产出 1 个 SYSTEM Contribution(含 workspace_name + 工具引导)+ N 个 TOOLS Contribution(四类工具齐全,含新增剧本写/介入审批工具)。纯函数,无 I/O。
- `SceneResourceAssembler.assemble`:lobby 产 `WorkspaceSceneResource` AgentResource;workbench 有 playbook_id 产 `PlaybookResource` AgentResource;workbench 无 playbook_id/workbench 不存在 → 空列表;无 workspace_id → 空列表。
- `chat_completions` 端点:有 workspace_id 时 `ext_info["dynamic_resources"]` 含场景资源;无时不改。
- 集成(人工/端到端):lobby 发对话不崩、主 agent 构建、可调场景管理工具;workbench 任务对话不崩、剧本工具可用。

## 8. 风险与取舍

- **保留旧 workspace 摘要注入(171-202)与资源协议 SYSTEM 槽并存**:两者互补(旧=实时数据,新=静态框架),不冲突。实时数据走资源协议 Executor 留后续,本期不做(加 Executor 是大改,且工具迁移已解决崩根因)。
- **`PlaybookResource.to_agent_resource` 新增**:`PlaybookResource` 现以 declare 产出 Contribution,新增"包成 AgentResource 进 dynamic_resources 让 build_pack 消费"的入口。需确认 build_pack 能从该 AgentResource 还原 PlaybookResource 的 Contribution(SYSTEM+TOOLS)——这是实现期要验证的关键点。
- **范围 Y(lobby+workbench 一起)**:比只做 lobby 大,但避免 workbench 留已知崩。剧本写工具/介入审批工具新增是工作量,但 RFC-005 资源协议本就要把场景管理工具全集化。
- **`build_workspace_toolkit` 移除影响面**:grep 已证无其他调用者,影响面仅 `_inject_workspace_context`。

## 9. 不做(YAGNI / 后续)

- 实时数据走资源协议 Executor 执行投影(`data_requirement` 回填)——本期保留旧摘要路径,后续如需统一再加 Executor。
- `extra_agents` 动态子 agent 机制保留但不新增用途。
- 全页任务表/详情卡的资源化(本次只管场景空间 Agent 对话注入)。
- SYSTEM 槽实时索引(计数+前几条)——本期 SYSTEM 只静态框架,索引靠工具;若后续要"开场即见索引"再加 Executor。
