# RFC-005 资源协议框架 —— 实现总结

> 本文档记录 RFC-005 资源协议框架的完整实现状态(2026-07-10),作为代码清理后的上下文恢复基准。
> 设计文档见 `docs/rfc/RFC-005-resource-protocol.md`。

---

## 一、已完成目标总览

| 目标 | 状态 | 关键产出 |
|---|---|---|
| 协议契约层(core/interface/resource/) | ✅ | 6 文件子包,纯数据模型+算法 |
| 编排层(core/agent/capabilities/) | ✅ | facade + registry + legacy_adapter |
| Capability 自管目录(core 层) | ✅ | sandbox/memory/mock |
| Capability 自管目录(serve 层) | ✅ | db/knowledge/app/skill/mcp/playbook |
| 工具自声明 capability_id | ✅ | ToolMetadata.capability_id + registry 索引 |
| 工具物理归入 capability tools/ | ✅ | db/knowledge/skill/playbook 各有 tools/ |
| 注解式 args_model | ✅ | ToolBase 可选 pydantic args_model 自动生成 schema |
| 执行面与声明面同源 | ✅ | react_master resolve_tool_entry 从 snapshot 查 |
| Executor.fetch 预取接口 | ✅ | declare 纯函数化 DB 等 I/O 数据 |
| 异步无阻塞(含 I/O) | ✅ | asyncio.to_thread + gather 并行 |
| system 动静态分块 + cache 适配 | ✅ | Anthropic 数组+cache_control / OpenAI 展平 str |
| Agent 默认走新协议 | ✅ | facade.assemble + snapshot.all_tools 默认路径 |
| 旧路径 shim 兼容 | ✅ | prompt_assembly/core-interface re-export |
| skill_exec 删除(冗余) | ✅ | bash 带 cwd 替代 |
| 记忆工具归属澄清 | ✅ | history_tools 非 memory 能力,不迁 |

---

## 二、代码结构

### 2.1 协议契约层:core/interface/resource/

```
core/interface/resource/
  __init__.py
  bundle.py            # Slot/Lifetime/CacheScope/Contribution/SystemBlock/
                       #   InputBundle/FrozenBundle + 排序/freeze/cache_control挂载
  tool_entry.py        # ToolEntry + BUILTIN_EXECUTOR_ID="agent:builtin"
  executor.py          # ReleaseReason/ExecutorStatus/ExecutorCall/Executor(ABC) +
                       #   ExecutorRegistry(ABC)/InMemoryExecutorRegistry +
                       #   topological_prepare + Executor.fetch(预取接口)
  dispatcher.py        # ToolDispatcher/ToolDispatchResult(按tool_name→executor_id路由)
  data_requirement.py  # DataRequirement + InjectionMode + injection_mode_for_table_count
  protocol.py          # ResourceProtocol(ABC) + ConsumerRegistry + apply_consumption
```

核心概念:
- **InputBundle**:Agent 输入载体(四槽 SYSTEM/USER_PART/TOOLS/VAR)
- **Contribution**:带 capability_id + Slot + Lifetime + CacheScope 的数据单元
- **FrozenBundle**:不可变快照(可缓存/序列化/cross-process)
- **ToolEntry**:工具声明(tool_name + tool + capability_id + executor_id)
- **ResourceProtocol**:资源协议(declare 纯函数 + requires + consume)
- **Executor**:执行投影(prepare + execute + release + fetch)

### 2.2 编排层:core/agent/capabilities/

```
core/agent/capabilities/
  __init__.py          # 导出 facade/registry/protocol
  facade.py            # ResourceFacade(产快照 + 双轨wrapper机制 + 并行declare +
                       #   并行fetch回填 + 动态扫描注册)
  registry.py          # CapabilityRegistry(自管目录自动发现)
  legacy_adapter.py    # LegacyResourceAdapter(过渡桥接,待删)
  sandbox/             # 沙箱 capability(纯 core)
    resource.py        # SandboxResource(declare env + declare_tools 归类沙箱工具)
    env.py             # env 文本构建
  memory/              # 记忆 capability(纯 core)
    resource.py        # MemoryCapabilityResource(declare 空 + consume 检索回注)
  mock/                # 扩展性验证范例
    resource.py
```

