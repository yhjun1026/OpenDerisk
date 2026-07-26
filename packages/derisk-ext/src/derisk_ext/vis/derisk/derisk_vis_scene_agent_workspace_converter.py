"""场景空间 AgentWorkspace 可视化转换器。

产出结构化 vis 产物 {render_name, planning, execution[], summary},前端 AgentWorkspaceRenderer 消费。
注册靠子类扫描(render_name = scene_agent_workspace)。

数据契约(与运行时核实):
- stream_msg LLM 流式: {message_id, sender, content(累计文本), thinking, status:"running"}
- stream_msg 工具调用: {type:"all"|"incr", action_report:[ActionOutput]} (pydantic 对象,属性访问)
- gpt_msg: GptsMessage,.content 为 assistant 文本,.action_report 为 List[dict](DB 序列化形态)
- messages: List[GptsMessage] 全量历史(每次调用都传入,用于幂等重建)
- plans_map: Dict[str, GptsPlan] 计划(可能为空)
"""
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from derisk_ext.vis.derisk.derisk_vis_manus_converter import (
    DeriskIncrVisManusConverter,
)

# 单步输出截断上限,避免超大工具结果撑爆 SSE / 前端渲染
_MAX_OUTPUT_CHARS = 4000
# 工具执行中占位文案,不作为有效 output
_RUNNING_PLACEHOLDERS = {"执行中", "执行中..", "执行中..."}
# 人类角色标识(GptsMessage.role / sender 上的人类侧取值)
_HUMAN_ROLES = {"Human", "user", "human", "UserProxy"}
# 最终回答的占位 action,不作为工具步骤展示(其内容即 summary)
_SKIP_TOOL_NAMES = {"blank"}


