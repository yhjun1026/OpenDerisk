"""execute_sql 文件模式测试：显式开关 + 沙箱上传 + 三段返回。

验证：
- output_to_file=true 将全量结果上传沙箱，返回数据量(行数+大小)/样例/沙箱路径
- file_format 支持 csv(默认)/json
- 无沙箱时降级内联展示并标注 file_export_error
- 自动导出(>MAX_EXPORT_ROWS)走沙箱而非 temp 目录
- _resolve_sandbox_client / _export_to_file 单元行为
"""

import json
import re
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# 部分模块间接 import openai，mock 掉避免环境依赖
if "openai" not in sys.modules:
    sys.modules["openai"] = MagicMock()

from derisk.agent.tools.context import ToolContext
from derisk_serve.agent.capabilities.db.tools import _db_tools_impl


def _parse_sql_query_vis(text: str) -> dict:
    """从 ```d-sql-query\n{...}\n``` 围栏中解析 JSON。"""
    m = re.search(r"```d-sql-query\s*\n(.*?)\n```", text, re.DOTALL)
    assert m, f"d-sql-query VIS not found in output:\n{text}"
    return json.loads(m.group(1))


def _make_connector(rows_count: int, db_type: str = "sqlite") -> MagicMock:
    mock_connector = MagicMock()
    mock_connector.db_type = db_type
    mock_connector.dialect = db_type
    mock_connector.get_db_version.return_value = "3.0"
    columns = ["id", "name"]
    rows = [[i, f"name_{i}"] for i in range(1, rows_count + 1)]
    mock_connector.run.return_value = [columns] + rows
    return mock_connector


def _make_context(
    connector: MagicMock, sandbox_client=None, ds_id: int = 42
) -> ToolContext:
    db_resource = MagicMock()
    db_resource._connector = connector
    db_resource._datasource_id = ds_id
    ctx = ToolContext()
    ctx.set_resource("db_resource", db_resource)
    if sandbox_client is not None:
        ctx.set_resource("sandbox_client", sandbox_client)
    return ctx

def _make_sandbox_client(work_dir: str = "/home/user") -> MagicMock:
    client = MagicMock()
    client.work_dir = work_dir
    # 显式置空：MagicMock 会自动生成 truthy 属性，干扰 AFS 解析
    client.agent_file_system = None
    client.file.write = AsyncMock(return_value=MagicMock())
    return client


def _make_afs(download_url: str = "https://oss.example.com/dl/query.csv",
              preview_url=None) -> MagicMock:
    """模拟 AgentFileSystem，save_file_from_sandbox 返回带 download_url 的元数据。"""
    afs = MagicMock()
    metadata = MagicMock()
    metadata.download_url = download_url
    metadata.preview_url = preview_url
    afs.save_file_from_sandbox = AsyncMock(return_value=metadata)
    return afs


@pytest.fixture
def passthrough_masking(monkeypatch):
    """mask_run_result 透传，避免脱敏规则查库引入不确定性。"""

    def _passthrough(ds_id, columns, all_rows, session_id=None):
        return columns, all_rows, []

    try:
        import derisk_serve.sql_guard.masking as masking_mod

        monkeypatch.setattr(masking_mod, "mask_run_result", _passthrough)
    except Exception:
        pass


class TestResolveSandboxClient:
    def test_v2_resource(self):
        client = MagicMock()
        ctx = ToolContext()
        ctx.set_resource("sandbox_client", client)
        assert _db_tools_impl._resolve_sandbox_client(ctx, {}) is client

    def test_dict_context_manager(self):
        client = MagicMock()
        sm = MagicMock()
        sm.client = client
        got = _db_tools_impl._resolve_sandbox_client({"sandbox_manager": sm}, {})
        assert got is client

    def test_dict_context_config(self):
        client = MagicMock()
        ctx = {"config": {"sandbox_client": client}}
        assert _db_tools_impl._resolve_sandbox_client(ctx, {}) is client

    def test_none_returns_none(self):
        assert _db_tools_impl._resolve_sandbox_client(None, {}) is None

    def test_kwargs_fallback(self):
        client = MagicMock()
        got = _db_tools_impl._resolve_sandbox_client(
            None, {"sandbox_client": client}
        )
        assert got is client


