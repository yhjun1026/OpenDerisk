"""Tests for Excel/CSV file datasets in the global datasource module.

验证全局入口(数据库模块添加连接):
  1. db_type_for_file 扩展名映射
  2. materialize_file_to_duckdb 多 sheet/csv
  3. rewrite_file_dataset_state: create/update 时 db_path 改写为物化后的 duckdb
  4. test_connection 走文件校验而非真实连接
"""
import io
import os

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from unittest.mock import MagicMock

from derisk_serve.datasource.api.schemas import DatasourceCreateRequest
from derisk_serve.datasource.manages.connector_manager import ConnectorManager
from derisk_serve.datasource.service.file_dataset import (
    db_type_for_file,
    materialize_file_to_duckdb,
    rewrite_file_dataset_state,
    validate_file_dataset,
)


def _xlsx_bytes(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


def test_db_type_for_file():
    assert db_type_for_file("a.xlsx") == "excel"
    assert db_type_for_file("a.XLS") == "excel"
    assert db_type_for_file("a.csv") == "csv"
    assert db_type_for_file("a.duckdb") is None
    assert db_type_for_file("a.exe") is None


def test_materialize_xlsx_multi_sheet(tmp_path):
    content = _xlsx_bytes({
        "orders": pd.DataFrame({"id": [1, 2]}),
        "users": pd.DataFrame({"uid": [1]}),
    })
    duckdb_path = str(tmp_path / "ds.duckdb")
    tables = materialize_file_to_duckdb(content, ".xlsx", duckdb_path)
    assert set(tables) == {"orders", "users"}
    engine = create_engine(f"duckdb:///{duckdb_path}")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM orders")).scalar() == 2


def test_rewrite_file_dataset_state(tmp_path):
    original = tmp_path / "sales_ab12cd34.xlsx"
    original.write_bytes(_xlsx_bytes({"orders": pd.DataFrame({"id": [1]})}))
    state = {"db_type": "excel", "db_path": str(original)}
    rewrite_file_dataset_state("excel", state)
    # db_path 指向物化后的 duckdb
    assert state["db_path"].endswith("sales_ab12cd34.duckdb")
    assert os.path.isfile(state["db_path"])
    engine = create_engine(f"duckdb:///{state['db_path']}")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM orders")).scalar() == 1


def test_rewrite_rejects_wrong_ext(tmp_path):
    original = tmp_path / "data.csv"
    original.write_bytes(b"id\n1\n")
    state = {"db_type": "excel", "db_path": str(original)}
    with pytest.raises(ValueError, match="expects one of"):
        rewrite_file_dataset_state("excel", state)


def test_rewrite_rejects_missing_file(tmp_path):
    state = {"db_type": "csv", "db_path": str(tmp_path / "nope.csv")}
    with pytest.raises(ValueError, match="not found"):
        rewrite_file_dataset_state("csv", state)


def test_rewrite_noop_for_non_file_dataset(tmp_path):
    state = {"db_type": "mysql", "db_path": ""}
    rewrite_file_dataset_state("mysql", state)
    assert state["db_path"] == ""


def test_test_connection_validates_file(tmp_path):
    original = tmp_path / "ok.xlsx"
    original.write_bytes(_xlsx_bytes({"t": pd.DataFrame({"id": [1]})}))
    manager = ConnectorManager(MagicMock())
    req = DatasourceCreateRequest(
        type="excel", params={"path": str(original)}, description="d"
    )
    assert manager.test_connection(req) is True

    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not an excel")
    req_bad = DatasourceCreateRequest(
        type="excel", params={"path": str(bad)}, description="d"
    )
    with pytest.raises(ValueError):
        manager.test_connection(req_bad)


def test_validate_file_dataset_csv(tmp_path):
    f = tmp_path / "r.csv"
    f.write_bytes(b"id,name\n1,a\n")
    validate_file_dataset("csv", str(f))
    with pytest.raises(ValueError, match="expects one of"):
        validate_file_dataset("excel", str(f))
