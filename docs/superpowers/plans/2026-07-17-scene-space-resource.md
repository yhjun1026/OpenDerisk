# 场景空间资源协议化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把场景空间的工具/资源注入从"agent 代码内造 toolkit agent 塞 extra_agents"的崩坏旁路,迁移到"独立资源装配器在对话前装配 → 标准 dynamic_resources → CapabilityPack"的资源协议正道,修复场景空间 Agent(lobby+workbench)对话崩溃。

**Architecture:** 新增 `WorkspaceSceneResource`(ResourceProtocol,lobby 静态框架 SYSTEM + 四类管理工具 TOOLS)和 `SceneResourceAssembler`(场景业务,按 lobby/workbench 装配资源)。`chat_completions` 端点预处理层调装配器把资源并进 `ext_info["dynamic_resources"]`;agent 主流程走标准 `build_pack` 消费。为 `workspace_scene`/`playbook` 注册 capability factory 让 `build_pack` 能从 AgentResource 还原 Capability。移除 `build_workspace_toolkit`/`_inject_workspace_context` 的 toolkit 注入段。

**Tech Stack:** Python 3 / asyncio / SQLAlchemy(derisk-serve),RFC-005 资源协议(ResourceProtocol/Contribution/CapabilityPack),pytest。

## Global Constraints

- **Agent 架构通用**:agent 代码(`aggregation_chat`/`_build_agent_by_gpts`)不感知 workspace/lobby/workbench/task/playbook;业务在装配器(对话前),契约是标准 `dynamic_resources`。
- **declare 纯函数零 I/O**:资源 SYSTEM 文本是静态框架,实时数据靠 TOOLS `list_*`/`get_*` 工具查;`workspace_name`/playbook 数据由装配器查 DB 填入 config,declare 只用 config。
- **capability_id/capability type_key 固定**:`WorkspaceSceneResource.capability_id="workspace_scene"`、factory type_key `"workspace_scene"`;`PlaybookResource.capability_id="playbook"`、factory type_key `"playbook"`。
- **不移除旧 workspace 摘要注入**:`_inject_workspace_context` 的 171-202(workspace_context 摘要 + scene_dynamic 进 system_prompt)保留(不崩,给 agent 实时数据);只移除 204-241(PlaybookResource 旧 system 注入 + toolkit agent 注入)。
- **不动 `agent_chat.py:1640-1647` extra_agents 分支**:移除 toolkit 后 `extra_agents` 为空,分支自然不走,机制保留。
- **工具函数体复用** `read_tools.py`/`write_tools.py` 已实现的工具,补齐缺失的剧本写/介入审批工具。
- **状态枚举固定**(应用层 `VALID_TRANSITIONS`):`draft/pending_trigger/running/awaiting_human/blocked/delivered/closed/archived/failed`。
- 提交信息末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。

## File Structure

**新建:**
- `packages/derisk-serve/src/derisk_serve/workspace/scene_resource.py` — `WorkspaceSceneResource`(ResourceProtocol)+ `WorkspaceSceneConfig`;`build_scene_management_tools`(四类管理工具全集,复用 read/write tools + 补齐)。
- `packages/derisk-serve/src/derisk_serve/workspace/scene_resource_assembler.py` — `SceneResourceAssembler.assemble(scene_resource_assembler.py)` lobby/workbench 装配产出 `List[AgentResource]`。
- `packages/derisk-serve/src/derisk_serve/workspace/scene_capability.py` — `workspace_scene` capability factory(注册到 `CapabilityFactoryRegistry`),从 AgentResource.value 还原 `WorkspaceSceneResource` Capability。
- `packages/derisk-serve/src/derisk_serve/playbook/resource/playbook_capability.py` — `playbook` capability factory,从 AgentResource.value 还原 PlaybookResource Capability。
- 测试: `tests/derisk_serve/workspace/test_scene_resource.py`、`test_scene_resource_assembler.py`、`test_scene_capability.py`;`tests/derisk_serve/playbook/resource/test_playbook_capability.py`。

**修改:**
- `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` — `_inject_workspace_context` 移除 204-241;删 `build_workspace_toolkit` import(88);保留 171-202。
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py` — 删 `build_workspace_toolkit`/`WorkspaceControlAgent`(无其他调用者)。保留 LAYER 常量(若 read_tools 用到)。
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/__init__.py` — 删 `build_workspace_toolkit` 导出。
- `packages/derisk-app/src/derisk_app/openapi/api_v1/api_v1.py` — `chat_completions` 端点预处理层调装配器。
- `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py` — 补齐 `create_playbook`/`update_playbook`/`delete_playbook`/`resolve_intervention`/`abort_intervention` 工具(供 scene_resource 复用)。
- `packages/derisk-core/src/derisk/agent/capabilities/registry.py` 或对应 `__init__.py` — 注册 `workspace_scene`/`playbook` factory(按现有 discover 机制)。
- `packages/derisk-serve/src/derisk_serve/playbook/service/service.py` — 确认 `create_playbook`/`update_playbook`/`delete_playbook` service 方法存在(写工具依赖);缺则补。

---

### Task 1: 补齐场景管理写工具(剧本写 + 介入审批)

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_write_tools.py` (Create if absent)

**Interfaces:**
- Consumes: `playbook_service.create/update/delete`(待确认签名);`intervention_service.resolve_and_execute/abort`(intervention/service/service.py 已有 `resolveAndExecuteIntervention` 等价方法);`get_intervention_service`/`get_playbook_service`(read_tools.py 已有)。
- Produces: `build_scene_write_tools(system_app, workspace_id, user_id, conv_uid, task_id=None, on_event=None) -> List[FunctionTool]`,含 `start_task`/`close_task`/`create_playbook`/`update_playbook`/`delete_playbook`/`resolve_intervention`/`abort_intervention`/`publish_asset`/`create_delivery`/`update_workspace`。

- [ ] **Step 1: 确认依赖 service 方法签名**

Run:
```bash
cd /Users/tuyang/GitHub/OpenDerisk
grep -nE "def create\b|def update\b|def delete\b|def resolve_and_execute|def abort" \
  packages/derisk-serve/src/derisk_serve/playbook/service/service.py \
  packages/derisk-serve/src/derisk_serve/intervention/service/service.py