### 2.3 Serve 层 capability 自管目录

```
serve/agent/capabilities/
  db/                  # DB capability 完整自管(serve 层,连 spec_service)
    __init__.py        # register_wrappers(纯谓词 _is_db_legacy)
    resource.py        # DBCapabilityResource(declare 库基本信息 + DataRequirement 占位)
    executor.py        # DBExecutor(fetch 分级 spec,asyncio.to_thread 异步化 I/O)
    tools/
      __init__.py      # register_db_tools_capability(设 capability_id="db")
      _db_tools_impl.py # execute_sql/get_table_spec/list_tables/search_tables 实现

  knowledge/           # 知识库 capability(serve 层,Consumer)
    __init__.py        # register_wrappers(纯谓词 _is_knowledge_legacy)
    resource.py        # KnowledgeCapabilityResource(declare 库列表 + consume 检索回注)
    tools/
      __init__.py
      search.py        # KnowledgeSearchTool(注解式 args_model,capability_id="knowledge")

  app/                 # 子 Agent capability(serve 层)
    __init__.py        # register_wrappers(纯谓词 _is_app_legacy)
    resource.py        # AppCapabilityResource(declare app 描述 + agent_start)

  skill/               # 技能 capability(serve 层,连 SkillService)
    __init__.py        # register_wrappers(纯谓词 _is_skill_legacy)
    resource.py        # SkillResource(declare 技能列表 <agent-skills>)
    tools/
      __init__.py      # register_tools(Skill + skill_list)
      read_skill.py    # ReadSkillTool(capability_id="skill")
      list_skills.py   # ListSkillsTool(capability_id="skill")

  mcp/                 # MCP 工具聚合(serve 层)
    __init__.py        # register_wrappers(isinstance ToolPack)
    resource.py        # MCPCapabilityResource(declare 工具列表 TOOLS)

  playbook/            # 剧本 capability(serve 层,连 PlaybookService)
    __init__.py        # import PlaybookResource + register_wrappers
    resource.py        # PlaybookResource(declare 剧本内容 + 工具)
    tools/
      __init__.py
      playbook_tools.py # 5 个剧本内置工具(get_playbook_info 等)
```

### 2.4 旧路径 shim(向后兼容)

```
core/agent/shared/prompt_assembly/
  __init__.py          # 从新位置 re-export facade/protocol/legacy_adapter/sandbox
  input_bundle.py      # 从 core/interface/input re-export
  resource_facade.py   # 从 capabilities/facade re-export
  resource_protocol.py # 从 core/interface/resource/protocol + capabilities/legacy_adapter re-export
  sandbox_resource.py  # 从 capabilities/sandbox/resource re-export
  resource_injector.py # 旧 ResourceInjector(LegacyResourceAdapter 依赖,待全迁后删)
  prompt_assembler.py  # 旧 PromptAssembler(身份/控制层渲染仍借用)
  prompt_registry.py   # 模板注册表(被 controller + resource_injector 共用)
```

```
core/interface/
  input.py             # shim → resource/{bundle,tool_entry,data_requirement}
  executor.py          # shim → resource/{executor,dispatcher}
```

---

## 三、数据流(Agent 运行时)

### 3.1 system prompt 组装(声明面)

