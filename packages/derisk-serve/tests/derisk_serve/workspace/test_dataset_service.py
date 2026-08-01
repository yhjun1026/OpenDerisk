"""P0 tests for workspace-owned datasets (Excel/CSV -> DuckDB datasource).

验证设计文档 docs/SCENARIO_WORKSPACE_ASSET_MANAGEMENT.md P0 闭环:
  1. DBType.excel/csv 是文件库类型
  2. connector 解析: excel/csv 委托 DuckDB 物理实现
  3. 上传 xlsx -> 沙箱目录 + duckdb 可查 + connect_config(owner_workspace_id)
     + workspace_resource 自动绑定
  4. 上传 csv -> 同上
  5. 同名重复上传 -> 复用同一 datasource(覆盖表)
  6. 名称消毒防路径穿越
  7. SchemaLearningService 在 excel 类型 datasource 上跑通 -> table_spec
"""
import io
import os
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from derisk.storage.metadata import db
from derisk_ext.datasource.schema import DBType
from derisk_ext.datasource.rdbms.conn_duckdb import DuckDbConnector
from derisk_ext.datasource.rdbms.conn_excel import (  # noqa: F401 注册子类
    CsvConnector,
    ExcelConnector,
)
from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao
from derisk_serve.datasource.manages.connector_manager import ConnectorManager
from derisk_serve.datasource.manages.db_spec_db import DbSpecDao  # noqa: F401 建表
from derisk_serve.datasource.manages.table_spec_db import TableSpecDao
from derisk_serve.datasource.service.learning_service import SchemaLearningService
from derisk_serve.workspace.dataset_service import (
    WorkspaceDatasetService,
    sanitize_asset_name,
)


@pytest.fixture
def setup(tmp_path):
    """init sqlite + dataset service(沙箱根指向 tmp)。"""
    db_path = tmp_path / "test.db"
    db.init_db(f"sqlite:///{db_path}")
    db.create_all()
    service = WorkspaceDatasetService(
        system_app=None, sandbox_root=str(tmp_path / "workspaces")
    )
    return service, tmp_path