```
记录每个方法签名。若 playbook service 缺 `create/update/delete`,Task 1 先补这三个 service 方法(参照现有 `PlaybookService` 风格);若 intervention service 的审批方法名不一致,记录真实名。

- [ ] **Step 2: 写失败测试**

创建测试(若文件不存在则建,补 `__init__.py`):

```python
"""场景管理写工具测试:剧本写 + 介入审批工具新增。"""
from unittest.mock import MagicMock, patch


def test_build_scene_write_tools_includes_playbook_and_intervention_tools():
    """build_scene_write_tools 产出含 create_playbook/update_playbook/delete_playbook/
    resolve_intervention/abort_intervention + 原有 start_task/close_task 等。"""
    from derisk_serve.workspace.agent_tools.write_tools import build_scene_write_tools
    tools = build_scene_write_tools(
        system_app=MagicMock(), workspace_id=1, user_id="u1",
        conv_uid="c1", task_id=None,
    )
    names = {t.name for t in tools}
    for must in ("start_task", "close_task", "create_playbook", "update_playbook",
                 "delete_playbook", "resolve_intervention", "abort_intervention",
                 "publish_asset", "create_delivery", "update_workspace"):
        assert must in names, f"missing tool {must}; got {names}"


def test_create_playbook_tool_calls_playbook_service_create():
    """create_playbook 工具调 playbook_service.create。"""
    from derisk_serve.workspace.agent_tools.write_tools import build_scene_write_tools
    with patch(
        "derisk_serve.workspace.agent_tools.write_tools.get_playbook_service"
    ) as mks:
        svc = MagicMock(); mks.return_value = svc; svc.create.return_value = MagicMock(id=9)
        tools = {t.name: t for t in build_scene_write_tools(
            MagicMock(), 1, "u1", "c1")}
        res = tools["create_playbook"].func(name="p", declaration_dsl="{}",
                                             workspace_id=1)
        svc.create.assert_called_once()
        assert res["playbook_id"] == 9
```

- [ ] **Step 3: 运行确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_write_tools.py -v`
Expected: FAIL — `build_scene_write_tools` 未定义。

- [ ] **Step 4: 实现 `build_scene_write_tools`**

在 `write_tools.py` 末尾追加。复用现有 `build_write_tools` 的 5 个工具 + 新增 5 个:

```python
def build_scene_write_tools(
    system_app, workspace_id: int, user_id: Optional[str],
    conv_uid: str, task_id: Optional[int] = None,
    on_event: Optional[WorkspaceEventCallback] = None,
) -> List[FunctionTool]:
    """场景管理写工具全集:任务/剧本/介入/产物交付/workspace,供 WorkspaceSceneResource TOOLS 槽。"""
    from derisk_serve.workspace.agent_tools.read_tools import get_playbook_service
    base = build_write_tools(system_app, workspace_id, user_id, conv_uid, task_id, on_event)

    def create_playbook(**kwargs):
        svc = get_playbook_service(system_app)
        from derisk_serve.playbook.api.schemas import PlaybookRequest
        req = PlaybookRequest(workspace_id=workspace_id, name=kwargs.get("name"),
                              declaration=kwargs.get("declaration_dsl") or "{}")
        entity = svc.create(req)
        return {"playbook_id": entity.id}

    def update_playbook(**kwargs):
        svc = get_playbook_service(system_app)
        from derisk_serve.playbook.api.schemas import PlaybookRequest
        req = PlaybookRequest(workspace_id=workspace_id, name=kwargs.get("name"),
                              declaration=kwargs.get("declaration_dsl") or "{}")
        entity = svc.update(int(kwargs.get("playbook_id")), req)
        return {"playbook_id": entity.id}

    def delete_playbook(**kwargs):
        svc = get_playbook_service(system_app)
        svc.delete(int(kwargs.get("playbook_id")))
        return {"playbook_id": int(kwargs.get("playbook_id")), "deleted": True}

    def resolve_intervention(**kwargs):
        svc = get_intervention_service(system_app)
        entity = svc.resolve_and_execute(
            int(kwargs.get("intervention_id")),
            decision=kwargs.get("decision") or {"action": "approved"},
        )
        return {"intervention_id": entity.id, "status": getattr(entity, "status", "resolved")}

    def abort_intervention(**kwargs):
        svc = get_intervention_service(system_app)
        entity = svc.abort(int(kwargs.get("intervention_id")))
        return {"intervention_id": entity.id, "status": getattr(entity, "status", "aborted")}

    extra_specs = [
        ("create_playbook", "在当前空间下创建一个剧本", create_playbook),
        ("update_playbook", "更新指定剧本的声明", update_playbook),
        ("delete_playbook", "删除指定剧本", delete_playbook),
        ("resolve_intervention", "批准并执行一个待介入请求", resolve_intervention),
        ("abort_intervention", "中止一个介入请求", abort_intervention),
    ]
    for name, desc, fn in extra_specs:
        base.append(FunctionTool(name=name, description=desc, func=fn, args_schema=None))
    return base
```

> 注:`PlaybookRequest`/`svc.create/update/delete`/`svc.resolve_and_execute/abort` 的确切签名以 Step 1 记录为准;若签名不符,按 Step 1 记录调整调用。若 service 方法缺失,先在 `playbook/service/service.py`/`intervention/service/service.py` 补齐(参照同文件已有方法风格)。

- [ ] **Step 5: 运行确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_write_tools.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/agent_tools/write_tools.py \
  packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/test_write_tools.py
