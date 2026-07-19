"""Unit tests for SceneAgentWorkspaceConverter."""
import json
import re
import pytest

from derisk_ext.vis.derisk.derisk_vis_scene_agent_workspace_converter import (
    SceneAgentWorkspaceConverter,
)


def _make_gpt_msg(content="", thinking=None, action_report=None, message_id="m1", sender="BAIZE"):
    """构造一个最小 GptsMessage-like 对象(对齐真实 GptsMessage 契约)。"""
    class _Msg:
        def __init__(self):
            self.message_id = message_id
            self.sender = sender
            self.role = "assistant" if sender != "Human" else "Human"
            self.content = content
            self.thinking = thinking
            self.action_report = action_report
            self.created_at = None
    return _Msg()


def _make_action_output(**overrides):
    """构造 ActionOutput-like 对象(流内工具推送形态)。"""
    class _AO:
        pass
    ao = _AO()
    ao.action_id = overrides.get("action_id", "tool-abc")
    ao.action = overrides.get("action", "Bash")
    ao.action_name = overrides.get("action_name", "Execute a shell command")
    ao.action_input = overrides.get("action_input", {"command": "ls"})
    ao.content = overrides.get("content", "执行中")
    ao.state = overrides.get("state", "running")
    ao.is_exe_success = overrides.get("is_exe_success", True)
    ao.start_time = overrides.get("start_time", "2026-07-17T08:20:34")
    ao.view = overrides.get("view")
    return ao


def _extract_payload(out: str) -> dict:
    match = re.search(r"```scene_agent_workspace\n(.*?)\n```", out, re.DOTALL)
    assert match is not None, f"未找到 scene_agent_workspace vis tag, got: {out!r}"
    return json.loads(match.group(1))


@pytest.mark.asyncio
async def test_render_name_is_scene_agent_workspace():
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    assert conv.render_name == "scene_agent_workspace"
    assert conv.web_use is True


@pytest.mark.asyncio
async def test_tool_stream_msg_produces_execution_step():
    """stream_msg 携带 action_report(ActionOutput 对象)→ execution 工具步骤。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    stream_msg = {
        "type": "all",
        "message_id": "m1",
        "action_report": [_make_action_output(state="running", content="执行中")],
    }
    payload = _extract_payload(await conv.visualization(messages=[], stream_msg=stream_msg))

    assert payload["render_name"] == "scene_agent_workspace"
    assert len(payload["execution"]) == 1
    step = payload["execution"][0]
    assert step["action"] == "Bash"
    assert step["status"] == "running"
    assert step["action_input"] == {"command": "ls"}
    # 执行中占位文案不作为 output
    assert step["output"] is None

    # 同一 action_id 完成推送 → 步骤状态与结果被合并更新
    done_msg = {
        "type": "all",
        "message_id": "m1",
        "action_report": [_make_action_output(state="complete", content="找到 3 条记录")],
    }
    payload = _extract_payload(await conv.visualization(messages=[], stream_msg=done_msg))
    assert len(payload["execution"]) == 1
    step = payload["execution"][0]
    assert step["status"] == "done"
    assert step["output"] == "找到 3 条记录"


@pytest.mark.asyncio
async def test_streaming_text_becomes_summary():
    """LLM 流式文本(stream_msg.content,增量 delta)→ summary 实时拼接更新。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    out1 = await conv.visualization(messages=[], stream_msg={"message_id": "m9", "content": "正在"})
    assert _extract_payload(out1)["summary"] == "正在"
    out2 = await conv.visualization(messages=[], stream_msg={"message_id": "m9", "content": "查询"})
    assert _extract_payload(out2)["summary"] == "正在查询"


@pytest.mark.asyncio
async def test_streaming_delta_appends_not_replaces():
    """stream_msg.content 是增量 delta:多个 chunk 应追加拼接,而非互相替换。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    await conv.visualization(messages=[], stream_msg={"message_id": "m9", "content": "正在"})
    await conv.visualization(messages=[], stream_msg={"message_id": "m9", "content": "查询"})
    out = await conv.visualization(messages=[], stream_msg={"message_id": "m9", "content": "任务"})
    assert _extract_payload(out)["summary"] == "正在查询任务"


@pytest.mark.asyncio
async def test_gpt_msg_history_dict_reports():
    """gpt_msg(落库形态:action_report 为 List[dict])→ 步骤 + summary。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    report = {
        "action_id": "tool-1",
        "action": "search_workspace",
        "action_input": {"query": "营收"},
        "state": "complete",
        "is_exe_success": True,
        "content": "找到 3 条记录",
        "start_time": "2026-07-17T08:20:34",
    }
    msg = _make_gpt_msg(content="这是最终回答", action_report=[report], message_id="m7")
    payload = _extract_payload(await conv.visualization(messages=[msg], gpt_msg=msg))

    assert payload["summary"] == "这是最终回答"
    tool_steps = [s for s in payload["execution"] if s["type"] == "tool_call"]
    assert len(tool_steps) == 1
    assert tool_steps[0]["action"] == "search_workspace"
    assert tool_steps[0]["status"] == "done"
    assert tool_steps[0]["output"] == "找到 3 条记录"


@pytest.mark.asyncio
async def test_intermediate_replies_become_steps_not_summary():
    """多条 assistant 文本:最新一条进 summary,之前的凝固为阶段回复步骤。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    msgs = [
        _make_gpt_msg(content="先查一下", message_id="m1"),
        _make_gpt_msg(content="最终结果如下", message_id="m2"),
    ]
    payload = _extract_payload(await conv.final_view(messages=msgs))
    assert payload["summary"] == "最终结果如下"
    narr_steps = [s for s in payload["execution"] if s["type"] == "thinking"]
    assert len(narr_steps) == 1
    assert narr_steps[0]["output"] == "先查一下"


@pytest.mark.asyncio
async def test_user_message_becomes_user_step():
    """Human 消息 → user 类型步骤(前端渲染用户气泡)。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    msgs = [
        _make_gpt_msg(content="帮我查下任务", message_id="u1", sender="Human"),
        _make_gpt_msg(content="好的,结果如下", message_id="a1"),
    ]
    payload = _extract_payload(await conv.final_view(messages=msgs))
    user_steps = [s for s in payload["execution"] if s["type"] == "user"]
    assert len(user_steps) == 1
    assert user_steps[0]["output"] == "帮我查下任务"
    assert payload["summary"] == "好的,结果如下"


@pytest.mark.asyncio
async def test_blank_action_is_skipped():
    """最终回答的 blank 占位 action 不作为工具步骤(内容即 summary)。"""
    conv = SceneAgentWorkspaceConverter(derisk_url="http://localhost")
    report = {"action_id": "a1", "action": "blank", "state": "complete", "content": "最终回答"}
    msg = _make_gpt_msg(content="最终回答", action_report=[report], message_id="m8")
    payload = _extract_payload(await conv.visualization(messages=[msg]))
    assert [s for s in payload["execution"] if s["type"] == "tool_call"] == []
