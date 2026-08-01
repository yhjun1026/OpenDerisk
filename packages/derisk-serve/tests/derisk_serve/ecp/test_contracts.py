"""contracts 单元测试:payload 契约单一事实来源 + confirm 晋升门禁。

契约设计:
- validate_payload: proposal 级(结构最小集) / executable 级(可执行全集)
- normalize_payload: 扁平形态机械升级为契约形态(幂等)
- Service.confirm: executable 级校验不合格拒绝确认(机器背书人类确认)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from derisk_serve.ecp.service.contracts import normalize_payload, validate_payload
from derisk_serve.ecp.service.service import Service


# ------------------------------------------------------------------ validate
class TestValidatePayload:
    # ---- entity ----
    def test_entity_ok(self):
        p = {"binding": {"table": "t", "datasource_id": 1}}
        assert validate_payload("entity", p) == []

    def test_entity_missing_binding(self):
        problems = validate_payload("entity", {"name": "x"})
        assert any("binding" in m for m in problems)

    def test_entity_missing_datasource_id(self):
        problems = validate_payload("entity", {"binding": {"table": "t"}})
        assert any("datasource_id" in m for m in problems)

    def test_entity_proposal_level_allows_no_datasource(self):
        # proposal 级只要求 binding.table,datasource_id 可后续补
        assert validate_payload("entity", {"binding": {"table": "t"}}, level="proposal") == []

    # ---- metric ----
    def test_metric_ok(self):
        p = {"entity": "ent.a", "expression": "SUM(x)"}
        assert validate_payload("metric", p) == []

    def test_metric_missing_entity(self):
        problems = validate_payload("metric", {"expression": "SUM(x)"})
        assert any("entity" in m for m in problems)

    def test_metric_missing_expression(self):
        problems = validate_payload("metric", {"entity": "ent.a"}, level="proposal")
        assert any("expression" in m for m in problems)

    # ---- dimension ----
    def test_dimension_ok(self):
        p = {"column": "c", "values": [{"label": "甲", "codes": ["1"]}]}
        assert validate_payload("dimension", p) == []

    def test_dimension_no_values_ok(self):
        # values 可缺省(纯 group_by 维度);存在则每项需 codes
        assert validate_payload("dimension", {"column": "c"}) == []

    def test_dimension_value_missing_codes(self):
        p = {"column": "c", "values": [{"label": "甲", "code": "1"}]}
        problems = validate_payload("dimension", p)
        assert any("codes" in m for m in problems)

    # ---- relation ----
    def test_relation_ok(self):
        assert validate_payload("relation", {"from": "a", "to": "b"}) == []

    def test_relation_missing_endpoint(self):
        problems = validate_payload("relation", {"from": "a"})
        assert any("to" in m for m in problems)

    # ---- 通用 ----
    def test_payload_not_dict(self):
        assert validate_payload("metric", "not-a-dict") != []

    def test_unknown_type_no_rules(self):
        assert validate_payload("unknown_type", {}) == []


# ----------------------------------------------------------------- normalize
class TestNormalizePayload:
    def test_entity_flat_to_binding(self):
        p = normalize_payload("entity", {"name": "门店", "table_name": "t", "datasource_id": 1})
        assert p["binding"]["table"] == "t"
        assert p["binding"]["datasource_id"] == 1
        assert p["binding"]["kind"] == "db"
        assert "table_name" not in p and "datasource_id" not in p

    def test_entity_binding_preserved(self):
        p = normalize_payload(
            "entity", {"binding": {"table": "t", "datasource_id": 2, "kind": "db"}}
        )
        assert p["binding"]["datasource_id"] == 2

    def test_entity_datasource_id_param_priority(self):
        p = normalize_payload(
            "entity", {"table_name": "t", "datasource_id": 9}, datasource_id=3
        )
        assert p["binding"]["datasource_id"] == 3

    def test_dimension_code_to_codes(self):
        p = normalize_payload(
            "dimension",
            {"column": "c", "values": [{"label": "甲", "code": "1"}, {"label": "乙", "codes": ["2"]}]},
        )
        assert p["values"][0]["codes"] == ["1"]
        assert "code" not in p["values"][0]
        assert p["values"][1]["codes"] == ["2"]

    def test_metric_grain_scalar_to_list(self):
        p = normalize_payload("metric", {"entity": "e", "expression": "SUM(x)", "grain": "Store"})
        assert p["grain"] == ["Store"]

    def test_idempotent(self):
        once = normalize_payload("entity", {"table_name": "t", "datasource_id": 1})
        twice = normalize_payload("entity", once)
        assert once == twice

    def test_non_dict_passthrough(self):
        assert normalize_payload("metric", "raw") == "raw"


# -------------------------------------------------------------- confirm 门禁
def _make_service(confirmed: bool, proposed_vo=None):
    svc = Service.__new__(Service)
    svc._confirmer_dao = MagicMock()
    svc._confirmer_dao.is_confirmer.return_value = confirmed
    svc._object_dao = MagicMock()
    svc._cache_dao = MagicMock()
    svc._oplog_dao = MagicMock()
    if proposed_vo is not None:
        svc._object_dao.get_version.return_value = proposed_vo
    return svc


class TestConfirmGate:
    def test_confirm_invalid_payload_rejected(self):
        vo = SimpleNamespace(
            obj_type="metric", payload={"expression": "SUM(x)"}, evidence=None
        )  # 缺 entity
        svc = _make_service(True, vo)
        with pytest.raises(ValueError, match="可执行契约"):
            svc.confirm("mtr.x", 1, "user0")

    def test_confirm_valid_payload_passes(self):
        vo = SimpleNamespace(
            obj_type="metric",
            payload={"entity": "ent.a", "expression": "SUM(x)"},
            evidence=None,
        )
        svc = _make_service(True, vo)
        svc._object_dao.confirm_version.return_value = SimpleNamespace(
            id="mtr.x", version=1
        )
        svc._cache_dao.invalidate_referencing.return_value = 0
        result = svc.confirm("mtr.x", 1, "user0")
        assert result.id == "mtr.x"
        svc._object_dao.confirm_version.assert_called_once()

    def test_confirm_edited_payload_invalid_rejected(self):
        vo = SimpleNamespace(obj_type="entity", payload={}, evidence=None)
        svc = _make_service(True, vo)
        with pytest.raises(ValueError, match="可执行契约"):
            svc.confirm("ent.x", 1, "user0", edited_payload={"name": "x"})

    def test_confirm_edited_payload_valid_passes(self):
        vo = SimpleNamespace(obj_type="entity", payload={}, evidence=None)
        svc = _make_service(True, vo)
        svc._object_dao.create_confirmed_version.return_value = SimpleNamespace(
            id="ent.x", version=2
        )
        svc._cache_dao.invalidate_referencing.return_value = 0
        result = svc.confirm(
            "ent.x", 1, "user0",
            edited_payload={"binding": {"table": "t", "datasource_id": 1}},
        )
        assert result.version == 2

    def test_confirm_non_confirmer_still_rejected(self):
        svc = _make_service(False)
        with pytest.raises(PermissionError):
            svc.confirm("mtr.x", 1, "intruder")


# ------------------------------------------------------- admin 契约检查/修复
class TestAdminContractOps:
    def _svc_with_catalog(self, objects):
        """objects: [(id, obj_type, version, payload)]"""
        svc = Service.__new__(Service)
        svc._object_dao = MagicMock()
        svc._cache_dao = MagicMock()
        svc._oplog_dao = MagicMock()
        svc._object_dao.list_catalog.return_value = [
            SimpleNamespace(id=o[0], obj_type=o[1]) for o in objects
        ]
        by_id = {o[0]: SimpleNamespace(
            id=o[0], obj_type=o[1], version=o[2], payload=o[3], evidence=None
        ) for o in objects}
        svc._object_dao.get_confirmed.side_effect = lambda oid, ws: by_id.get(oid)
        return svc

    def test_contract_check_finds_problems(self):
        svc = self._svc_with_catalog([
            ("mtr.ok", "metric", 1, {"entity": "ent.a", "expression": "SUM(x)"}),
            ("mtr.bad", "metric", 1, {"expression": "SUM(x)"}),  # 缺 entity
        ])
        result = svc.contract_check()
        assert result["total"] == 2
        assert result["non_compliant_count"] == 1
        assert result["non_compliant"][0]["id"] == "mtr.bad"
        assert any("entity" in p for p in result["non_compliant"][0]["problems"])

    def test_normalize_fixes_and_writes_new_version(self):
        # 扁平 entity(normalize 可修复)
        svc = self._svc_with_catalog([
            ("ent.x", "entity", 1, {"name": "x", "table_name": "t", "datasource_id": 1}),
        ])
        svc._object_dao.create_confirmed_version.return_value = SimpleNamespace(
            id="ent.x", version=2
        )
        result = svc.normalize_confirmed()
        assert result["fixed"] == [{"id": "ent.x", "version": 2}]
        assert result["skipped"] == []
        # 写入的是 normalize 后的契约形态
        call_payload = svc._object_dao.create_confirmed_version.call_args[1]["payload"]
        assert call_payload["binding"]["datasource_id"] == 1

    def test_normalize_skips_unfixable(self):
        # 缺 entity 引用(normalize 无法补)
        svc = self._svc_with_catalog([
            ("mtr.bad", "metric", 1, {"expression": "SUM(x)"}),
        ])
        result = svc.normalize_confirmed()
        assert result["fixed"] == []
        assert result["skipped"][0]["id"] == "mtr.bad"
        svc._object_dao.create_confirmed_version.assert_not_called()

    def test_normalize_noop_when_all_compliant(self):
        svc = self._svc_with_catalog([
            ("mtr.ok", "metric", 1, {"entity": "ent.a", "expression": "SUM(x)"}),
        ])
        result = svc.normalize_confirmed()
        assert result["fixed"] == [] and result["skipped"] == []


# ------------------------------------------------- entity_bindings 漂移与自愈
class TestEntityBindingsNormalize:
    def test_entity_bindings_to_entity(self):
        """提案 agent 漂移形态 entity_bindings(数组) → entity(单值)。"""
        p = normalize_payload(
            "metric",
            {"expression": "SUM(x)", "entity_bindings": ["ent.store"]},
        )
        assert p["entity"] == "ent.store"

    def test_existing_entity_not_overwritten(self):
        p = normalize_payload(
            "metric",
            {"expression": "SUM(x)", "entity": "ent.a", "entity_bindings": ["ent.b"]},
        )
        assert p["entity"] == "ent.a"

    def test_confirm_self_heals_entity_bindings(self):
        """confirm 时归一化自愈:entity_bindings 提案确认后变契约形态新版本。"""
        vo = SimpleNamespace(
            obj_type="metric",
            payload={"expression": "SUM(x)", "entity_bindings": ["ent.store"]},
            evidence=None,
        )
        svc = _make_service(True, vo)
        svc._object_dao.create_confirmed_version.return_value = SimpleNamespace(
            id="mtr.x", version=2
        )
        svc._cache_dao.invalidate_referencing.return_value = 0
        result = svc.confirm("mtr.x", 1, "user0")
        assert result.version == 2
        call_payload = svc._object_dao.create_confirmed_version.call_args[1]["payload"]
        assert call_payload["entity"] == "ent.store"
        # confirm_version(纯状态翻转)不应被调用——走了归一化新版本路径
        svc._object_dao.confirm_version.assert_not_called()

    def test_confirm_compliant_uses_plain_path(self):
        """payload 本就合规 → 走纯状态翻转,不产生额外版本。"""
        vo = SimpleNamespace(
            obj_type="metric",
            payload={"entity": "ent.a", "expression": "SUM(x)"},
            evidence=None,
        )
        svc = _make_service(True, vo)
        svc._object_dao.confirm_version.return_value = SimpleNamespace(
            id="mtr.x", version=1
        )
        svc._cache_dao.invalidate_referencing.return_value = 0
        svc.confirm("mtr.x", 1, "user0")
        svc._object_dao.confirm_version.assert_called_once()
        svc._object_dao.create_confirmed_version.assert_not_called()