git commit -m "feat(scene): scene write tools — playbook write + intervention approval

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: WorkspaceSceneResource(资源协议实现)

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/scene_resource.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource.py`

**Interfaces:**
- Consumes: Task 1 的 `build_scene_write_tools`;`build_read_tools`(read_tools.py);`ResourceProtocol/Contribution/Slot/Lifetime/CacheScope`(`derisk.core.interface.resource.{protocol,bundle}`);`FunctionTool`(`derisk.agent.resource.tool.base`)。
- Produces: `WorkspaceSceneConfig(workspace_id:int, conv_uid:str, workspace_name:str)`;`WorkspaceSceneResource(ResourceProtocol)` 含 `declare(cls, config)->List[Contribution]`、`capability_id="workspace_scene"`;`build_scene_management_tools(workspace_id, conv_uid)->List[FunctionTool]`(读全集 + 写全集)。

- [ ] **Step 1: 写失败测试**

创建 `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource.py`(若 `workspace/` 测试目录无 `__init__.py` 则建):

```python
"""WorkspaceSceneResource 资源协议实现测试。"""
from unittest.mock import MagicMock, patch


def test_declare_produces_system_and_tools_contributions():
    from derisk_serve.workspace.scene_resource import (
        WorkspaceSceneConfig, WorkspaceSceneResource,
    )
    config = WorkspaceSceneConfig(workspace_id=1, conv_uid="c1", workspace_name="营收空间")
    with patch("derisk_serve.workspace.scene_resource.build_scene_management_tools") as mtools:
        mtools.return_value = [MagicMock(name="list_tasks"), MagicMock(name="start_task")]
        contribs = WorkspaceSceneResource.declare(config)
    slots = [c.slot for c in contribs]
    assert any(str(s) == "Slot.SYSTEM" or s.name == "SYSTEM" for s in slots)
    assert sum(1 for c in contribs if not (str(c.slot) == "Slot.SYSTEM" or getattr(c.slot,'name',None)=="SYSTEM")) == 2
    sys_contrib = next(c for c in contribs if str(c.slot) == "Slot.SYSTEM" or getattr(c.slot,'name',None)=="SYSTEM")
    assert "营收空间" in sys_contrib.content
    assert "list_tasks" in sys_contrib.content  # 工具引导文本含工具名


def test_declare_is_pure_no_io():
    """declare 不查 DB:不传 workspace_name 的真实查询,只用 config。"""
    from derisk_serve.workspace.scene_resource import (
        WorkspaceSceneConfig, WorkspaceSceneResource,
    )
    config = WorkspaceSceneConfig(workspace_id=1, conv_uid="c1", workspace_name="x")
    with patch("derisk_serve.workspace.scene_resource.build_scene_management_tools") as mtools:
        mtools.return_value = []
        WorkspaceSceneResource.declare(config)
    mtools.assert_called_once_with(1, "c1")