```
react_master_agent.load_thinking_messages()
  → PromptAssembler._assemble_identity → identity_text (GLOBAL)
  → PromptAssembler._assemble_control_flow → control_text (GLOBAL)
  → ResourceFacade.assemble(
      identity=identity_text,
      control_block=control_text,
      memory_static_block=…,
      builtin_tools=available_system_tools,
      extra_static_contribs=sandbox_env_contribs,
      extra_tools=sandbox_delegated_tools,
    )
    → _build_static_bundle:
        → 身份层 + 控制层 Contribution (GLOBAL)
        → 遍历 ResourcePack 子资源:
            → _to_resource_protocol(sub):
                → isinstance(sub, ResourceProtocol) → 直接用
                → 否则查 _legacy_wrappers 谓词命中 → 包装
            → 并行 declare (asyncio.gather)
            → 无 declare 命中 → LegacyResourceAdapter 桥接
        → _resolve_data_requirements:
            → 并行 fetch DataRequirement (asyncio.gather + asyncio.to_thread)
            → 用 fetch 结果重建 Contribution(替换占位)
    → snapshot = AgentInputsSnapshot(frozen + builtin_tools + extra_tools + memory + session + turn)
    → system_prompt = separator_join_system_blocks(snapshot.full_system_blocks())
    → self._last_snapshot = snapshot

  → _call_llm_chat:
      → context.extra["system_blocks"] = snapshot.full_system_blocks()
      → llm_client.create(context=..., messages=...)
          → claude_provider: 若 system_blocks → 数组式 + cache_control
          → openai_provider: messages[0].content str(展平)
```

### 3.2 tools 组装(声明面)

```
react_master_agent.function_calling_params()
  → snapshot.all_tools() → [Contribution(资源工具) + ToolEntry(sandbox) + ToolEntry(builtin)]
  → for entry: _tool_from_entry(entry) → _tool_to_function → functions[]
  → return {tools: functions, tool_choice: "auto"}
```

### 3.3 工具执行(执行面)

```
react_master_agent.act()
  → parse_actions(llm_out) → [ToolAction]
  → ToolAction.run():
      → resolve_tool_entry(tool_name)  # 从 _last_snapshot.all_tools 查(执行面与声明面同源)
      → 若无 snapshot: fallback 旧多源 dict (sandbox_tool_dict/system_tool_dict/resource)
      → tool.execute(args)  # 工具执行体自处理沙箱/本地/连接器切换
```

### 3.4 Capability wrapper 动态发现注册

```
react_master_agent._get_resource_facade()
  → ResourceFacade()
  → _register_capability_wrappers(facade):
      → pkgutil.iter_modules("derisk.agent.capabilities")  # core 层
      → pkgutil.iter_modules("derisk_serve.agent.capabilities")  # serve 层
      → 每个 capability 子包若有 register_wrappers(facade) → 调用
      → 不强引用任何具体 capability 类型(agent 只依赖协议)
```

---

## 四、各 Capability 工具清单

| capability | 工具 | 位置 | capability_id |
|---|---|---|---|
| sandbox | bash, read, write, edit, deliver_file, download_file | core tools/builtin/{shell,file_system,sandbox}/ | sandbox |
| db | execute_sql, get_table_spec, list_tables, search_tables | serve capabilities/db/tools/ | db |
| knowledge | knowledge_search(注解式) | serve capabilities/knowledge/tools/ | knowledge |
| skill | Skill(read_skill), skill_list | serve capabilities/skill/tools/ | skill |
| playbook | get_playbook_info/text_content/skills/resources/deliverables | serve capabilities/playbook/tools/ | playbook |
| mcp | ToolPack.sub_resources | serve capabilities/mcp/resource.py | mcp |
| app | agent_start(builtin 注入) | serve capabilities/app/resource.py | app:builtin |
| memory | (无工具,consume 型) | core capabilities/memory/ | memory |

注:skill_exec 已删除(沙箱 bash 带 cwd 替代)。

---

## 五、双轨迁移机制

### 5.1 核心原理
存量 Resource 子类(被 ResourceManager.build_resource 实例化)保持不动(build_resource 链不断)。新 capability 写 ResourceProtocol wrapper 包装旧实例,使 facade 走原生 declare 脱离 legacy 桥接。

