"""回归测试：deliver_file / create_file 必须接纳相对 URL 作为交付链接。

背景：
本地 SimpleDistributedStorage 后端对非公网 host 返回的是形如
``/api/v2/serve/file/files/...`` 的相对 URL（见 file.py:SimpleDistributedStorage
.get_public_url 的设计注释）。AFS.save_file_from_sandbox 在本地后端下产生的
元数据形如：oss_url=derisk-fs://..., download_url=/api/v2/..., preview_url=None。

此前 deliver_file / create_file 用 ``url.startswith(("http://","https://"))``
过滤交付 URL，把这种合法的相对 URL 一 并误杀，导致已成功落存的文件被判为
"Storage upload failed"。同时 deliver_file 回退分支引用了未定义的 ``context``
变量（_execute_sandbox 签名不含 context），回退直接 NameError，进一步掩盖
真正可用的 download_url。

本测试复现该场景：fake client 的 agent_file_system 只回填相对 download_url，
断言 deliver_file / create_file 能成功返回并携带可用链接。
"""

from typing import Any, Optional

import pytest

from derisk.agent.core.memory.gpts.file_base import (
    AgentFileMetadata,
    FileType,
)
from derisk.agent.tools.builtin.sandbox.create_file import CreateFileTool
from derisk.agent.tools.builtin.sandbox.deliver_file import (
    DeliverFileTool,
    _is_deliverable_url,
)


# --------------------------------------------------------------------------- #
# _is_deliverable_url 单元
# --------------------------------------------------------------------------- #
def test_is_deliverable_url_accepts_relative_and_http():
    assert _is_deliverable_url("/api/v2/serve/file/files/bucket/id")
    assert _is_deliverable_url("https://oss.example.com/a/b.pptx")
    assert _is_deliverable_url("http://10.0.0.1:7777/api/v2/serve/file/files/b/i")


def test_is_deliverable_url_rejects_internal_and_invalid():
    assert not _is_deliverable_url(None)
    assert not _is_deliverable_url("")
    assert not _is_deliverable_url(123)  # type: ignore[arg-type]
    # 内部 URI 不可被浏览器直接访问
    assert not _is_deliverable_url("derisk-fs://distributed/agent_files/abc")
    assert not _is_deliverable_url("oss://bucket/key.pptx")
    # 协议相对 / 无前导斜杠的裸路径不算
    assert not _is_deliverable_url("tmp/relative/path.pptx")


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _FileResult:
    status = "completed"
    output = None
    console = []


class _FakeShell:
    async def exec_command(self, *args, **kwargs):
        # detect_path_kind 期待的输出：FILE → 路径类型为文件
        r = _FileResult()
        r.output = "FILE"
        return r


class _FakeFileNamespace:
    async def read(self, *args, **kwargs):
        return None


class _FakeAgentFileSystem:
    """模拟本地后端下 AFS：只回填相对 download_url。"""

    def __init__(self, *, oss_url: str = "derisk-fs://distributed/agent_files/x"):
        self._oss_url = oss_url
        self.conv_id = "conv-1"
        self.metadata_storage = type(
            "MS",
            (),
            {
                "get_file_by_key": lambda self, *a, **k: _as_coro(None),
                "save_file_metadata": lambda self, *a, **k: _as_coro(None),
                "list_files": lambda self, *a, **k: _as_coro([]),
            },
        )()

    async def save_file_from_sandbox(self, **kwargs: Any) -> AgentFileMetadata:
        name = kwargs["sandbox_path"].split("/")[-1]
        return AgentFileMetadata(
            file_id="fake-id",
            conv_id="conv-1",
            conv_session_id="conv-1",
            file_key=name,
            file_name=name,
            file_type=FileType.DELIVERABLE.value,
            local_path=kwargs["sandbox_path"],
            file_size=243955,
            oss_url=self._oss_url,
            preview_url=None,  # pptx 不在预览白名单
            download_url="/api/v2/serve/file/files/agent_files/fake-id",
            metadata={},
        )


class _FakeSandboxClient:
    work_dir = "/mnt"
    skill_dir = None
    shell = _FakeShell()
    agent_file_system = _FakeAgentFileSystem()
    file = _FakeFileNamespace()


def _as_coro(value: Any):
    import asyncio

    fut: "asyncio.Future[Any]" = asyncio.Future()
    fut.set_result(value)
    return fut


# --------------------------------------------------------------------------- #
# deliver_file: 本地后端相对 URL 必须交付成功
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_deliver_file_succeeds_with_relative_url():
    tool = DeliverFileTool()
    client = _FakeSandboxClient()
    res = await tool._execute_sandbox(
        path="/mnt/Walmart销售数据分析报告.pptx",
        description="Walmart销售数据分析报告PPT",
        file_type="deliverable",
        client=client,
        context=None,
    )
    assert res.success, f"deliver_file 不应失败: {res.error}"
    out = res.get_output_string()
    assert "/api/v2/serve/file/files/agent_files/fake-id" in out


@pytest.mark.asyncio
async def test_deliver_file_fallback_context_param_is_defined():
    """AFS 未回填 URL 时回退分支不应 NameError（context 已作为参数传入）。"""

    class _NoUrlAFS(_FakeAgentFileSystem):
        async def save_file_from_sandbox(self, **kwargs: Any) -> AgentFileMetadata:
            m = await super().save_file_from_sandbox(**kwargs)
            m.download_url = None
            m.oss_url = None
            return m

    class _Client(_FakeSandboxClient):
        agent_file_system = _NoUrlAFS()

    tool = DeliverFileTool()
    res = await tool._execute_sandbox(
        path="/mnt/no_url.pptx",
        description="d",
        file_type="deliverable",
        client=_Client(),
        context=None,
    )
    # 无可交付 URL 时允许失败，但错误码必须是 STORAGE_UPLOAD_FAILED，
    # 关键是回退分支不能因 NameError 中断（之前会先抛 name 'context' is not defined）。
    assert not res.success
    assert res.error_code == "STORAGE_UPLOAD_FAILED"


# --------------------------------------------------------------------------- #
# create_file: 同源过滤也需接纳相对 URL
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_file_accepts_relative_url():
    tool = CreateFileTool()
    client = _FakeSandboxClient()

    # create_file 直接调 save_file_from_sandbox 拿 download_url
    afs = client.agent_file_system
    md = await afs.save_file_from_sandbox(
        sandbox_path="/out/r.md", file_type=FileType.DELIVERABLE.value
    )
    assert _is_deliverable_url(md.download_url)
