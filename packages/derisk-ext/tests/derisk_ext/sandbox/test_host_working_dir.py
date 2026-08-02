"""场景空间独立沙箱目录(host_working_dir)测试。

设计:场景空间对话(大厅/任务)的沙箱工作目录指向空间家目录
(pilot/data/workspaces/<id>,与数据集目录同源),跨会话持久;
host_working_dir 未设置时保持原有的 session 目录嵌套行为。
"""
import os

from derisk.sandbox.providers.base import SessionConfig
from derisk_ext.sandbox.local.improved_provider import LocalSandboxConfig
from derisk_ext.sandbox.local.improved_runtime import ImprovedLocalSandboxSession


def _make_session(tmp_path, config: SessionConfig) -> ImprovedLocalSandboxSession:
    return ImprovedLocalSandboxSession(
        session_id="s1", config=config, runtime_dir=str(tmp_path / "rt")
    )


def test_host_working_dir_used_directly(tmp_path):
    """host_working_dir 设置时:物理工作目录=该真实路径,不嵌套 session 目录。"""
    host_dir = tmp_path / "workspaces" / "42"
    config = SessionConfig(working_dir="/ignored", host_working_dir=str(host_dir))
    session = _make_session(tmp_path, config)
    assert session._work_dir == str(host_dir)
    assert os.path.isdir(host_dir)  # 自动创建
    # 不嵌套:不在 session_dir 下
    assert not session._work_dir.startswith(session.session_dir)


def test_default_nested_behavior_unchanged(tmp_path):
    """未设置 host_working_dir:保持原有的 session 目录嵌套行为。"""
    config = SessionConfig(working_dir="/data/workspace")
    session = _make_session(tmp_path, config)
    expected = os.path.abspath(
        os.path.join(session.session_dir, "data/workspace")
    )
    assert session._work_dir == expected


def test_config_from_dict_carries_host_work_dir():
    cfg = LocalSandboxConfig.from_dict({"host_work_dir": "/tmp/ws/1"})
    assert cfg.host_work_dir == "/tmp/ws/1"
    sc = cfg.to_session_config()
    assert sc.host_working_dir == "/tmp/ws/1"


def test_config_default_host_work_dir_none():
    cfg = LocalSandboxConfig.from_dict({})
    assert cfg.host_work_dir is None
    assert cfg.to_session_config().host_working_dir is None


def test_workspace_sandbox_root(tmp_path, monkeypatch):
    """空间沙箱根目录:绝对路径 + files/db/runtime 子目录 + env 覆盖。"""
    from derisk_serve.workspace.dataset_service import workspace_sandbox_root

    monkeypatch.setenv("DERISK_WORKSPACE_SANDBOX_ROOT", str(tmp_path / "ws"))
    root = workspace_sandbox_root(7)
    assert root == os.path.abspath(str(tmp_path / "ws" / "7"))
    for sub in ("files", "db", "runtime"):
        assert os.path.isdir(os.path.join(root, sub))
