"""Excel/CSV file dataset connectors.

Workspace-owned datasets (uploaded Excel/CSV files) are materialized as
DuckDB files, so both connector types delegate to the DuckDB physical
implementation. They exist as distinct db_types because their management
semantics differ from a plain DuckDB datasource: "editing" means
re-uploading a file, and deletion cascades to the backing file.
"""

from dataclasses import dataclass
from typing import Dict, List, Type

from sqlalchemy import text

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.util.i18n_utils import _

from .conn_duckdb import DuckDbConnector, DuckDbConnectorParameters


class DuckDbNativeReflection:
    """Reflection via DuckDB-native PRAGMA instead of the SQLAlchemy inspector.

    duckdb-engine 0.9.1's inspector emits pg_catalog queries that DuckDB
    1.2.x cannot answer (e.g. pg_collation), so schema learning breaks on
    inspector-based reflection. These overrides keep the new file-dataset
    connector types working without touching DuckDbConnector itself.
    """

    def get_columns(self, table_name: str) -> List[Dict]:
        """Get columns via PRAGMA table_info."""
        with self.session_scope() as session:
            rows = session.execute(
                text(f'PRAGMA table_info("{table_name}")')
            ).fetchall()
        # cid, name, type, notnull, dflt_value, pk
        return [
            {
                "name": r[1],
                "type": r[2],
                "nullable": not r[3],
                "default": r[4],
                "comment": "",
                "pk": bool(r[5]),
            }
            for r in rows
        ]

    def get_pk_constraint(self, table_name: str) -> Dict:
        """Get primary key columns via PRAGMA table_info."""
        pk_cols = [c["name"] for c in self.get_columns(table_name) if c["pk"]]
        return {"constrained_columns": pk_cols, "name": "primary"} if pk_cols else {}

    def get_indexes(self, table_name: str) -> List[Dict]:
        """File datasets carry no secondary indexes."""
        return []

    def get_foreign_keys(self, table_name: str) -> List[Dict]:
        """File datasets carry no foreign keys."""
        return []

    def get_table_comment(self, table_name: str) -> Dict:
        """File datasets carry no table comments."""
        return {"text": ""}

    def get_show_create_table(self, table_name: str) -> str:
        """Get CREATE TABLE statement via DuckDB's SHOW CREATE TABLE."""
        try:
            with self.session_scope() as session:
                result = session.execute(
                    text(f'SHOW CREATE TABLE "{table_name}"')
                ).fetchone()
                if result:
                    return result[0]
        except Exception:
            pass
        return ""

    def quote_identifier(self, identifier: str) -> str:
        """DuckDB quotes identifiers with double quotes, not backticks."""
        return f'"{identifier}"'


@auto_register_resource(
    label=_("Excel dataset"),
    category=ResourceCategory.DATABASE,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("Workspace-owned Excel file dataset, backed by DuckDB."),
)
@dataclass
class ExcelConnectorParameters(DuckDbConnectorParameters):
    """Excel dataset connection parameters (path to the backing DuckDB file)."""

    __type__ = "excel"

    def create_connector(self) -> "ExcelConnector":
        """Create Excel dataset connector."""
        return ExcelConnector.from_parameters(self)


class ExcelConnector(DuckDbNativeReflection, DuckDbConnector):
    """Excel dataset connector, physically backed by DuckDB."""

    db_type: str = "excel"

    @classmethod
    def param_class(cls) -> Type[ExcelConnectorParameters]:
        """Return the parameter class."""
        return ExcelConnectorParameters


@auto_register_resource(
    label=_("CSV dataset"),
    category=ResourceCategory.DATABASE,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("Workspace-owned CSV file dataset, backed by DuckDB."),
)
@dataclass
class CsvConnectorParameters(DuckDbConnectorParameters):
    """CSV dataset connection parameters (path to the backing DuckDB file)."""

    __type__ = "csv"

    def create_connector(self) -> "CsvConnector":
        """Create CSV dataset connector."""
        return CsvConnector.from_parameters(self)


class CsvConnector(DuckDbNativeReflection, DuckDbConnector):
    """CSV dataset connector, physically backed by DuckDB."""

    db_type: str = "csv"

    @classmethod
    def param_class(cls) -> Type[CsvConnectorParameters]:
        """Return the parameter class."""
        return CsvConnectorParameters
