"""Shared helpers for Excel/CSV file datasets.

Excel/CSV files become first-class datasources by materializing them into
DuckDB files (one dataset = one DuckDB file, sheet = table). Used by both
creation entries:

- Global datasource module (Service.create/update): uploaded file is
  materialized next to the original and `db_path` is rewritten to the
  DuckDB file, so spec learning and SQL tooling work unchanged.
- Scene workspace (WorkspaceDatasetService): materialized inside the
  workspace sandbox directory with `owner_workspace_id` set.
"""

import io
import os
import re
import threading
from typing import Any, Dict, List, Optional

from derisk.util.pd_utils import clean_dataframe_types

# db_type -> accepted file extensions for file datasets.
FILE_DATASET_EXTS: Dict[str, set] = {
    "excel": {".xlsx", ".xls"},
    "csv": {".csv"},
}

# Per-file write locks: DuckDB allows a single writer, so concurrent
# materialization into the same backing file is serialized here.
_file_locks: Dict[str, threading.Lock] = {}
_file_locks_guard = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    with _file_locks_guard:
        return _file_locks.setdefault(path, threading.Lock())


def db_type_for_file(file_name: str) -> Optional[str]:
    """Return the file-dataset db_type for a file name, or None."""
    ext = os.path.splitext(file_name)[1].lower()
    for db_type, exts in FILE_DATASET_EXTS.items():
        if ext in exts:
            return db_type
    return None


def sanitize_asset_name(name: str, fallback: str = "dataset") -> str:
    """Sanitize a user-supplied name into a safe identifier.

    Prevents path traversal and keeps the name usable as a file name,
    table name and db_name component.
    """
    name = re.sub(r"[^\w\-]+", "_", name).strip("._-")
    return name[:64] or fallback


def materialize_file_to_duckdb(
    file_content: bytes, ext: str, duckdb_path: str
) -> List[str]:
    """Load an Excel/CSV file and write its sheets as tables into DuckDB.

    Uses the duckdb driver directly (register + CREATE OR REPLACE TABLE)
    instead of pandas.to_sql: the duckdb_engine reflection used by
    if_exists="replace" fails on existing files (pg_catalog queries).

    Returns:
        List of created table names.
    """
    import duckdb
    import pandas as pd

    ext = ext.lower()
    if ext in FILE_DATASET_EXTS["excel"]:
        sheets: Dict[str, Any] = pd.read_excel(io.BytesIO(file_content), sheet_name=None)
    elif ext in FILE_DATASET_EXTS["csv"]:
        sheets = {"data": pd.read_csv(io.BytesIO(file_content))}
    else:
        raise ValueError(
            f"Unsupported file type '{ext}', expected one of "
            f"{sorted(FILE_DATASET_EXTS['excel'] | FILE_DATASET_EXTS['csv'])}"
        )
    if not sheets:
        raise ValueError("The uploaded file contains no data sheets")

    tables: List[str] = []
    lock = _lock_for(duckdb_path)
    with lock:
        con = duckdb.connect(duckdb_path)
        try:
            for sheet_name, df in sheets.items():
                table = sanitize_asset_name(str(sheet_name), fallback="sheet")
                if table in tables:
                    table = f"{table}_{len(tables)}"
                df.columns = [str(c).strip() for c in df.columns]
                df = clean_dataframe_types(df)
                con.register("_incoming_df", df)
                try:
                    con.execute(
                        f'CREATE OR REPLACE TABLE "{table}" '
                        f"AS SELECT * FROM _incoming_df"
                    )
                finally:
                    con.unregister("_incoming_df")
                tables.append(table)
        finally:
            con.close()
    return tables


def rewrite_file_dataset_state(db_type: str, persisted_state: Dict[str, Any]) -> None:
    """Materialize an uploaded Excel/CSV into DuckDB and rewrite db_path.

    Called on datasource create/update for file-dataset types: the incoming
    `db_path` points at the uploaded original (xlsx/csv); after this call it
    points at the materialized DuckDB file next to the original.
    """
    if db_type not in FILE_DATASET_EXTS:
        return
    original_path = persisted_state.get("db_path")
    if not original_path:
        raise ValueError(f"{db_type} dataset requires an uploaded file path")
    if not os.path.isabs(original_path):
        original_path = os.path.abspath(original_path)
    ext = os.path.splitext(original_path)[1].lower()
    if ext not in FILE_DATASET_EXTS[db_type]:
        raise ValueError(
            f"'{db_type}' dataset expects one of "
            f"{sorted(FILE_DATASET_EXTS[db_type])}, got '{ext}'"
        )
    if not os.path.isfile(original_path):
        raise ValueError(f"Uploaded file not found: {original_path}")

    duckdb_path = os.path.splitext(original_path)[0] + ".duckdb"
    with open(original_path, "rb") as f:
        content = f.read()
    materialize_file_to_duckdb(content, ext, duckdb_path)
    persisted_state["db_path"] = duckdb_path


def validate_file_dataset(db_type: str, file_path: str) -> None:
    """Validate that a file is a readable Excel/CSV (for connection test)."""
    import pandas as pd

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in FILE_DATASET_EXTS.get(db_type, set()):
        raise ValueError(
            f"'{db_type}' dataset expects one of "
            f"{sorted(FILE_DATASET_EXTS.get(db_type, set()))}, got '{ext}'"
        )
    if not os.path.isfile(file_path):
        raise ValueError(f"File not found: {file_path}")
    if ext in FILE_DATASET_EXTS["excel"]:
        pd.read_excel(file_path, sheet_name=None, nrows=1)
    else:
        pd.read_csv(file_path, nrows=1)