def test_build_scene_management_tools_full_set():
    from derisk_serve.workspace.scene_resource import build_scene_management_tools
    tools = build_scene_management_tools(1, "c1")
    names = {t.name for t in tools}
    for must in ("list_tasks", "get_task_info", "list_artifacts", "list_deliveries",
                 "list_assets", "list_playbooks", "get_playbook_detail", "list_interventions",
                 "start_task", "close_task", "create_playbook", "update_playbook",
                 "delete_playbook", "resolve_intervention", "abort_intervention",
                 "publish_asset", "create_delivery", "update_workspace"):
        assert must in names, f"missing {must}"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource.py -v`
Expected: FAIL — 模块不存在。

- [ ] **Step 3: 实现 `scene_resource.py`**

```python
"""WorkspaceSceneResource — RFC-005 资源协议实现(场景空间 lobby 资源)。

包含:
- SYSTEM 槽:静态框架(workspace_name + 四类管理工具使用引导),零 I/O
- TOOLS 槽:任务/剧本/介入/产物交付资产 管理工具全集(读+写)

设计:declare 纯函数;workspace_name 由装配器查 DB 填入 config;实时数据靠工具查。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

from derisk.agent.resource.tool.base import FunctionTool
from derisk.core.interface.resource.bundle import (
    CacheScope, Contribution, Lifetime, Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

from derisk_serve.workspace.agent_tools.read_tools import build_read_tools
from derisk_serve.workspace.agent_tools.write_tools import build_scene_write_tools


@dataclass
class WorkspaceSceneConfig:
    workspace_id: int
    conv_uid: str
    workspace_name: str


def build_scene_management_tools(workspace_id: int, conv_uid: str) -> List[FunctionTool]:
    """四类管理工具全集:读(build_read_tools,10)+ 写(build_scene_write_tools,10)。"""
    from derisk.component import CFG
    reads = build_read_tools(CFG.SYSTEM_APP, workspace_id)
    writes = build_scene_write_tools(
        CFG.SYSTEM_APP, workspace_id, user_id=None, conv_uid=conv_uid, task_id=None,
    )
    return reads + writes


class WorkspaceSceneResource(ResourceProtocol):
    capability_id: str = "workspace_scene"

    @classmethod
    def declare(cls, config: WorkspaceSceneConfig) -> List[Contribution]:
        contributions: List[Contribution] = []
        contributions.append(Contribution(
            capability_id="workspace_scene:system",
            slot=Slot.SYSTEM,
            content=cls._render_system_framework(config),
            lifetime=Lifetime.SESSION, cache_scope=CacheScope.USER, order=0,
        ))
        for tool in build_scene_management_tools(config.workspace_id, config.conv_uid):
            contributions.append(Contribution(
                capability_id=f"workspace_scene:tool:{tool.name}",
                slot=Slot.TOOLS, content=tool,
                lifetime=Lifetime.CONFIG_STATIC, cache_scope=CacheScope.NONE, order=0,
            ))
        return contributions

    @staticmethod
    def _render_system_framework(config: WorkspaceSceneConfig) -> str:
        return (
            f"# 场景空间:{config.workspace_name}\n"
            "你是场景空间助手。可管理任务、剧本、介入、产物/交付/资产。\n"
            "- 看任务:list_tasks(可按状态过滤);细节 get_task_info。发起:start_task/create_task;关闭:close_task。\n"
            "- 看剧本:list_playbooks;细节 get_playbook_detail。管理:create_playbook/update_playbook/delete_playbook。\n"
            "- 介入:list_interventions 看待介入;处理:resolve_intervention/abort_intervention。\n"
            "- 产物/交付/资产:list_artifacts/list_deliveries/list_assets。\n"
            "实时数量与详情通过上述工具按需查找,不在此列出。\n"
        )
```

> 注:`Slot.SYSTEM` 的枚举访问方式(Slot.SYSTEM vs Slot["SYSTEM"])以 `derisk.core.interface.resource.bundle` 实际定义为准;若 Slot 是 Enum,用 `Slot.SYSTEM`;若 str-like,直接字符串。实现时按 PlaybookResource 里的用法对齐(playbook_resource.py:253 用 `slot=Slot.SYSTEM`,照抄)。

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/scene_resource.py \
  packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource.py
git commit -m "feat(scene): WorkspaceSceneResource — SYSTEM framework + TOOLS mgmt set

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: workspace_scene capability factory(注册到 build_pack)

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/scene_capability.py`
- Modify: `packages/derisk-core/src/derisk/agent/capabilities/registry.py`(或 `__init__.py`,按 discover 机制注册)— 让 `workspace_scene` type_key 的 factory 被发现
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_capability.py`

**Interfaces:**
- Consumes: Task 2 的 `WorkspaceSceneConfig`/`WorkspaceSceneResource`;`CapabilityFactoryRegistry.register(type_key, factory)`(`registry_factory.py:40`);`AgentResource` value dict 规范化(`_normalize_value`)。
- Produces: `workspace_scene_factory(value: dict, system_app) -> Capability`,从 `value`(含 `workspace_id`/`conv_uid`/`workspace_name`/`workspace_id`)还原 Capability,内含 `WorkspaceSceneConfig` + `WorkspaceSceneResource` 的 declare。

- [ ] **Step 1: 读现有 Capability/factory 实现作参照**

Run:
```bash
cd /Users/tuyang/GitHub/OpenDerisk
sed -n '1,80p' packages/derisk-core/src/derisk/agent/capabilities/registry.py
ls packages/derisk-core/src/derisk/agent/capabilities/*/  # 看现有 capability 目录结构
```
记录:`Capability` 基类接口(declare/requires/consume)、factory 注册约定、一个现有 capability(如 memory)的 factory 实现,作 Task 3/4 模板。

- [ ] **Step 2: 写失败测试**

```python
"""workspace_scene capability factory 测试:build_pack 能从 AgentResource 还原。"""
from unittest.mock import MagicMock


def test_workspace_scene_factory_registered():
    from derisk.agent.capabilities.registry_factory import get_default_factory_registry
    reg = get_default_factory_registry()
    reg.discover()
    assert "workspace_scene" in reg._factories


def test_workspace_scene_factory_builds_capability_from_value():
    from derisk_serve.workspace.scene_capability import workspace_scene_factory
    import json
    value = json.dumps({"workspace_id": 1, "conv_uid": "c1", "workspace_name": "营收"})
    cap = workspace_scene_factory(value, system_app=MagicMock())
    assert cap is not None
    contribs = cap.declare(cap._config) if hasattr(cap, "_config") else cap.declare()
    assert any(getattr(c.slot, "name", None) == "SYSTEM" or str(c.slot) == "Slot.SYSTEM" for c in contribs)


def test_build_pack_consumes_workspace_scene_agent_resource():
    """build_pack([AgentResource(type=workspace_scene)]) 产含 workspace_scene cap 的 pack。"""
    from derisk.agent.capabilities.registry_factory import get_default_factory_registry
    from derisk.agent.resource.base import AgentResource
    import json
    reg = get_default_factory_registry(); reg.discover()
    ar = AgentResource(type="workspace_scene", name="scene",
                       value=json.dumps({"workspace_id": 1, "conv_uid": "c1", "workspace_name": "x"}))
    pack = reg.build_pack([ar], system_app=MagicMock())
    cap_ids = [getattr(c, "capability_id", "?") for c in (pack.sub_resources or [])]
    assert any("workspace_scene" in str(i) for i in cap_ids)
```

- [ ] **Step 3: 运行确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_scene_capability.py -v`
Expected: FAIL — factory 未注册/不存在。

- [ ] **Step 4: 实现 `scene_capability.py` + 注册**

`scene_capability.py`(按 Step 1 记录的 Capability 基类接口实现;下文为骨架,确切基类名/方法以 Step 1 为准):

```python
"""workspace_scene capability:从 AgentResource.value 还原 WorkspaceSceneResource。"""
import json
from typing import Any, List

from derisk.core.interface.resource.bundle import Contribution
from derisk_serve.workspace.scene_resource import (
    WorkspaceSceneConfig, WorkspaceSceneResource,
)


class WorkspaceSceneCapability:
    """Capability 包装 WorkspaceSceneResource.declare。基类/接口按 derisk.agent.capabilities 现有 Capability。"""
    capability_id = "workspace_scene"

    def __init__(self, config: WorkspaceSceneConfig, system_app: Any = None):
        self._config = config
        self._system_app = system_app

    def declare(self, config: WorkspaceSceneConfig = None) -> List[Contribution]:
        return WorkspaceSceneResource.declare(config or self._config)

    def requires(self, config=None):
        return []


def workspace_scene_factory(value, system_app):
    """build_pack 调:value 是 AgentResource.value(string/dict),还原 Capability。"""
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            return None
    elif isinstance(value, dict):
        data = value
    elif hasattr(value, "to_dict"):
        data = value.to_dict()
    else:
        return None
    config = WorkspaceSceneConfig(
        workspace_id=int(data.get("workspace_id")),
        conv_uid=data.get("conv_uid", ""),
        workspace_name=data.get("workspace_name", ""),
    )
    return WorkspaceSceneCapability(config, system_app)


def register(registry):
    registry.register("workspace_scene", workspace_scene_factory)
```

注册:按 Step 1 记录的 discover 约定,在 `capabilities/registry.py` 的 import 列表/`__init__.py` 加 `from derisk_serve.workspace.scene_capability import register as register_scene_cap`,并在 discover 扫描时调用 `register_scene_cap(registry_factory)`。具体落点以 Step 1 现有约定为准(若 derisk-serve 的 capability 通过独立 register 函数被 derisk-core discover,则在 discover 路径加入;若需手动 register,在 app 启动初始化处加)。

- [ ] **Step 5: 运行确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk_serve/tests/derisk_serve/workspace/test_scene_capability.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/scene_capability.py \
  packages/derisk-core/src/derisk/agent/capabilities/registry.py \
  packages/derisk-serve/tests/derisk_serve/workspace/test_scene_capability.py
git commit -m "feat(scene): register workspace_scene capability factory for build_pack

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: playbook capability factory + PlaybookResource.to_agent_resource

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/playbook/resource/playbook_capability.py`
- Modify: `packages/derisk-serve/src/derisk_serve/playbook/resource/playbook_resource.py`(加 `to_agent_resource` 静态方法)
- Test: `packages/derisk-serve/tests/derisk_serve/playbook/resource/test_playbook_capability.py`

**Interfaces:**
- Consumes: `PlaybookResource`/`PlaybookConfig`(playbook_resource.py);`CapabilityFactoryRegistry.register`。
- Produces: `playbook_factory(value, system_app) -> Capability`;`PlaybookResource.to_agent_resource(config) -> AgentResource`(type="playbook", value=PlaybookConfig 序列化)。

- [ ] **Step 1: 写失败测试**

```python
"""playbook capability factory + to_agent_resource 测试。"""
import json
from unittest.mock import MagicMock


def test_playbook_factory_registered():
    from derisk.agent.capabilities.registry_factory import get_default_factory_registry
    reg = get_default_factory_registry(); reg.discover()
    assert "playbook" in reg._factories


def test_playbook_to_agent_resource_roundtrip():
    from derisk_serve.playbook.resource.playbook_resource import (
        PlaybookConfig, PlaybookResource,
    )
    cfg = PlaybookConfig(playbook_id=7, playbook_name="营收分析")
    ar = PlaybookResource.to_agent_resource(cfg)
    assert ar.type == "playbook"
    data = json.loads(ar.value) if isinstance(ar.value, str) else ar.value
    assert data["playbook_id"] == 7


def test_build_pack_consumes_playbook_agent_resource():
    from derisk.agent.capabilities.registry_factory import get_default_factory_registry
    from derisk_serve.playbook.resource.playbook_resource import (
        PlaybookConfig, PlaybookResource,
    )
    reg = get_default_factory_registry(); reg.discover()
    ar = PlaybookResource.to_agent_resource(PlaybookConfig(playbook_id=7, playbook_name="x"))
    pack = reg.build_pack([ar], system_app=MagicMock())
    assert any(getattr(c, "capability_id", "").startswith("playbook") for c in (pack.sub_resources or []))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/playbook/resource/test_playbook_capability.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现**

`playbook_capability.py`(骨架,基类/接口按 Task 3 Step 1 记录):

```python
"""playbook capability:从 AgentResource.value 还原 PlaybookResource.declare。"""
import json
from typing import Any, List

from derisk.core.interface.resource.bundle import Contribution
from derisk_serve.playbook.resource.playbook_resource import (
    PlaybookConfig, PlaybookResource,
)


class PlaybookCapability:
    capability_id = "playbook"

    def __init__(self, config: PlaybookConfig, system_app: Any = None):
        self._config = config
        self._system_app = system_app
        # workbench 剧本详情(query DB 拿 declaration)由装配器在 to_agent_resource 前预载入 config;
        # factory 只用 config(零 I/O 还原)。若 value 只含 playbook_id,这里查 DB 重建完整 config。
        if not config.text_content and not config.skills and system_app is not None:
            try:
                from derisk_serve.playbook.service.service import (
                    PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService,
                )
                svc = system_app.get_component(PLAYBOOK_SERVICE_COMPONENT_NAME, PlaybookService)
                pb = svc.get_by_id(config.playbook_id)
                if pb:
                    self._config = PlaybookConfig.from_playbook_response(pb)
            except Exception:
                pass

    def declare(self, config: PlaybookConfig = None) -> List[Contribution]:
        return PlaybookResource.declare(config or self._config)

    def requires(self, config=None):
        return []


def playbook_factory(value, system_app):
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except (TypeError, ValueError):
            return None
    elif isinstance(value, dict):
        data = value
    elif hasattr(value, "to_dict"):
        data = value.to_dict()
    else:
        return None
    config = PlaybookConfig(
        playbook_id=int(data.get("playbook_id")),
        playbook_name=data.get("playbook_name", ""),
    )
    return PlaybookCapability(config, system_app)


def register(registry):
    registry.register("playbook", playbook_factory)
```

在 `playbook_resource.py` 加静态方法:

```python
    @staticmethod
    def to_agent_resource(config: "PlaybookConfig"):
        from derisk.agent.resource.base import AgentResource
        import json as _json
        value = _json.dumps({
            "playbook_id": config.playbook_id,
            "playbook_name": config.playbook_name,
        }, ensure_ascii=False)
        return AgentResource(type="playbook", name=f"playbook_{config.playbook_id}", value=value)
```

注册 playbook factory(同 Task 3 注册路径,加 `register(registry)` 到 discover)。

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/playbook/resource/test_playbook_capability.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/playbook/resource/playbook_capability.py \
  packages/derisk-serve/src/derisk_serve/playbook/resource/playbook_resource.py \
  packages/derisk-serve/tests/derisk_serve/playbook/resource/test_playbook_capability.py \
  packages/derisk-core/src/derisk/agent/capabilities/registry.py
git commit -m "feat(playbook): playbook capability factory + to_agent_resource for build_pack

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: SceneResourceAssembler(场景业务装配器)

**Files:**
- Create: `packages/derisk-serve/src/derisk_serve/workspace/scene_resource_assembler.py`
- Test: `packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource_assembler.py`

**Interfaces:**
- Consumes: Task 2 的 `WorkspaceSceneConfig`/`WorkspaceSceneResource`;Task 4 的 `PlaybookConfig`/`PlaybookResource.to_agent_resource`;`WorkspaceService.get_by_id`、`TaskService.get_by_id`、`PlaybookService.get_by_id`。
- Produces: `SceneResourceAssembler.assemble(system_app, workspace_id, task_id, conv_uid) -> List[AgentResource]`。lobby → `[WorkspaceSceneResource.to_agent_resource(...)]`;workbench 有 playbook_id → `[PlaybookResource.to_agent_resource(...)]`;否则 `[]`。

- [ ] **Step 1: 写失败测试**

```python
"""SceneResourceAssembler 测试:lobby/workbench 装配 + 边界。"""
import json
from unittest.mock import MagicMock, patch


def _mock_system_app(workspace=None, task=None, playbook=None, missing_ws=False):
    sa = MagicMock()
    def get_component(name, cls=None):
        m = MagicMock()
        if name == "serve_workspace_service":
            m.get_by_id.return_value = None if missing_ws else (workspace or MagicMock(name="营收空间"))
        elif name == "serve_task_service":
            m.get_by_id.return_value = task
        elif name == "serve_playbook_service":
            m.get_by_id.return_value = playbook
        return m
    sa.get_component.side_effect = get_component
    return sa


def test_lobby_assembles_workspace_scene_resource():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    sa = _mock_system_app(workspace=MagicMock(name="营收空间"))
    out = SceneResourceAssembler.assemble(sa, workspace_id=1, task_id=None, conv_uid="c1")
    assert len(out) == 1
    assert out[0].type == "workspace_scene"
    data = json.loads(out[0].value) if isinstance(out[0].value, str) else out[0].value
    assert data["workspace_id"] == 1


def test_workbench_with_playbook_assembles_playbook_resource():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    task = MagicMock(); task.playbook_id = 7
    pb = MagicMock(id=7); pb.name = "营收分析"; pb.id = 7
    sa = _mock_system_app(task=task, playbook=pb)
    out = SceneResourceAssembler.assemble(sa, workspace_id=1, task_id=99, conv_uid="c1")
    assert len(out) == 1
    assert out[0].type == "playbook"


def test_workbench_without_playbook_returns_empty():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    task = MagicMock(); task.playbook_id = None
    sa = _mock_system_app(task=task)
    assert SceneResourceAssembler.assemble(sa, 1, 99, "c1") == []


def test_missing_workspace_returns_empty():
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    sa = _mock_system_app(missing_ws=True)
    assert SceneResourceAssembler.assemble(sa, 1, None, "c1") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource_assembler.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 `scene_resource_assembler.py`**

```python
"""SceneResourceAssembler — 场景空间业务:对话前按 lobby/workbench 装配资源。

