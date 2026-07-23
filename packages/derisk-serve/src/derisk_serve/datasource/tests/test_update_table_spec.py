"""Tests for SchemaLearningService.update_table_spec.

Covers the single-table edit endpoint's core logic: updating table
comment / group name, editing per-column fields while preserving
non-editable fields (e.g. distribution), and regenerating the
database-level spec summary so it stays in sync.
"""
import json
from unittest.mock import MagicMock

import pytest

from derisk.storage.metadata import db
from derisk_serve.datasource.manages.connect_config_db import ConnectConfigEntity
from derisk_serve.datasource.service.learning_service import (
    SchemaLearningService,
)


@pytest.fixture
def service(tmp_path):
    db_path = tmp_path / "test_update_spec.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    return SchemaLearningService(
        connector_manager=MagicMock(), system_app=None
    )


def _seed(service, datasource_id=1):
    """Seed a connect_config row (id=1) and a table_spec for 'users'."""
    with db.session() as session:
        session.add(ConnectConfigEntity(db_type="sqlite", db_name="test_db"))
        session.commit()

    columns = [
        {
            "name": "id",
            "type": "INTEGER",
            "nullable": False,
            "default": None,
            "comment": "",
            "pk": True,
        },
        {
            "name": "status",
            "type": "VARCHAR(20)",
            "nullable": True,
            "default": None,
            "comment": "",
            "pk": False,
            "distribution": {
                "type": "enum",
                "values": ["active", "inactive"],
            },
        },
    ]
    service._table_spec_dao.upsert(datasource_id, "users", {
        "table_comment": "old comment",
        "row_count": 100,
        "columns_json": json.dumps(columns, ensure_ascii=False),
        "indexes_json": "[]",
        "foreign_keys_json": None,
        "sample_data_json": None,
        "create_ddl": "CREATE TABLE users (id INT, status VARCHAR(20))",
        "group_name": "default",
    })
    return datasource_id


def test_update_table_comment_and_group(service):
    ds_id = _seed(service)
    result = service.update_table_spec(ds_id, "users", {
        "table_comment": "new comment",
        "group_name": "auth",
    })
    assert result is not None
    assert result["table_comment"] == "new comment"
    assert result["group_name"] == "auth"


def test_update_column_comment_preserves_distribution(service):
    ds_id = _seed(service)
    result = service.update_table_spec(ds_id, "users", {
        "columns": [{"name": "status", "comment": "用户状态"}],
    })
    assert result is not None
    status_col = next(c for c in result["columns"] if c["name"] == "status")
    assert status_col["comment"] == "用户状态"
    # distribution must be preserved (not an editable field)
    assert status_col.get("distribution") == {
        "type": "enum",
        "values": ["active", "inactive"],
    }
    # untouched column stays the same
    id_col = next(c for c in result["columns"] if c["name"] == "id")
    assert id_col["pk"] is True


def test_update_column_structure(service):
    ds_id = _seed(service)
    result = service.update_table_spec(ds_id, "users", {
        "columns": [
            {"name": "status", "type": "VARCHAR(50)", "nullable": False},
        ],
    })
    status_col = next(c for c in result["columns"] if c["name"] == "status")
    assert status_col["type"] == "VARCHAR(50)"
    assert status_col["nullable"] is False


def test_update_regenerates_db_spec_summary(service):
    ds_id = _seed(service)
    service.update_table_spec(ds_id, "users", {"table_comment": "synced summary"})
    db_spec = service._db_spec_dao.get_by_datasource_id(ds_id)
    assert db_spec is not None
    spec_content = db_spec["spec_content"]
    entry = next(e for e in spec_content if e["table_name"] == "users")
    assert entry["summary"] == "synced summary"
    assert db_spec["status"] == "ready"


def test_update_nonexistent_returns_none(service):
    result = service.update_table_spec(1, "no_such_table", {"table_comment": "x"})
    assert result is None


def test_update_no_op_when_empty(service):
    ds_id = _seed(service)
    result = service.update_table_spec(ds_id, "users", {})
    assert result is not None
    assert result["table_comment"] == "old comment"


# ------------------------------------------------------------------
# enrich_table_descriptions (Part B: LLM-generated descriptions)
# ------------------------------------------------------------------


def test_enrich_fills_empty_comments_preserves_existing(service, monkeypatch):
    ds_id = _seed(service)
    monkeypatch.setattr(
        service,
        "_generate_table_and_column_comments",
        lambda **kw: {
            "table_comment": "用户表",
            "columns": [
                {"name": "id", "comment": "主键ID"},
                {"name": "status", "comment": "用户状态"},
            ],
        },
    )
    result = service.enrich_table_descriptions(ds_id, "users", force=False)
    # existing non-empty table comment preserved (force=False)
    assert result["table_comment"] == "old comment"
    # empty column comments filled in
    id_col = next(c for c in result["columns"] if c["name"] == "id")
    assert id_col["comment"] == "主键ID"
    status_col = next(c for c in result["columns"] if c["name"] == "status")
    assert status_col["comment"] == "用户状态"
    # distribution preserved
    assert status_col.get("distribution") == {
        "type": "enum",
        "values": ["active", "inactive"],
    }


def test_enrich_force_overwrites(service, monkeypatch):
    ds_id = _seed(service)
    monkeypatch.setattr(
        service,
        "_generate_table_and_column_comments",
        lambda **kw: {
            "table_comment": "用户表",
            "columns": [
                {"name": "id", "comment": "主键ID"},
                {"name": "status", "comment": "用户状态"},
            ],
        },
    )
    result = service.enrich_table_descriptions(ds_id, "users", force=True)
    assert result["table_comment"] == "用户表"
    id_col = next(c for c in result["columns"] if c["name"] == "id")
    assert id_col["comment"] == "主键ID"


def test_enrich_llm_unavailable_returns_unchanged(service, monkeypatch):
    ds_id = _seed(service)
    monkeypatch.setattr(
        service, "_generate_table_and_column_comments", lambda **kw: None
    )
    result = service.enrich_table_descriptions(ds_id, "users", force=True)
    assert result is not None
    assert result["table_comment"] == "old comment"


def test_enrich_nonexistent_returns_none(service):
    result = service.enrich_table_descriptions(1, "no_such", force=True)
    assert result is None


def test_enrich_regenerates_db_spec(service, monkeypatch):
    ds_id = _seed(service)
    monkeypatch.setattr(
        service,
        "_generate_table_and_column_comments",
        lambda **kw: {
            "table_comment": "enriched summary",
            "columns": [],
        },
    )
    service.enrich_table_descriptions(ds_id, "users", force=True)
    db_spec = service._db_spec_dao.get_by_datasource_id(ds_id)
    assert db_spec is not None
    entry = next(
        e for e in db_spec["spec_content"] if e["table_name"] == "users"
    )
    assert entry["summary"] == "enriched summary"


def test_parse_llm_json_strips_code_fence(service):
    text = '```json\n{"table_comment": "x", "columns": []}\n```'
    assert service._parse_llm_json(text) == {
        "table_comment": "x",
        "columns": [],
    }


def test_parse_llm_json_extracts_from_text(service):
    text = "结果如下: {\"table_comment\": \"y\"} 完"
    assert service._parse_llm_json(text) == {"table_comment": "y"}


def test_parse_llm_json_invalid(service):
    assert service._parse_llm_json("no json here") is None
    assert service._parse_llm_json("") is None