### 5.2 谓词注册(纯 core,无 serve 依赖)
facade `_to_resource_protocol(sub)`:遇 ResourceProtocol 直接用;否则查 `_legacy_wrappers`(谓词或类)匹配 → wrapper 工厂包装。

各 capability `register_wrappers(facade)` 注册纯属性谓词(不 import 上层类):
- app: `hasattr(sub,"app_code") and hasattr(sub,"app_name")`
- db: `hasattr(sub,"_db_name") and hasattr(sub,"_connector")`
- knowledge: `hasattr(sub,"knowledge_spaces"|"retriever"|"space_slug")`
- skill: `hasattr(sub,"skill_meta") and hasattr(sub,"_skill")`
- mcp: `isinstance(sub, ToolPack)`(ToolPack 在 core)
- sandbox/memory: 直接用谓词或 core Resource 类型

### 5.3 终态
所有 ResourcePack 子资源有对应 capability wrapper → facade legacy 分支永不命中 → LegacyResourceAdapter/resource_injector **标记待删**(本轮不删,保回退兼容)。

---

## 六、分层约束

### 6.1 依赖方向(纯净)
- `core/interface/resource/`:协议契约,0 依赖 serve
- `core/agent/capabilities/`:编排层 + 纯 core capability(sandbox/memory/mock),0 依赖 serve
- `serve/agent/capabilities/`:连 serve 服务的 capability(db/knowledge/app/skill/mcp/playbook),依赖 core

### 6.2 Agent 不强引用具体类型
react_master `_register_capability_wrappers` 用 `pkgutil.iter_modules` 动态扫描两层 capabilities 包,不列名 capability 类型,只依赖 ResourceProtocol 协议接口,注册即用。

---

## 七、异步无阻塞规范

- **Executor.fetch 同步 I/O 一律 `asyncio.to_thread`**(DBExecutor 落实:get_db_stats/format_db_spec/get_table_names 全异步化)
- **facade `_resolve_data_requirements` 用 `asyncio.gather` 并行**——多 DataRequirement 并行 fetch、system/tools 槽并行 resolve
- **declare 并行**(`asyncio.gather` `_declare_one`)
- **executor acquire 并行**

---

## 八、system prompt 动静态分块 + cache 适配

### 8.1 分块(SystemBlock)
每个 SystemBlock 带 `cache_scope`(GLOBAL/USER/ENV/NONE)。排序:GLOBAL → USER → ENV → NONE(scope 优先级)。

### 8.2 Provider 适配
react_master 传 `snapshot.full_system_blocks()` 到 `context.extra["system_blocks"]`:
- **Anthropic(claude_provider)**:有 system_blocks → 数组式 `[{type:text,text,...},...]`,最后一块挂 `cache_control:{type:ephemeral}`(prompt caching)
- **OpenAI(openai_provider 等)**:用 messages[0].content 展平 str(OpenAI 自动 prompt prefix cache,不需手动 cache_control)

### 8.3 Lifetime × CacheScope
| Lifetime | CacheScope | 含义 |
|---|---|---|
| CONFIG_STATIC | GLOBAL | 跨用户共享(身份/控制层) |
| CONFIG_STATIC | USER | 跨会话同用户(DB schema/资源声明) |
| SESSION | ENV | 本会话环境(沙箱 env) |
| TURN | NONE | 仅本轮(RAG/memory consume) |

---

## 九、注解式 args_model

ToolBase 支持可选 `args_model`(pydantic BaseModel)类属性:
- 若声明,`_resolve_parameters()` 自动从 `model_json_schema()` 生成 parameters(无需手写 `_define_parameters`)
- `execute(args: dict)` 不破坏;工具内部可 `MyArgs(**args)` 转强类型(有补全/校验)
- 旧工具覆盖 `_define_parameters` 仍兼容
- KnowledgeSearchTool 是示范(`KnowledgeSearchArgs(BaseModel)` + `args_model = KnowledgeSearchArgs`)

---