class TestResolveAgentFileSystem:
    def test_from_sandbox_client(self):
        afs = MagicMock()
        client = MagicMock()
        client.agent_file_system = afs
        assert _db_tools_impl._resolve_agent_file_system(None, {}, client) is afs

    def test_from_v2_context_resource(self):
        afs = MagicMock()
        client = MagicMock()
        client.agent_file_system = None
        ctx = ToolContext()
        ctx.set_resource("agent_file_system", afs)
        assert _db_tools_impl._resolve_agent_file_system(ctx, {}, client) is afs

    def test_none_when_absent(self):
        client = MagicMock()
        client.agent_file_system = None
        ctx = ToolContext()
        assert _db_tools_impl._resolve_agent_file_system(ctx, {}, client) is None


class TestExportToFile:
    @pytest.mark.asyncio
    async def test_csv(self):
        client = _make_sandbox_client()
        ctx = ToolContext()
        ctx.set_resource("sandbox_client", client)
        info = await _db_tools_impl._export_to_file(
            columns=["id", "name"], rows=[[1, "a"]], db_name="t", sql="SELECT",
            file_format="csv", context=ctx, kwargs={},
        )
        assert info["format"] == "csv"
        assert info["path"].startswith("/home/user/exports/")
        assert info["path"].endswith(".csv")
        assert info["size"] > 0
        client.file.write.assert_awaited_once()
        call = client.file.write.call_args
        assert call.kwargs["path"] == info["path"]
        assert call.kwargs["overwrite"] is True

    @pytest.mark.asyncio
    async def test_json(self):
        client = _make_sandbox_client()
        ctx = ToolContext()
        ctx.set_resource("sandbox_client", client)
        info = await _db_tools_impl._export_to_file(
            columns=["id", "name"], rows=[[1, "a"]], db_name="t", sql="SELECT",
            file_format="json", context=ctx, kwargs={},
        )
        assert info["format"] == "json"
        assert info["path"].endswith(".json")
        call = client.file.write.call_args
        assert json.loads(call.kwargs["data"]) == [{"id": 1, "name": "a"}]

    @pytest.mark.asyncio
    async def test_no_sandbox_returns_none(self):
        info = await _db_tools_impl._export_to_file(
            columns=["id"], rows=[[1]], db_name="t", sql="SELECT",
            file_format="csv", context=None, kwargs={},
        )
        assert info is None

    @pytest.mark.asyncio
    async def test_with_afs_returns_download_url(self):
        client = _make_sandbox_client()
        afs = _make_afs(download_url="https://oss.example.com/dl/q.csv")
        ctx = ToolContext()
        ctx.set_resource("sandbox_client", client)
        ctx.set_resource("agent_file_system", afs)
        info = await _db_tools_impl._export_to_file(
            columns=["id", "name"], rows=[[1, "a"]], db_name="t", sql="SELECT",
            file_format="csv", context=ctx, kwargs={},
        )
        assert info["download_url"] == "https://oss.example.com/dl/q.csv"
        afs.save_file_from_sandbox.assert_awaited_once()
        call = afs.save_file_from_sandbox.call_args
        assert call.kwargs["sandbox_path"] == info["path"]
        assert call.kwargs["is_deliverable"] is False
        assert call.kwargs["tool_name"] == "execute_sql"

    @pytest.mark.asyncio
    async def test_without_afs_no_download_url(self):
        client = _make_sandbox_client()  # agent_file_system=None, 无 context AFS
        ctx = ToolContext()
        ctx.set_resource("sandbox_client", client)
        info = await _db_tools_impl._export_to_file(
            columns=["id"], rows=[[1]], db_name="t", sql="SELECT",
            file_format="csv", context=ctx, kwargs={},
        )
        assert info is not None
        assert info["download_url"] is None


