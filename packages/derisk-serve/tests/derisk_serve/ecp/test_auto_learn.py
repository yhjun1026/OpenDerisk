"""全自动 miss 学习测试:get_miss_report 工具 + 聚类共享函数 + cron 懒注册。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from derisk_serve.ecp.service import auto_learn
from derisk_serve.ecp.service.service import cluster_fallbacks
from derisk_serve.ecp.tools import ecp_tools


def _entry(sql, reasoning="缺指标", ds=1, ts="2026-08-01"):
    return SimpleNamespace(
        ts=ts, detail={"datasource_id": ds, "sql": sql, "reasoning": reasoning}
    )


class TestClusterFallbacksShared:
    def test_shared_with_service_and_tool(self):
        entries = [
            _entry("SELECT a FROM t WHERE x = 1"),
            _entry("select a from t where x=2"),
            _entry("SELECT b FROM t2"),
        ]
        clusters = cluster_fallbacks(entries)
        assert len(clusters) == 2
        assert clusters[0]["count"] == 2


class TestGetMissReportTool:
    @pytest.mark.asyncio
    async def test_min_count_filter(self, monkeypatch):
        entries = [
            _entry("SELECT a FROM t WHERE x = 1"),
            _entry("select a from t where x=2"),
            _entry("SELECT b FROM t2", reasoning="单次"),
        ]
        dao = MagicMock()
        dao.list.return_value = entries
        monkeypatch.setattr(ecp_tools, "OpLogDao", lambda: dao)
        out = json.loads(await ecp_tools.get_miss_report(min_count=2, limit=20))
        assert out["total_fallbacks"] == 3
        assert len(out["clusters"]) == 1  # 单次的被 min_count=2 过滤
        assert out["clusters"][0]["count"] == 2
        assert "hint" in out

    @pytest.mark.asyncio
    async def test_empty(self, monkeypatch):
        dao = MagicMock()
        dao.list.return_value = []
        monkeypatch.setattr(ecp_tools, "OpLogDao", lambda: dao)
        out = json.loads(await ecp_tools.get_miss_report())
        assert out["clusters"] == []


class TestEnsureAutoLearnCron:
    @pytest.mark.asyncio
    async def test_no_system_app_noop(self, monkeypatch):
        monkeypatch.setattr(
            "derisk._private.config.Config",
            lambda: SimpleNamespace(SYSTEM_APP=None),
        )
        await auto_learn.ensure_auto_learn_cron()  # 静默返回,不抛异常

    @pytest.mark.asyncio
    async def test_no_proposal_agent_noop(self, monkeypatch):
        monkeypatch.setattr(
            "derisk._private.config.Config",
            lambda: SimpleNamespace(SYSTEM_APP=MagicMock()),
        )
        monkeypatch.setattr(
            "derisk_serve.ecp.models.models.WorkspaceConfigDao",
            lambda: SimpleNamespace(
                get=lambda ws: SimpleNamespace(proposal_agent_id=None)
            ),
        )
        await auto_learn.ensure_auto_learn_cron()  # 静默返回

    @pytest.mark.asyncio
    async def test_registers_job_when_missing(self, monkeypatch):
        cron = MagicMock()
        cron.get_job = AsyncMock(return_value=None)
        cron.add_job = AsyncMock()
        app = MagicMock()
        app.get_component.return_value = cron
        monkeypatch.setattr(
            "derisk._private.config.Config",
            lambda: SimpleNamespace(SYSTEM_APP=app),
        )
        monkeypatch.setattr(
            "derisk_serve.ecp.models.models.WorkspaceConfigDao",
            lambda: SimpleNamespace(
                get=lambda ws: SimpleNamespace(proposal_agent_id="proposal-app-1")
            ),
        )
        await auto_learn.ensure_auto_learn_cron()
        cron.add_job.assert_called_once()
        job = cron.add_job.call_args[0][0]
        assert job.id == "ecp-auto-learn-default"
        assert job.payload.agent_id == "proposal-app-1"
        assert job.schedule.expr == "0 4 * * *"

    @pytest.mark.asyncio
    async def test_idempotent_when_job_exists(self, monkeypatch):
        cron = MagicMock()
        cron.get_job = AsyncMock(return_value=SimpleNamespace(id="ecp-auto-learn-default"))
        cron.add_job = AsyncMock()
        app = MagicMock()
        app.get_component.return_value = cron
        monkeypatch.setattr(
            "derisk._private.config.Config",
            lambda: SimpleNamespace(SYSTEM_APP=app),
        )
        monkeypatch.setattr(
            "derisk_serve.ecp.models.models.WorkspaceConfigDao",
            lambda: SimpleNamespace(
                get=lambda ws: SimpleNamespace(proposal_agent_id="proposal-app-1")
            ),
        )
        await auto_learn.ensure_auto_learn_cron()
        cron.add_job.assert_not_called()