def _xlsx_bytes(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


# ---------------- 1. DBType ----------------
def test_dbtype_excel_csv_are_file_dbs():
    assert DBType.of_db_type("excel").is_file_db()
    assert DBType.of_db_type("csv").is_file_db()
    assert DBType.Excel.value() == "excel"
    assert DBType.CSV.value() == "csv"


# ---------------- 2. connector 委托 ----------------
def test_connector_resolution_delegates_to_duckdb():
    manager = ConnectorManager(MagicMock())
    assert manager.get_cls_by_dbtype("excel") is ExcelConnector
    assert manager.get_cls_by_dbtype("csv") is CsvConnector
    assert issubclass(ExcelConnector, DuckDbConnector)
    assert issubclass(CsvConnector, DuckDbConnector)


def test_supported_types_no_duplicates_and_excel_csv_visible():
    """全局数据源表单: 子类遍历去重(excel/csv/openGauss 曾因遍历 bug 重复),
    excel/csv 作为文件库类型各出现一次(全局+空间双入口)。"""
    manager = ConnectorManager(MagicMock())
    manager.pkg_import()
    names = [t.name for t in manager.get_supported_types().types]
    assert len(names) == len(set(names)), f"duplicated types: {names}"
    assert "excel" in names
    assert "csv" in names
    # 分辨率不受影响(spec learning 依赖)
    assert manager.get_cls_by_dbtype("excel") is ExcelConnector
    assert manager.get_cls_by_dbtype("csv") is CsvConnector


# ---------------- 3. 上传 xlsx 全链路 ----------------
def test_import_xlsx_full_chain(setup):
    service, tmp_path = setup
    content = _xlsx_bytes({
        "订单": pd.DataFrame({"id": [1, 2], "amount": [10.5, 20.0]}),
        "users": pd.DataFrame({"uid": [1], "name": ["a"]}),
    })
    result = service.import_dataset(
        workspace_id=1,
        file_name="sales.xlsx",
        file_content=content,
        display_name="销售数据",
        trigger_learning=False,
    )

    # 沙箱目录
    root = tmp_path / "workspaces" / "1"
    for sub in ("files", "db", "runtime"):
        assert (root / sub).is_dir()
    assert (root / "files" / "sales.xlsx").is_file()

    # duckdb 可查(中文表名)
    engine = create_engine(f"duckdb:///{result['duckdb_path']}")
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT * FROM "订单"')).fetchall()
        assert len(rows) == 2
    assert set(result["tables"]) == {"订单", "users"}

    # connect_config: excel 类型 + owner_workspace_id
    entity = ConnectConfigDao().get_by_names("ws1_sales")
    assert entity is not None
    assert entity.db_type == "excel"
    assert entity.owner_workspace_id == 1
    assert entity.db_path == result["duckdb_path"]
    assert entity.comment == "销售数据"

    # workspace_resource 自动绑定
    bindings = [
        e for e in service._resource_dao.list_by_workspace(1, "data_source")
        if e.physical_ref == str(result["datasource_id"])
    ]
    assert len(bindings) == 1
    assert bindings[0].category == "scenario_specific"


# ---------------- 4. 上传 csv ----------------
def test_import_csv(setup):
    service, _ = setup
    csv_content = "id,name\n1,foo\n2,bar\n".encode("utf-8")
    result = service.import_dataset(
        workspace_id=2, file_name="ref.csv", file_content=csv_content,
        trigger_learning=False,
    )
    assert result["db_type"] == "csv"
    assert result["tables"] == ["data"]
    engine = create_engine(f"duckdb:///{result['duckdb_path']}")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM data")).scalar() == 2


# ---------------- 5. 重复上传复用 datasource ----------------
def test_reimport_reuses_datasource(setup):
    service, _ = setup
    csv_v1 = "id\n1\n".encode("utf-8")
    csv_v2 = "id\n1\n2\n3\n".encode("utf-8")
    r1 = service.import_dataset(1, "metrics.csv", csv_v1, trigger_learning=False)
    r2 = service.import_dataset(1, "metrics.csv", csv_v2, trigger_learning=False)
    assert r1["datasource_id"] == r2["datasource_id"]
    # 表已覆盖
    engine = create_engine(f"duckdb:///{r2['duckdb_path']}")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM data")).scalar() == 3
    # 绑定不重复
    bindings = service._resource_dao.list_by_workspace(1, "data_source")
    assert len(bindings) == 1


# ---------------- 6. 名称消毒 ----------------
def test_sanitize_asset_name():
    assert sanitize_asset_name("../etc/passwd") == "etc_passwd"
    assert sanitize_asset_name("...") == "dataset"
    assert sanitize_asset_name("销售 数据.xlsx") == "销售_数据_xlsx"
    assert sanitize_asset_name("a" * 100) == "a" * 64


def test_import_rejects_unknown_ext(setup):
    service, _ = setup
    with pytest.raises(ValueError, match="Unsupported file type"):
        service.import_dataset(1, "evil.exe", b"xx", trigger_learning=False)


# ---------------- 7. spec learning 跑通 ----------------
def test_schema_learning_on_excel_datasource(setup):
    service, _ = setup
    content = _xlsx_bytes({
        "orders": pd.DataFrame({"id": [1, 2, 3], "amount": [1.0, 2.0, 3.0]}),
    })
    result = service.import_dataset(
        workspace_id=1, file_name="orders.xlsx", file_content=content,
        trigger_learning=False,
    )
    ds_id = result["datasource_id"]

    connector_manager = ConnectorManager(MagicMock())
    learning = SchemaLearningService(connector_manager, MagicMock())
    spec = learning.learn_single_table(ds_id, "ws1_orders", "orders")

    assert spec["table_name"] == "orders"
    column_names = {c["name"] for c in spec["columns"]}
    assert {"id", "amount"} <= column_names
    assert spec["row_count"] == 3

    # table_spec 落库可查
    stored = TableSpecDao().get_by_datasource_and_table(ds_id, "orders")
    assert stored is not None
    assert stored["table_name"] == "orders"
