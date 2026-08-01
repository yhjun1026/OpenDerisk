"""asset_gate 单元测试:ECP 托管资产门禁(上下文保留 + 工具面硬门禁)。

设计:ECP 托管的资源以降级形态注入(schema 只读开放,数据查询走 ECP 工具);
execute_sql 经 ecp_gate_message 硬门禁拦截。覆盖:
- ecp_gate_message:无 agent/无 ECP 绑定/托管命中/未托管/fail-open
- build_managed_assets_text:降级使用纪律清单
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from derisk_serve.ecp.service import asset_gate


def _ref(ref_id: str, status: str = "active"):
    return SimpleNamespace(ref_id=ref_id, status=status)


def _patch_dao(monkeypatch, refs_by_ws: dict):
    """AssetRefDao().list(ws, kind) -> refs_by_ws.get(ws, [])"""
    dao = MagicMock()
    dao.list.side_effect = lambda ws, kind=None: refs_by_ws.get(ws, [])
    monkeypatch.setattr(asset_gate, "AssetRefDao", lambda: dao)
    return dao


def _agent_with_ecp(workspace_id: str = "default"):
    ecp_cap = SimpleNamespace(capability_id="ecp", _workspace_id=workspace_id)
    pack = SimpleNamespace(sub_resources=[ecp_cap])
    return SimpleNamespace(capability_pack=pack)


def _agent_without_ecp():
    pack = SimpleNamespace(sub_resources=[SimpleNamespace(capability_id="db:1")])
    return SimpleNamespace(capability_pack=pack)


class TestEcpGateMessage:
    def test_agent_none_passes(self, monkeypatch):
        dao = _patch_dao(monkeypatch, {"default": [_ref("1")]})
        assert asset_gate.ecp_gate_message(None, 1, "db") is None
        dao.list.assert_not_called()

    def test_datasource_id_none_passes(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1")]})
        assert asset_gate.ecp_gate_message(_agent_with_ecp(), None, "db") is None

    def test_agent_without_ecp_passes(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1")]})
        assert asset_gate.ecp_gate_message(_agent_without_ecp(), 1, "db") is None

    def test_managed_datasource_blocked(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1")]})
        msg = asset_gate.ecp_gate_message(_agent_with_ecp(), 1, "sqlite_test")
        assert msg is not None
        assert "⛔" in msg
        assert "sqlite_test (id=1)" in msg
        assert "execute_metric_query" in msg
        assert "execute_raw_sql" in msg
        assert "get_table_spec" in msg  # 只读 schema 不受限的说明

    def test_unmanaged_datasource_passes(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1")]})
        assert asset_gate.ecp_gate_message(_agent_with_ecp(), 2, "db") is None

    def test_inactive_ref_passes(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1", status="deprecated")]})
        assert asset_gate.ecp_gate_message(_agent_with_ecp(), 1, "db") is None

    def test_workspace_isolation(self, monkeypatch):
        # ds 1 只在 ws-other 托管;agent 绑的是 default → 放行
        _patch_dao(monkeypatch, {"ws-other": [_ref("1")]})
        assert asset_gate.ecp_gate_message(_agent_with_ecp("default"), 1, "db") is None

    def test_dao_failure_fail_open(self, monkeypatch):
        dao = MagicMock()
        dao.list.side_effect = RuntimeError("db down")
        monkeypatch.setattr(asset_gate, "AssetRefDao", lambda: dao)
        assert asset_gate.ecp_gate_message(_agent_with_ecp(), 1, "db") is None

    def test_capability_pack_missing_passes(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1")]})
        agent = SimpleNamespace(capability_pack=None)
        assert asset_gate.ecp_gate_message(agent, 1, "db") is None


class TestBuildManagedAssetsText:
    def test_manifest_with_db_ref(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1")]})
        monkeypatch.setattr(asset_gate, "_db_name_for", lambda rid: "sqlite_test")
        text = asset_gate.build_managed_assets_text("default")
        assert "ECP 托管资产" in text
        assert "降级使用" in text
        assert "sqlite_test (id=1)" in text
        assert "execute_sql" in text  # 直连已禁用声明
        assert "get_table_spec" in text  # 只读 schema 开放声明
        assert "execute_metric_query" in text

    def test_manifest_name_unresolvable(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": [_ref("1")]})
        monkeypatch.setattr(asset_gate, "_db_name_for", lambda rid: None)
        text = asset_gate.build_managed_assets_text("default")
        assert "id=1" in text

    def test_no_refs_returns_empty(self, monkeypatch):
        _patch_dao(monkeypatch, {"default": []})
        assert asset_gate.build_managed_assets_text("default") == ""

    def test_dao_failure_returns_empty(self, monkeypatch):
        dao = MagicMock()
        dao.list.side_effect = RuntimeError("db down")
        monkeypatch.setattr(asset_gate, "AssetRefDao", lambda: dao)
        assert asset_gate.build_managed_assets_text("default") == ""