## 十、测试覆盖

- **core 测试**:211 passed
  - `tests/core/interface/`:协议契约(input/executor/dispatcher/data_requirement)
  - `tests/agent/capabilities/`:编排层(extensibility/fetch/memory)
  - `tests/agent/expand/react_master_agent/`:v1 接入(s10/s19/context_engine)
  - `tests/agent/shared/prompt_assembly/`:consume/facade/executor_lifecycle
  - `tests/agent/tools/test_annotated_args.py`:注解式 args_model
- **serve 测试**:28 passed
  - `tests/derisk_serve/agent/capabilities/`:各 serve capability(db/knowledge/app/skill/mcp)
- **合计 239 passed, 0 regression**

---

## 十一、待续/清理任务(本轮不做,记录)

| 任务 | 说明 |
|---|---|
| 删 LegacyResourceAdapter + resource_injector | 全量资源迁原生 declare 后,legacy 分支永不命中时删 |
| 删旧 KnowledgeSearch(Action v1) | 6 处 v1/v2 引用(function_call_parser/unified_tool_adapter/tool_context_factory),属 v1 Action 体系退役 |
| 删 prompt_assembler | 身份/控制层渲染迁出新协议层后删(controller 的 registry 直用需改) |
| 删 prompt_assembly 旧 re-export shim | 全量切新 import 路径后删 |
| MCPExecutor 实现 | MCP 工具执行体收编(MCP server 调用),当前走 ToolPack builtin 回调 |
| SubAgentExecutor 实现 | agent_start 执行体收编(子 agent runtime),当前走 builtin 回调 |
| history_tools 归位澄清 | read_history_chapter/search_history 是对话历史压缩回顾工具,非 memory 能力,不迁 memory/ |
| v2(BAIZE)接入 | 生产全 v1,v2 接入待 build 链建立后落 |

---

## 十二、关键文件清单(实现路径)

### 协议契约(core/interface/resource/)
- `bundle.py` — InputBundle/Contribution/SystemBlock/FrozenBundle + cache 算法
- `tool_entry.py` — ToolEntry + BUILTIN_EXECUTOR_ID
- `executor.py` — Executor(prepare/execute/release/fetch)/Registry/topological_prepare
- `dispatcher.py` — ToolDispatcher(按tool_name→executor_id路由)
- `data_requirement.py` — DataRequirement + injection_mode_for_table_count
- `protocol.py` — ResourceProtocol/ConsumerRegistry/apply_consumption

### 编排层(core/agent/capabilities/)
- `facade.py` — ResourceFacade(双轨wrapper/并行declare/fetch回填/动态扫描)
- `registry.py` — CapabilityRegistry(自管目录发现)
- `legacy_adapter.py` — LegacyResourceAdapter(过渡)
- `sandbox/resource.py` — SandboxResource(env + 工具归类)
- `memory/resource.py` — MemoryCapabilityResource(consume 接口)

### Serve 层(serve/agent/capabilities/)
- `db/{resource,executor,__init__}.py` + `tools/{__init__,_db_tools_impl}.py`
- `knowledge/{resource,__init__}.py` + `tools/{__init__,search}.py`
- `app/{resource,__init__}.py`
- `skill/{resource,__init__}.py` + `tools/{__init__,read_skill,list_skills}.py`
- `mcp/{resource,__init__}.py`
- `playbook/{resource,__init__}.py` + `tools/{__init__,playbook_tools}.py`

### v1 接入(core/agent/expand/react_master_agent/)
- `react_master_agent.py` — load_thinking_messages(facade.assemble + system_blocks)
- `tool_action.py` — ToolAction.run(resolve_tool_entry 从 snapshot 查)
- `base_agent.py` — system_tool_injection(register_builtin_tools + db capability_id)

### Provider 适配(core/agent/util/llm/provider/)
- `claude_provider.py` — system_blocks → 数组式 + cache_control
- `openai_provider.py` — 展平 str(不变)