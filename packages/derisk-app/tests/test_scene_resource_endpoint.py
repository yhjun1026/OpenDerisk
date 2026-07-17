"""Task 6: chat_completions 端点预处理层 -> SceneResourceAssembler 接入测试。

抽 `_assemble_scene_resources(ext_info, conv_uid)` 为模块级纯函数,便于在不
起整个端点的情况下单测。本文件覆盖:
- 无 workspace_id -> [](装配器不触发)
- 有 workspace_id -> 调 SceneResourceAssembler.assemble 并原样返回其结果
- task_id 透传(为 None 时也透传)
"""
from unittest.mock import patch, MagicMock

from derisk_app.openapi.api_v1.api_v1 import _assemble_scene_resources


def test_assemble_scene_resources_noop_without_workspace():
    assert _assemble_scene_resources({}, "c1") == []


def test_assemble_scene_resources_calls_assembler_with_workspace():
    with patch(
        "derisk_serve.workspace.scene_resource_assembler.SceneResourceAssembler.assemble"
    ) as m:
        m.return_value = [MagicMock(type="workspace_scene")]
        out = _assemble_scene_resources({"workspace_id": 5}, "c1")
        assert len(out) == 1
        m.assert_called_once()
        _, kwargs = m.call_args
        assert kwargs["workspace_id"] == 5
        assert kwargs["task_id"] is None
        assert kwargs["conv_uid"] == "c1"


def test_assemble_scene_resources_forwards_task_id():
    with patch(
        "derisk_serve.workspace.scene_resource_assembler.SceneResourceAssembler.assemble"
    ) as m:
        m.return_value = []
        _assemble_scene_resources({"workspace_id": 7, "task_id": 42}, "c2")
        _, kwargs = m.call_args
        assert kwargs["workspace_id"] == 7
        assert kwargs["task_id"] == 42
        assert kwargs["conv_uid"] == "c2"


def test_assemble_scene_resources_none_ext_info():
    assert _assemble_scene_resources(None, "c1") == []