class SceneAgentWorkspaceConverter(DeriskIncrVisManusConverter):
    """场景空间 AgentWorkspace 转换器。

    不复用 manus 的 VIS tag 输出,改为维护一份累积的结构化状态
    (工具步骤 / 阶段回复 / 思考 / 计划),每次推送全量输出,
    前端按 id 合并。
    """

    SCENE_TAG = "scene_agent_workspace"

    # opt-in:vis_messages/vis_final 的消息合并默认屏蔽 Human 消息,
    # 本转换器需要用户消息(渲染用户气泡),故声明保留。
    include_user_messages = True

    def __init__(self, paths: Optional[str] = None, **kwargs):
        super().__init__(paths, **kwargs)
        # key 前缀区分来源: tool-{action_id} / think-{message_id} / narr-{message_id}
        # value = (step_dict, ts_str);ts 用于跨来源按时间交错排序
        self._scene_items: Dict[str, Tuple[Dict[str, Any], str]] = {}
        # message_id -> (assistant 文本, ts_str);最新一条进 summary,其余凝固为步骤
        self._scene_narrations: Dict[str, Tuple[str, str]] = {}

    @property
    def reuse_name(self):
        # 通用页(/chat 历史会话、应用详情)不认识 scene_agent_workspace 协议,
        # 声明回退到 vis_manus 布局:通用页用 manus converter 实时组装同一份消息数据
        return "vis_manus"

    @property
    def render_name(self):
        return "scene_agent_workspace"

    @property
    def web_use(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "场景空间 AgentWorkspace 结构化可视化布局"

    # ------------------------------------------------------------------
    # 解析辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if not isinstance(value, str):
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _report_get(report: Any, key: str) -> Any:
        """兼容 ActionOutput(pydantic 对象)与 dict 两种形态。"""
        if isinstance(report, dict):
            return report.get(key)
        return getattr(report, key, None)

    @staticmethod
    def _ts_str(value: Any) -> str:
        """归一化时间戳为可比较字符串(datetime / str / None)。"""
        if value is None:
            return ""
        iso = getattr(value, "isoformat", None)
        if callable(iso):
            try:
                return iso()
            except Exception:  # noqa: BLE001 - 时间戳异常不影响主流程
                return ""
        return str(value)

    def _tool_name_from_view(self, view: Any) -> Optional[str]:
        """从 d-tool vis fence 中提取 tool_name 兜底。"""
        if not isinstance(view, str) or "```" not in view:
            return None
        try:
            body = view.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(body)
            return data.get("tool_name")
        except (IndexError, ValueError, TypeError):
            return None

    def _upsert_tool_step(self, report: Any) -> None:
        action_id = self._report_get(report, "action_id")
        if not action_id:
            return
        key = f"tool-{action_id}"

        state = str(self._report_get(report, "state") or "").lower()
        success = self._report_get(report, "is_exe_success")
        if success is False or state in ("failed", "error", "blocked"):
            status = "failed"
        elif state in ("running", "pending", "executing", "todo", "waiting", "retrying"):
            status = "running"
        else:
            status = "done"

        tool = (
            self._report_get(report, "action")
            or self._tool_name_from_view(self._report_get(report, "view"))
            or self._report_get(report, "action_name")
            or self._report_get(report, "name")
            or "工具调用"
        )
        if str(tool).lower() in _SKIP_TOOL_NAMES:
            return

        raw_input = self._report_get(report, "action_input")
        action_input = raw_input if isinstance(raw_input, dict) else self._safe_json_loads(raw_input)

        content = self._report_get(report, "content")
        output = None
        if isinstance(content, str) and content.strip() and content.strip() not in _RUNNING_PLACEHOLDERS:
            output = content.strip()[:_MAX_OUTPUT_CHARS]

        existing = self._scene_items.get(key)
        step = existing[0] if existing else {
            "id": str(action_id),
            "type": "tool_call",
            "title": str(tool),
            "status": "running",
            "action": str(tool),
            "action_input": None,
            "output": None,
            "artifact": None,
            "vis": None,
        }
        step["title"] = str(tool)
        step["action"] = str(tool)
        step["status"] = status
        if action_input is not None:
            step["action_input"] = action_input
        if output is not None:
            step["output"] = output
        ts = self._ts_str(self._report_get(report, "start_time")) or (existing[1] if existing else "")
        self._scene_items[key] = (step, ts)

    def _ingest_assistant_text(
        self, message_id: Optional[str], content: Any, ts: Any = None, append: bool = False
    ) -> None:
        """登记 assistant 文本(阶段回复/最终回答候选,最新一条进 summary)。

        append=True 用于 LLM 流式:stream_msg.content 是增量 delta,需追加;
        来自持久化消息的全量文本则整体替换。
        """
        if not isinstance(content, str) or not content:
            return
        mid = message_id or "unknown"
        prev_text, prev_ts = self._scene_narrations.get(mid, ("", ""))
        text = (prev_text + content) if append else content
        self._scene_narrations[mid] = (text.strip() if not append else text, self._ts_str(ts) or prev_ts)

    def _ingest_thinking(self, message_id: Optional[str], thinking: Any, live: bool, ts: Any = None) -> None:
        if not isinstance(thinking, str) or not thinking.strip():
            return
        mid = message_id or "unknown"
        key = f"think-{mid}"
        prev_step, prev_ts = self._scene_items.get(key, ({}, ""))
        # 流式 thinking 同样是增量 delta,追加而非替换
        prev_output = prev_step.get("output", "") if isinstance(prev_step, dict) else ""
        output = (prev_output + thinking) if live else thinking.strip()
        self._scene_items[key] = ({
            "id": key,
            "type": "thinking",
            "title": "深度思考",
            "status": "running" if live else "done",
            "action": None,
            "action_input": None,
            "output": output[:_MAX_OUTPUT_CHARS],
            "artifact": None,
            "vis": None,
        }, self._ts_str(ts) or prev_ts)

    def _ingest_user_message(self, msg: Any) -> None:
        """用户消息 → user 步骤(展示用户问题,气泡渲染)。"""
        content = getattr(msg, "content", None)
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            # 多模态:拼接 text 片段
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            text = " ".join(p for p in parts if p)
        if not text.strip():
            return
        mid = getattr(msg, "message_id", None) or uuid.uuid4().hex
        key = f"user-{mid}"
        self._scene_items[key] = ({
            "id": key,
            "type": "user",
            "title": "我",
            "status": "done",
            "action": None,
            "action_input": None,
            "output": text.strip()[:_MAX_OUTPUT_CHARS],
            "artifact": None,
            "vis": None,
        }, self._ts_str(getattr(msg, "created_at", None)))

    def _ingest_message(self, msg: Any) -> None:
        """从一条 GptsMessage(已完成)摄取步骤 / 思考 / 回复。"""
        role = str(getattr(msg, "role", "") or "")
        sender = str(getattr(msg, "sender", "") or "")
        if role in _HUMAN_ROLES or sender in _HUMAN_ROLES:
            self._ingest_user_message(msg)
            return
        if role == "tool":
            return
        message_id = getattr(msg, "message_id", None)
        ts = getattr(msg, "created_at", None)

        reports = getattr(msg, "action_report", None)
        if isinstance(reports, (list, tuple)):
            for report in reports:
                self._upsert_tool_step(report)

        self._ingest_thinking(message_id, getattr(msg, "thinking", None), live=False, ts=ts)
        self._ingest_assistant_text(message_id, getattr(msg, "content", None), ts=ts)

    def _ingest_stream_msg(self, stream_msg: Union[Dict, str]) -> None:
        if not isinstance(stream_msg, dict):
            return
        message_id = stream_msg.get("message_id") or stream_msg.get("uid")
        ts = stream_msg.get("start_time")

        reports = stream_msg.get("action_report")
        if isinstance(reports, (list, tuple)):
            for report in reports:
                self._upsert_tool_step(report)

        if stream_msg.get("thinking"):
            self._ingest_thinking(message_id, stream_msg.get("thinking"), live=True, ts=ts)
        if stream_msg.get("content"):
            # stream content 是增量 delta,追加
            self._ingest_assistant_text(message_id, stream_msg.get("content"), ts=ts, append=True)

    def _build_planning(self, plans_map: Optional[Dict[str, Any]], messages: List[Any]) -> Optional[Dict[str, Any]]:
        if not plans_map:
            return None
        plans = sorted(
            plans_map.values(),
            key=lambda p: (getattr(p, "conv_round", 0) or 0, getattr(p, "sub_task_num", 0) or 0),
        )
        if not plans:
            return None

        status_map = {"todo": "pending", "running": "running", "complete": "done", "failed": "failed"}
        steps = []
        for p in plans:
            state = str(getattr(p, "state", "") or "").lower()
            steps.append({
                "id": str(getattr(p, "task_uid", None) or getattr(p, "sub_task_id", "") or uuid.uuid4().hex),
                "title": str(getattr(p, "sub_task_title", None) or getattr(p, "sub_task_content", "") or "子任务"),
                "status": status_map.get(state, "pending"),
            })

        goal = getattr(plans[0], "task_round_title", None) or ""
        if not goal:
            for msg in messages:
                sender = str(getattr(msg, "sender", "") or "")
                role = str(getattr(msg, "role", "") or "")
                if sender in _HUMAN_ROLES or role in _HUMAN_ROLES:
                    content = getattr(msg, "content", None)
                    if isinstance(content, str) and content.strip():
                        goal = content.strip()[:200]
                        break
        return {"goal": goal or "任务计划", "steps": steps}

    def _build_view(self, plans_map: Optional[Dict[str, Any]], messages: List[Any]) -> Dict[str, Any]:
        # 最新一条 assistant 文本 → summary;之前的阶段回复凝固为 execution 步骤
        narr_ids = list(self._scene_narrations.keys())
        summary: Optional[str] = None
        frozen_narr: List[Tuple[str, str]] = []  # (text, ts)
        if narr_ids:
            summary = self._scene_narrations[narr_ids[-1]][0]
            frozen_narr = [self._scene_narrations[mid] for mid in narr_ids[:-1]]

        execution: List[Tuple[Dict[str, Any], str]] = list(self._scene_items.values())
        for text, ts in frozen_narr:
            execution.append(({
                "id": f"narr-{uuid.uuid5(uuid.NAMESPACE_URL, text[:64]).hex[:12]}",
                "type": "thinking",
                "title": "阶段回复",
                "status": "done",
                "action": None,
                "action_input": None,
                "output": text[:_MAX_OUTPUT_CHARS],
                "artifact": None,
                "vis": None,
            }, ts))

        # 按时间交错排序(无 ts 的排后,稳定)
        execution.sort(key=lambda item: item[1] or "￿")
        # ts 透出给前端:跨轮次(agent conv)合并时按时间交错
        ordered_steps = [{**step, "ts": ts or None} for step, ts in execution]

        return {
            "render_name": "scene_agent_workspace",
            "planning": self._build_planning(plans_map, messages),
            "execution": ordered_steps,
            "summary": summary,
        }

    def _render(self, plans_map: Optional[Dict[str, Any]], messages: List[Any]) -> str:
        body = json.dumps(self._build_view(plans_map, messages), ensure_ascii=False)
        return f"```{self.SCENE_TAG}\n{body}\n```"

    # ------------------------------------------------------------------
    # 入口:运行期增量推送 + 历史最终视图
    # ------------------------------------------------------------------
    async def visualization(
        self,
        messages: List[Any],
        plans_map: Optional[Dict[str, Any]] = None,
        gpt_msg: Any = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[Any]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict[str, Any]] = None,
        main_agent_name: Optional[str] = None,
        is_first_push: bool = False,
        **kwargs,
    ) -> str:
        """产出结构化 vis tag 包裹的 JSON(每次全量,前端按 id 合并)。"""
        for msg in messages or []:
            self._ingest_message(msg)
        if gpt_msg is not None:
            self._ingest_message(gpt_msg)
        if stream_msg:
            self._ingest_stream_msg(stream_msg)
        return self._render(plans_map, messages or [])

    async def final_view(
        self,
        messages: List[Any],
        plans_map: Optional[Dict[str, Any]] = None,
        senders_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """历史查询路径(query_chat → vis_final):从持久化消息重建完整视图。"""
        self._scene_items = {}
        self._scene_narrations = {}
        for msg in messages or []:
            self._ingest_message(msg)
        return self._render(plans_map, messages or [])