agent 代码不感知;由 chat_completions 端点预处理层调用。产出 List[AgentResource],
并进 ext_info["dynamic_resources"],由标准 build_pack 消费。
"""
import logging
from typing import List, Optional

from derisk.agent.resource.base import AgentResource
from derisk_serve.playbook.resource.playbook_resource import (
    PlaybookConfig, PlaybookResource,
)
from derisk_serve.workspace.scene_resource import (
    WorkspaceSceneConfig, WorkspaceSceneResource,
)

logger = logging.getLogger(__name__)

_WORKSPACE = "serve_workspace_service"
_TASK = "serve_task_service"
_PLAYBOOK = "serve_playbook_service"


class SceneResourceAssembler:
    @staticmethod
    def assemble(system_app, workspace_id: int,
                 task_id: Optional[int], conv_uid: str) -> List[AgentResource]:
        try:
            if task_id:
                return SceneResourceAssembler._assemble_workbench(system_app, workspace_id, task_id)
            return SceneResourceAssembler._assemble_lobby(system_app, workspace_id, conv_uid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"SceneResourceAssembler failed: {e}", exc_info=True)
            return []

    @staticmethod
    def _assemble_lobby(system_app, workspace_id, conv_uid):
        ws_service = system_app.get_component(_WORKSPACE, None)
        ws = ws_service.get_by_id(workspace_id) if ws_service else None
        if not ws:
            return []
        config = WorkspaceSceneConfig(
            workspace_id=workspace_id, conv_uid=conv_uid,
            workspace_name=getattr(ws, "name", ""),
        )
        return [WorkspaceSceneResource.to_agent_resource(config)]

    @staticmethod
    def _assemble_workbench(system_app, workspace_id, task_id):
        task_service = system_app.get_component(_TASK, None)
        task = task_service.get_by_id(task_id) if task_service else None
        if not task or not task.playbook_id:
            return []
        playbook_service = system_app.get_component(_PLAYBOOK, None)
        pb = playbook_service.get_by_id(task.playbook_id) if playbook_service else None
        if not pb:
            return []
        config = PlaybookConfig.from_playbook_response(pb)
        return [PlaybookResource.to_agent_resource(config)]
```

在 `scene_resource.py` 的 `WorkspaceSceneResource` 加 `to_agent_resource`(同 Task 4 模式):

```python
    @staticmethod
    def to_agent_resource(config: "WorkspaceSceneConfig"):
        from derisk.agent.resource.base import AgentResource
        import json as _json
        value = _json.dumps({
            "workspace_id": config.workspace_id,
            "conv_uid": config.conv_uid,
            "workspace_name": config.workspace_name,
        }, ensure_ascii=False)
        return AgentResource(type="workspace_scene", name=f"workspace_scene_{config.workspace_id}", value=value)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource_assembler.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/workspace/scene_resource_assembler.py \
  packages/derisk-serve/src/derisk_serve/workspace/scene_resource.py \
  packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource_assembler.py
git commit -m "feat(scene): SceneResourceAssembler — lobby/workbench assemble pre-chat

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: chat_completions 端点预处理层调装配器

**Files:**
- Modify: `packages/derisk-app/src/derisk_app/openapi/api_v1/api_v1.py`(394 端点内,446 后)
- Test: `packages/derisk-app/tests/` 下端点测试(若有)或单测装配器接入函数

**Interfaces:**
- Consumes: Task 5 的 `SceneResourceAssembler.assemble`;`dialogue.ext_info`/`dialogue.conv_uid`。
- Produces: 端点在有 workspace_id 时调装配器,产出并进 `dialogue.ext_info["dynamic_resources"]`。

- [ ] **Step 1: 抽纯函数 + 写测试**(端点难单测,抽 `_assemble_scene_resources(ext_info, conv_uid) -> list` 纯函数)

在 `api_v1.py` `chat_completions` 附近加模块级函数:

```python
def _assemble_scene_resources(ext_info: dict, conv_uid: str):
    """预处理:有 workspace_id 时调场景资源装配器,返回待并入 dynamic_resources 的列表。"""
    ws_id = ext_info.get("workspace_id") if ext_info else None
    if not ws_id:
        return []
    from derisk_serve.workspace.scene_resource_assembler import SceneResourceAssembler
    from derisk.component import CFG
    return SceneResourceAssembler.assemble(
        CFG.SYSTEM_APP, workspace_id=int(ws_id),
        task_id=ext_info.get("task_id"), conv_uid=conv_uid,
    )
```

测试(放 `packages/derisk-app/tests/test_scene_resource_endpoint.py`,若无测试框架则按现有 api_v1 测试约定):

```python
from unittest.mock import patch, MagicMock
from derisk_app.openapi.api_v1.api_v1 import _assemble_scene_resources


def test_assemble_scene_resources_noop_without_workspace():
    assert _assemble_scene_resources({}, "c1") == []


def test_assemble_scene_resources_calls_assembler_with_workspace():
    with patch("derisk_serve.workspace.scene_resource_assembler.SceneResourceAssembler.assemble") as m:
        m.return_value = [MagicMock(type="workspace_scene")]
        out = _assemble_scene_resources({"workspace_id": 5}, "c1")
        assert len(out) == 1
        m.assert_called_once()
        _, kwargs = m.call_args
        assert kwargs["workspace_id"] == 5
        assert kwargs["task_id"] is None
```

- [ ] **Step 2: 运行确认失败**

Run(若有 derisk-app 测试运行器): `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-app/tests/test_scene_resource_endpoint.py -v 2>/dev/null || python -c "from derisk_app.openapi.api_v1.api_v1 import _assemble_scene_resources; print('import ok')"`
Expected: FAIL(import 失败)或函数不存在。

- [ ] **Step 3: 接入端点**

在 `chat_completions`(394)内,446 后(`dialogue.ext_info.update` 们之后)、`in_message = HumanMessage.parse_chat_completion_message(...)`(448)之前插入:

```python
        # 预处理:场景空间资源装配(agent 通用骨架不感知,此处为场景业务)
        scene_res = _assemble_scene_resources(dialogue.ext_info, dialogue.conv_uid)
        if scene_res:
            existing_dyn = dialogue.ext_info.get("dynamic_resources") or []
            existing_dyn.extend(scene_res)
            dialogue.ext_info["dynamic_resources"] = existing_dyn
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-app/tests/test_scene_resource_endpoint.py -v 2>/dev/null || python -c "import derisk_app.openapi.api_v1.api_v1 as m; m._assemble_scene_resources({}, 'c1'); print('ok')"`
Expected: 测试 PASS 或 `ok`。

- [ ] **Step 5: 提交**

```bash
git add packages/derisk-app/src/derisk_app/openapi/api_v1/api_v1.py \
  packages/derisk-app/tests/test_scene_resource_endpoint.py
git commit -m "feat(web-api): assemble scene resources in chat_completions pre-processing

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 移除 _inject_workspace_context 旧 toolkit 注入段 + 删 build_workspace_toolkit

**Files:**
- Modify: `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py`(移除 `_inject_workspace_context` 的 204-241 段 + 88 import)
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py`(删 `build_workspace_toolkit`/`WorkspaceControlAgent`)
- Modify: `packages/derisk-serve/src/derisk_serve/workspace/agent_tools/__init__.py`(删导出)
- Test: 现有 `test_agent_chat_playbook_command.py` 仍通过;新增回归断言 `_inject_workspace_context` 不再 append extra_agents

**Interfaces:**
- Consumes: 前序 Task 的资源协议正道已就位(装配器+factory+端点)。
- Produces: agent 代码不再造 toolkit agent、不再 `agent_to_resource(extra_agent)` 崩;`extra_agents` 始终空。

- [ ] **Step 1: 写失败/回归测试**

追加到 `packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py`:

```python
def test_inject_workspace_context_no_longer_appends_extra_agents():
    """移除 toolkit 注入后,_inject_workspace_context 不再往 extra_agents append。"""
    from derisk_serve.agent.agents.chat.agent_chat import _inject_workspace_context
    from unittest.mock import MagicMock, patch
    extra_agents = []
    ext_info = {"workspace_id": 1}
    with patch("derisk_serve.agent.agents.chat.agent_chat._legacy_build_workspace_context") as mleg, \
         patch("derisk_serve.agent.agents.chat.agent_chat.build_workspace_context") as mbwc, \
         patch("derisk_serve.agent.agents.chat.agent_chat.render_workspace_context_summary") as msum, \
         patch("derisk_serve.agent.agents.chat.agent_chat.render_scene_dynamic_context") as mscene:
        mleg.return_value = {"materialized": {"dynamic_resources": [], "extra_agents": []}}
        mbwc.return_value = MagicMock(playbook_resource=None)
        msum.return_value = ""; mscene.return_value = ""
        _inject_workspace_context(
            system_app=MagicMock(), workspace_id=1, user_id="u1",
            conv_uid="c1", task_id=None, system_prompt=[],
            extra_agents=extra_agents, ext_info=ext_info, llm_config=None,
            event_queue=None, app_code="scene-workspace-agent",
        )
    assert extra_agents == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py::test_inject_workspace_context_no_longer_appends_extra_agents -v`
Expected: FAIL(现状 241 行 append toolkit agent)。

- [ ] **Step 3: 移除 agent_chat.py 旧段**

在 `_inject_workspace_context`(147-243)中,删除 204-241(从 `# NEW: RFC-005 剧本资源注入` 注释到 `extra_agents.append(agent)` 含 `build_workspace_toolkit` 调用 + playbook_resource declare 进 system + toolkit append)。**保留 166-202**(workspace_context/scene_dynamic 进 system_prompt)。移除后函数以 242-243 的 `except` 收尾。

删除 `agent_chat.py:88` `from derisk_serve.workspace.agent_tools.toolkit import build_workspace_toolkit`(若仅此处用)。

- [ ] **Step 4: 删 build_workspace_toolkit/WorkspaceControlAgent**

`toolkit.py`:删除 `WorkspaceControlAgent` 类(26-46)与 `build_workspace_toolkit` 函数(49-112)。保留文件顶部的 `LAYER1_READ`/`LAYER2_READ`/`LAYER3_READ` 常量(若 read_tools 或他处引用;若无人引用则一并删)。若 `toolkit.py` 删空,删整个文件并清 `__init__.py` 的 `build_workspace_toolkit` 导出。

`__init__.py`:删 `from .toolkit import build_workspace_toolkit` 与 `__all__` 里的 `"build_workspace_toolkit"`。

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run:
```bash
cd /Users/tuyang/GitHub/OpenDerisk
python -m pytest packages/derisk-serve/tests/derisk_serve/workspace/agent_tools/ packages/derisk-serve/tests/derisk_serve/agent/agents/chat/ packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource.py packages/derisk-serve/tests/derisk_serve/workspace/test_scene_resource_assembler.py packages/derisk-serve/tests/derisk_serve/workspace/test_scene_capability.py packages/derisk-serve/tests/derisk_serve/playbook/resource/test_playbook_capability.py -v
```
Expected: 全 PASS(含 7 Task1 连带 + 新回归)。

- [ ] **Step 6: grep 确认无残留引用**

Run:
```bash
cd /Users/tuyang/GitHub/OpenDerisk
grep -rn "build_workspace_toolkit\|WorkspaceControlAgent" packages/ --include="*.py" | grep -v __pycache__
```
Expected: 空(或仅注释/历史,无活引用)。

- [ ] **Step 7: 提交**

```bash
git add packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py \
  packages/derisk-serve/src/derisk_serve/workspace/agent_tools/toolkit.py \
  packages/derisk-serve/src/derisk_serve/workspace/agent_tools/__init__.py \
  packages/derisk-serve/tests/derisk_serve/agent/agents/chat/test_agent_chat_playbook_command.py
git commit -m "refactor(scene): remove build_workspace_toolkit/extra_agents legacy injection

Scene tools now flow via resource protocol (WorkspaceSceneResource TOOLS slot)
assembled pre-chat. Fixes agent_context-None crash in agent_to_resource.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 验证 — 全链路冒烟

**Files:** 无代码改动,仅运行验证。

- [ ] **Step 1: 后端全量测试**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && python -m pytest packages/derisk-serve/tests/ packages/derisk-app/tests/ -v 2>&1 | tail -20`
Expected: 本计划相关测试全 PASS;预先存在的无关失败记录但不归责本计划。

- [ ] **Step 2: 端到端冒烟(用户/人工)**

起 derisk 后端 + web 前端,在场景空间:
1. lobby 发对话(不选剧本)→ 不崩、主 agent `scene-workspace-agent` 构建、日志见 `[AgentChat] CapabilityPack built: ... caps (...'workspace_scene:system'...)`、Agent 能调 `list_tasks` 等场景管理工具。
2. workbench 选剧本发起任务 → 任务对话不崩、日志见 playbook capability、Agent 能调剧本工具。
3. 确认无 `agent_context ... agent_app_code` 错误。

> 若无法本地起服务,至少完成 Step 1,并在 PR 描述标注 Step 2 待验证。

- [ ] **Step 3: 改动文件清单确认**

Run: `cd /Users/tuyang/GitHub/OpenDerisk && git diff --stat 7ea180ff..HEAD`
Expected: 新建 scene_resource.py/scene_resource_assembler.py/scene_capability.py/playbook_capability.py + 改 agent_chat.py/api_v1.py/toolkit.py/__init__.py/write_tools.py/registry.py/playbook_resource.py + 诸测试。

---

## Self-Review

**1. Spec coverage:** spec §4.1 装配器 → Task 5;§4.2 WorkspaceSceneResource(SYSTEM+TOOLS 四类工具)→ Task 2(+Task 1 补齐写工具);§4.3 PlaybookResource 迁移 → Task 4;§4.4 端点预处理注入 → Task 6;§4.5 移除旧路径 → Task 7;§3 架构/§5 数据流 → Task 6+7+factory(Task 3/4);§7 测试 → 各 Task TDD + Task 8。覆盖完整。spec §"不做"(Executor/实时数据走协议)本计划不做,符合。

**2. Placeholder scan:** Task 1 Step 1/4、Task 3 Step 1 有"按记录调整签名"——这是必要的运行期确认(依赖 service 真实签名),非占位,但给了具体回退路径。无 TBD/TODO。所有代码块完整。

**3. Type consistency:** `WorkspaceSceneConfig(workspace_id, conv_uid, workspace_name)` 在 Task 2/3/5 一致;`capability_id="workspace_scene"`/`type_key="workspace_scene"` 一致;`PlaybookConfig.from_playbook_response` 真实存在(playbook_resource.py:101);`PlaybookResource.to_agent_resource` Task 4 定义、Task 5 用;`build_scene_management_tools` Task 2 定义、被 declare 用;`build_scene_write_tools` Task 1 定义、Task 2 用;`_assemble_scene_resources` Task 6 定义、端点用。一致。

**4. 关键实现风险(已在对应 Task 标注):**
- `build_pack` 经 factory 注册消费(Task 3/4 的 `register`);若 derisk-serve capability 不被 derisk-core discover 自动扫,需在 app 启动初始化手动 register(Task 3 Step 4 已注)。
- `Slot.SYSTEM` 枚举访问以 PlaybookResource 现用法对齐(Task 2 Step 3 注)。
- PlaybookCapability 内查 DB 重建 config(Task 4)— 若装配器已预载 full config(`PlaybookConfig.from_playbook_response`),factory 可不查;Task 5 已用 from_playbook_response,故 factory 可简化为 zero-IO(实现时确认,Task 4 Step 3 注)。