class TestExecuteSqlFileMode:
    @pytest.mark.asyncio
    async def test_file_mode_csv(self, passthrough_masking):
        connector = _make_connector(rows_count=30)
        sandbox = _make_sandbox_client()
        ctx = _make_context(connector, sandbox_client=sandbox)
        result = await _db_tools_impl.execute_sql(
            db_name="test_db", sql="SELECT id, name FROM t",
            output_to_file=True, file_format="csv", context=ctx,
        )
        data = _parse_sql_query_vis(result)
        # 三段：数据量 / 样例 / 路径
        assert data["file_mode"] is True
        assert data["total_rows"] == 30  # 行数
        assert data["file_size"] > 0  # 大小
        assert data["file_format"] == "csv"
        path = data["file_path"]
        assert path.startswith("/home/user/exports/") and path.endswith(".csv")
        assert len(data["rows"]) <= 20  # 样例 <= SAMPLE_SIZE
        assert data["csv_file"] == data["file_path"]  # 向后兼容
        sandbox.file.write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_file_mode_json(self, passthrough_masking):
        connector = _make_connector(rows_count=5)
        sandbox = _make_sandbox_client()
        ctx = _make_context(connector, sandbox_client=sandbox)
        result = await _db_tools_impl.execute_sql(
            db_name="test_db", sql="SELECT id, name FROM t",
            output_to_file=True, file_format="json", context=ctx,
        )
        data = _parse_sql_query_vis(result)
        assert data["file_format"] == "json"
        assert data["file_path"].endswith(".json")
        call = sandbox.file.write.call_args
        assert isinstance(json.loads(call.kwargs["data"]), list)

    @pytest.mark.asyncio
    async def test_file_mode_no_sandbox_fallback(self, passthrough_masking):
        connector = _make_connector(rows_count=30)
        ctx = _make_context(connector, sandbox_client=None)  # 无沙箱
        result = await _db_tools_impl.execute_sql(
            db_name="test_db", sql="SELECT id, name FROM t",
            output_to_file=True, context=ctx,
        )
        data = _parse_sql_query_vis(result)
        assert "file_export_error" in data
        assert "file_path" not in data
        # 降级为分页展示，仍有数据
        assert data["total_rows"] == 30

    @pytest.mark.asyncio
    async def test_auto_export_large_result_uses_sandbox(self, passthrough_masking):
        # > MAX_EXPORT_ROWS(200)，output_to_file=False，应自动走沙箱而非 temp
        connector = _make_connector(rows_count=250)
        sandbox = _make_sandbox_client()
        ctx = _make_context(connector, sandbox_client=sandbox)
        result = await _db_tools_impl.execute_sql(
            db_name="test_db", sql="SELECT id, name FROM t",
            output_to_file=False, context=ctx,
        )
        data = _parse_sql_query_vis(result)
        assert data["file_path"].startswith("/home/user/exports/")
        assert data["file_size"] > 0
        sandbox.file.write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_file_mode_download_url_from_afs(self, passthrough_masking):
        """文件模式：AFS 可用时返回 download_url 供前端渲染下载链接。"""
        connector = _make_connector(rows_count=30)
        sandbox = _make_sandbox_client()
        afs = _make_afs(download_url="https://oss.example.com/dl/query.csv")
        ctx = _make_context(connector, sandbox_client=sandbox)
        ctx.set_resource("agent_file_system", afs)
        result = await _db_tools_impl.execute_sql(
            db_name="test_db", sql="SELECT id, name FROM t",
            output_to_file=True, file_format="csv", context=ctx,
        )
        data = _parse_sql_query_vis(result)
        # file_path 给 Agent，download_url 给前端，二者共存
        assert data["file_path"].startswith("/home/user/exports/")
        assert data["download_url"] == "https://oss.example.com/dl/query.csv"
        afs.save_file_from_sandbox.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_file_mode_no_afs_omits_download_url(self, passthrough_masking):
        """文件模式：AFS 不可用时不报错，仅缺 download_url。"""
        connector = _make_connector(rows_count=30)
        sandbox = _make_sandbox_client()  # 无 AFS
        ctx = _make_context(connector, sandbox_client=sandbox)
        result = await _db_tools_impl.execute_sql(
            db_name="test_db", sql="SELECT id, name FROM t",
            output_to_file=True, context=ctx,
        )
        data = _parse_sql_query_vis(result)
        assert data["file_mode"] is True
        assert "download_url" not in data
