#!/usr/bin/env python3
"""
DDL Generator for Derisk Project - Enterprise-grade multi-database DDL generator.

This module generates DDL scripts from SQLAlchemy ORM models, supporting multiple
database dialects (MySQL, PostgreSQL, and extensible to others).

Key Features:
- Single source of truth: ORM models
- Native SQLAlchemy dialect support
- Intelligent incremental DDL generation
- Extensible architecture for new databases
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Type
from collections import OrderedDict

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Index,
    UniqueConstraint,
    ForeignKey,
    inspect,
)
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.sql import sqltypes
from sqlalchemy.dialects import mysql, postgresql

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class ColumnDef:
    """Column definition in unified format."""

    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    autoincrement: bool = False
    unique: bool = False
    default: Optional[str] = None
    comment: Optional[str] = None

    # For serialization
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "nullable": self.nullable,
            "primary_key": self.primary_key,
            "autoincrement": self.autoincrement,
            "unique": self.unique,
            "default": self.default,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColumnDef":
        return cls(**data)


@dataclass
class IndexDef:
    """Index definition."""

    name: str
    columns: List[str]
    unique: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "columns": self.columns,
            "unique": self.unique,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexDef":
        return cls(**data)


@dataclass
class ConstraintDef:
    """Constraint definition."""

    name: str
    type: str  # "unique", "foreign_key", "check", etc.
    columns: List[str]
    reference_table: Optional[str] = None
    reference_columns: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "columns": self.columns,
            "reference_table": self.reference_table,
            "reference_columns": self.reference_columns,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConstraintDef":
        return cls(**data)


@dataclass
class TableDef:
    """Table definition in unified format."""

    name: str
    columns: Dict[str, ColumnDef] = field(default_factory=dict)
    indexes: Dict[str, IndexDef] = field(default_factory=dict)
    constraints: Dict[str, ConstraintDef] = field(default_factory=dict)
    comment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "columns": {k: v.to_dict() for k, v in self.columns.items()},
            "indexes": {k: v.to_dict() for k, v in self.indexes.items()},
            "constraints": {k: v.to_dict() for k, v in self.constraints.items()},
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TableDef":
        return cls(
            name=data["name"],
            columns={k: ColumnDef.from_dict(v) for k, v in data["columns"].items()},
            indexes={k: IndexDef.from_dict(v) for k, v in data["indexes"].items()},
            constraints={
                k: ConstraintDef.from_dict(v) for k, v in data["constraints"].items()
            },
            comment=data.get("comment"),
        )


@dataclass
class UnifiedSchema:
    """Unified schema representation."""

    tables: Dict[str, TableDef] = field(default_factory=dict)
    version: str = "0.0.0"
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tables": {k: v.to_dict() for k, v in self.tables.items()},
            "version": self.version,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSchema":
        return cls(
            tables={k: TableDef.from_dict(v) for k, v in data["tables"].items()},
            version=data.get("version", "0.0.0"),
            generated_at=data.get("generated_at", datetime.now().isoformat()),
        )

    def to_json(self, file_path: Path) -> None:
        """Serialize to JSON file."""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, file_path: Path) -> "UnifiedSchema":
        """Deserialize from JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# ============================================================================
# Schema Reflector
# ============================================================================

class SchemaReflector:
    """Reflect SQLAlchemy ORM models into UnifiedSchema."""

    def __init__(self, metadata: MetaData):
        """
        Initialize reflector.

        Args:
            metadata: SQLAlchemy MetaData object from Model.metadata
        """
        self.metadata = metadata

    def reflect(self) -> UnifiedSchema:
        """
        Reflect all tables from metadata.

        Returns:
            UnifiedSchema object
        """
        schema = UnifiedSchema()

        for table_name, table in self.metadata.tables.items():
            # Skip internal tables
            if self._should_skip_table(table_name):
                continue

            table_def = self._reflect_table(table)
            schema.tables[table_name] = table_def
            logger.debug(f"Reflected table: {table_name} ({len(table_def.columns)} columns)")

        logger.info(f"Reflected {len(schema.tables)} tables from metadata")
        return schema

    def _should_skip_table(self, table_name: str) -> bool:
        """Check if table should be skipped."""
        # Skip Alembic migration tables
        if table_name == "alembic_version":
            return True
        # Skip test tables
        if table_name.startswith("test_"):
            return True
        return False

    def _reflect_table(self, table: Table) -> TableDef:
        """Reflect a single table."""
        table_def = TableDef(name=table.name, comment=table.comment)

        # Reflect columns
        for column in table.columns:
            col_def = self._reflect_column(column)
            table_def.columns[col_def.name] = col_def

        # Reflect indexes
        for index in table.indexes:
            index_def = self._reflect_index(index)
            table_def.indexes[index_def.name] = index_def

        # Reflect constraints
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                constraint_def = self._reflect_unique_constraint(constraint)
                table_def.constraints[constraint_def.name] = constraint_def
            # TODO: Handle ForeignKey, CheckConstraint, etc.

        return table_def

    def _reflect_column(self, column: Column) -> ColumnDef:
        """Reflect a single column."""
        # Determine column type string
        type_str = self._get_type_string(column.type)

        # Process default value
        default_value = None
        if column.default:
            default_arg = column.default.arg
            # Handle callable defaults (like datetime.now)
            if callable(default_arg):
                default_value = default_arg.__name__
            else:
                default_value = str(default_arg)

        return ColumnDef(
            name=column.name,
            type=type_str,
            nullable=column.nullable,
            primary_key=column.primary_key,
            autoincrement=column.autoincrement or False,
            unique=column.unique or False,
            default=default_value,
            comment=column.comment,
        )

    def _get_type_string(self, sqla_type: sqltypes.TypeEngine) -> str:
        """
        Convert SQLAlchemy type to string representation.

        This preserves the original type information for dialect-specific generation.
        """
        # Get the type class name
        type_class = type(sqla_type).__name__

        # Handle common types with parameters
        if hasattr(sqla_type, 'length') and sqla_type.length:
            return f"{type_class}({sqla_type.length})"
        elif hasattr(sqla_type, 'precision') and sqla_type.precision:
            if hasattr(sqla_type, 'scale') and sqla_type.scale:
                return f"{type_class}({sqla_type.precision}, {sqla_type.scale})"
            return f"{type_class}({sqla_type.precision})"

        # Default: return type class name
        return type_class

    def _reflect_index(self, index: Index) -> IndexDef:
        """Reflect an index."""
        return IndexDef(
            name=index.name,
            columns=[col.name for col in index.columns],
            unique=index.unique,
        )

    def _reflect_unique_constraint(self, constraint: UniqueConstraint) -> ConstraintDef:
        """Reflect a unique constraint."""
        return ConstraintDef(
            name=constraint.name or f"uk_{constraint.columns[0].name}",
            type="unique",
            columns=[col.name for col in constraint.columns],
        )


# ============================================================================
# Dialect Adapters
# ============================================================================

class DialectAdapter(ABC):
    """Base class for database dialect adapters."""

    @property
    @abstractmethod
    def dialect_name(self) -> str:
        """Dialect name (e.g., 'mysql', 'postgresql')."""
        pass

    @abstractmethod
    def generate_full_ddl(self, schema: UnifiedSchema) -> List[str]:
        """
        Generate full DDL statements for creating all tables.

        Args:
            schema: Unified schema

        Returns:
            List of DDL statements
        """
        pass

    @abstractmethod
    def generate_incremental_ddl(
        self, old_schema: UnifiedSchema, new_schema: UnifiedSchema
    ) -> List[str]:
        """
        Generate incremental DDL statements for schema migration.

        Args:
            old_schema: Previous schema version
            new_schema: Current schema version

        Returns:
            List of DDL statements
        """
        pass

    @staticmethod
    @abstractmethod
    def quote_identifier(name: str) -> str:
        """Quote identifier with database-specific quotes."""
        pass


class MySQLAdapter(DialectAdapter):
    """MySQL dialect adapter."""

    dialect_name = "mysql"

    @staticmethod
    def quote_identifier(name: str) -> str:
        return f"`{name}`"

    def generate_full_ddl(self, schema: UnifiedSchema) -> List[str]:
        """Generate full MySQL DDL."""
        statements = []

        # Header
        statements.append("-- ============================================================")
        statements.append("-- MySQL DDL Script for Derisk")
        statements.append(f"-- Version: {schema.version}")
        statements.append(f"-- Generated: {schema.generated_at}")
        statements.append("-- ============================================================")
        statements.append("")
        statements.append("SET NAMES utf8mb4;")
        statements.append("SET FOREIGN_KEY_CHECKS = 0;")
        statements.append("")

        # Generate CREATE TABLE for each table
        for table_name, table_def in schema.tables.items():
            ddl = self._generate_create_table(table_def)
            statements.extend(ddl)
            statements.append("")

        # Footer
        statements.append("SET FOREIGN_KEY_CHECKS = 1;")
        statements.append("")
        statements.append("-- ============================================================")
        statements.append("-- End of DDL Script")
        statements.append("-- ============================================================")

        return statements

    def _generate_create_table(self, table_def: TableDef) -> List[str]:
        """Generate CREATE TABLE statement for MySQL."""
        lines = []

        # Table header
        lines.append(f"-- Table: {table_def.name}")
        lines.append(f"CREATE TABLE IF NOT EXISTS {self.quote_identifier(table_def.name)} (")

        # Columns
        column_defs = []
        primary_keys = []

        for col_name, col_def in table_def.columns.items():
            col_ddl = self._generate_column_ddl(col_def)
            column_defs.append(f"  {col_ddl}")

            if col_def.primary_key:
                primary_keys.append(col_name)

        # Add PRIMARY KEY constraint
        if primary_keys:
            pk_cols = ", ".join([self.quote_identifier(pk) for pk in primary_keys])
            column_defs.append(f"  PRIMARY KEY ({pk_cols})")

        # Add unique constraints
        for constraint_def in table_def.constraints.values():
            if constraint_def.type == "unique":
                cols = ", ".join(
                    [self.quote_identifier(col) for col in constraint_def.columns]
                )
                column_defs.append(
                    f"  UNIQUE KEY {self.quote_identifier(constraint_def.name)} ({cols})"
                )

        # Add indexes
        for index_def in table_def.indexes.values():
            cols = ", ".join(
                [self.quote_identifier(col) for col in index_def.columns]
            )
            unique_keyword = "UNIQUE " if index_def.unique else ""
            column_defs.append(
                f"  {unique_keyword}KEY {self.quote_identifier(index_def.name)} ({cols})"
            )

        lines.append(",\n".join(column_defs))

        # Table options
        lines.append(
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
        )

        return lines

    def _generate_column_ddl(self, col_def: ColumnDef) -> str:
        """Generate column definition for MySQL."""
        parts = [self.quote_identifier(col_def.name)]

        # Type
        mysql_type = self._map_type_to_mysql(col_def.type)
        parts.append(mysql_type)

        # NULL/NOT NULL
        if col_def.primary_key:
            parts.append("NOT NULL")
        elif not col_def.nullable:
            parts.append("NOT NULL")
        else:
            parts.append("NULL")

        # AUTO_INCREMENT
        if col_def.primary_key and (col_def.autoincrement or "INTEGER" in col_def.type.upper()):
            parts.append("AUTO_INCREMENT")

        # DEFAULT
        if col_def.default:
            default_val = self._process_default_value(col_def.default)
            parts.append(f"DEFAULT {default_val}")

        # COMMENT
        if col_def.comment:
            comment = col_def.comment.replace("'", "''")
            parts.append(f"COMMENT '{comment}'")

        return " ".join(parts)

    def _map_type_to_mysql(self, type_str: str) -> str:
        """Map type string to MySQL-specific type."""
        # Extract base type and parameters
        import re
        match = re.match(r'(\w+)(?:\((\d+(?:,\s*\d+)?)\))?', type_str)
        if not match:
            return type_str.upper()

        base_type = match.group(1).upper()
        params = match.group(2)

        # Type mapping
        type_map = {
            'STRING': 'VARCHAR',
            'INTEGER': 'INT',
            'BIGINT': 'BIGINT',
            'SMALLINT': 'SMALLINT',
            'SMALLINTEGER': 'SMALLINT',
            'DATETIME': 'DATETIME',
            'BOOLEAN': 'TINYINT(1)',
            'TEXT': 'TEXT',
            'JSON': 'JSON',
            'FLOAT': 'FLOAT',
        }

        # Get mapped type
        mapped_type = type_map.get(base_type, base_type)

        # Handle special cases
        if base_type == 'TEXT':
            # Check for TEXT with length parameter
            if params and ('2147483647' in params or '2**31' in params):
                return 'LONGTEXT'
            elif params:
                try:
                    length = int(params)
                    if length > 65535:
                        return 'LONGTEXT'
                except (ValueError, TypeError):
                    pass
            return 'TEXT'

        elif base_type == 'STRING' and params:
            # VARCHAR with length
            return f'VARCHAR({params})'

        elif mapped_type in ('INT', 'BIGINT', 'SMALLINT') and not params:
            return mapped_type

        elif params:
            return f'{mapped_type}({params})'

        return mapped_type

    def _process_default_value(self, default: str) -> str:
        """Process default value for MySQL."""
        # Handle datetime defaults
        if 'now' in default.lower() or 'datetime' in default.lower():
            return "CURRENT_TIMESTAMP"

        # Handle boolean defaults
        if default in ("True", "1"):
            return "1"
        if default in ("False", "0"):
            return "0"

        # Handle numeric defaults
        if default.lstrip('-').isdigit():
            return default

        # Handle None/null
        if default in ("None", "null"):
            return "NULL"

        # Default: treat as string literal (quote it)
        return default

    def generate_incremental_ddl(
        self, old_schema: UnifiedSchema, new_schema: UnifiedSchema
    ) -> List[str]:
        """Generate incremental MySQL DDL for schema migration."""
        from .comparator import SchemaComparator, ChangeType

        comparator = SchemaComparator()
        diff = comparator.compare(old_schema, new_schema)

        if not diff.has_changes():
            logger.info("No schema changes detected")
            return []

        statements = []

        # Header
        statements.append("-- ============================================================")
        statements.append("-- MySQL Incremental DDL Script for Derisk")
        statements.append(f"-- Upgrade from {diff.old_version} to {diff.new_version}")
        if diff.old_generated:
            statements.append(f"-- Source schema generated: {diff.old_generated}")
        statements.append(f"-- Generated: {diff.new_generated}")
        statements.append("-- ============================================================")
        statements.append("")
        statements.append("SET NAMES utf8mb4;")
        statements.append("SET FOREIGN_KEY_CHECKS = 0;")
        statements.append("")

        # New tables
        if diff.added_tables:
            statements.append("-- ============================================================")
            statements.append("-- New Tables")
            statements.append("-- ============================================================")
            statements.append("")

            for table_name in sorted(diff.added_tables):
                table_def = new_schema.tables[table_name]
                ddl_lines = self._generate_create_table(table_def)
                statements.extend(ddl_lines)
                statements.append("")

        # Modified tables
        if diff.modified_tables:
            statements.append("-- ============================================================")
            statements.append("-- Modified Tables")
            statements.append("-- ============================================================")
            statements.append("")

            for table_name in sorted(diff.modified_tables.keys()):
                table_change = diff.modified_tables[table_name]
                statements.append(f"-- Table: {table_name}")

                # Column changes
                for col_change in table_change.column_changes:
                    if col_change.change_type == ChangeType.ADDED:
                        col_ddl = self._generate_column_ddl(col_change.new_def)
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"ADD COLUMN {col_ddl};"
                        )
                    elif col_change.change_type == ChangeType.MODIFIED:
                        col_ddl = self._generate_column_ddl(col_change.new_def)
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"MODIFY COLUMN {col_ddl};"
                        )
                    elif col_change.change_type == ChangeType.REMOVED:
                        # Safe mode: comment out DROP statements
                        statements.append(
                            f"-- ALTER TABLE {self.quote_identifier(table_name)} "
                            f"DROP COLUMN {self.quote_identifier(col_change.column_name)};"
                        )

                # Index changes
                for idx_change in table_change.index_changes:
                    if idx_change.change_type == ChangeType.ADDED:
                        idx_def = idx_change.new_def
                        cols = ", ".join(
                            [self.quote_identifier(c) for c in idx_def.columns]
                        )
                        unique_kw = "UNIQUE " if idx_def.unique else ""
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"ADD {unique_kw}INDEX {self.quote_identifier(idx_def.name)} ({cols});"
                        )
                    elif idx_change.change_type == ChangeType.REMOVED:
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"DROP INDEX {self.quote_identifier(idx_change.index_name)};"
                        )
                    elif idx_change.change_type == ChangeType.MODIFIED:
                        # MySQL requires DROP and re-add for modified indexes
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"DROP INDEX {self.quote_identifier(idx_change.index_name)};"
                        )
                        idx_def = idx_change.new_def
                        cols = ", ".join(
                            [self.quote_identifier(c) for c in idx_def.columns]
                        )
                        unique_kw = "UNIQUE " if idx_def.unique else ""
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"ADD {unique_kw}INDEX {self.quote_identifier(idx_def.name)} ({cols});"
                        )

                # Constraint changes
                for const_change in table_change.constraint_changes:
                    if const_change.change_type == ChangeType.ADDED:
                        const_def = const_change.new_def
                        cols = ", ".join(
                            [self.quote_identifier(c) for c in const_def.columns]
                        )
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"ADD CONSTRAINT {self.quote_identifier(const_def.name)} "
                            f"UNIQUE ({cols});"
                        )
                    elif const_change.change_type == ChangeType.REMOVED:
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"DROP INDEX {self.quote_identifier(const_change.constraint_name)};"
                        )

                statements.append("")

        # Removed tables (commented out for safety)
        if diff.removed_tables:
            statements.append("-- ============================================================")
            statements.append("-- Removed Tables (commented out for safety)")
            statements.append("-- ============================================================")
            statements.append("")

            for table_name in sorted(diff.removed_tables):
                statements.append(
                    f"-- DROP TABLE IF EXISTS {self.quote_identifier(table_name)};"
                )
            statements.append("")

        # Footer
        statements.append("SET FOREIGN_KEY_CHECKS = 1;")
        statements.append("")
        statements.append("-- ============================================================")
        statements.append("-- End of Incremental DDL Script")
        statements.append("-- ============================================================")

        return statements


class PostgreSQLAdapter(DialectAdapter):
    """PostgreSQL dialect adapter."""

    dialect_name = "postgresql"

    @staticmethod
    def quote_identifier(name: str) -> str:
        return f'"{name}"'

    def generate_full_ddl(self, schema: UnifiedSchema) -> List[str]:
        """Generate full PostgreSQL DDL."""
        statements = []

        # Header
        statements.append("-- ============================================================")
        statements.append("-- PostgreSQL DDL Script for Derisk")
        statements.append(f"-- Version: {schema.version}")
        statements.append(f"-- Generated: {schema.generated_at}")
        statements.append("-- ============================================================")
        statements.append("")

        # Generate CREATE TABLE for each table
        for table_name, table_def in schema.tables.items():
            ddl = self._generate_create_table(table_def)
            statements.extend(ddl)
            statements.append("")

        # Footer
        statements.append("-- ============================================================")
        statements.append("-- End of DDL Script")
        statements.append("-- ============================================================")

        return statements

    def _generate_create_table(self, table_def: TableDef) -> List[str]:
        """Generate CREATE TABLE statement for PostgreSQL."""
        lines = []

        # Table header
        lines.append(f"-- Table: {table_def.name}")
        lines.append(
            f"CREATE TABLE IF NOT EXISTS {self.quote_identifier(table_def.name)} ("
        )

        # Columns
        column_defs = []
        primary_keys = []

        for col_name, col_def in table_def.columns.items():
            col_ddl = self._generate_column_ddl(col_def)
            column_defs.append(f"  {col_ddl}")

            if col_def.primary_key:
                primary_keys.append(col_name)

        # Add PRIMARY KEY constraint
        if primary_keys:
            pk_cols = ", ".join([self.quote_identifier(pk) for pk in primary_keys])
            column_defs.append(f"  PRIMARY KEY ({pk_cols})")

        # Add unique constraints
        for constraint_def in table_def.constraints.values():
            if constraint_def.type == "unique":
                cols = ", ".join(
                    [self.quote_identifier(col) for col in constraint_def.columns]
                )
                column_defs.append(
                    f"  CONSTRAINT {self.quote_identifier(constraint_def.name)} UNIQUE ({cols})"
                )

        lines.append(",\n".join(column_defs))
        lines.append(");")

        # Create indexes separately in PostgreSQL
        for index_def in table_def.indexes.values():
            index_ddl = self._generate_create_index(table_def.name, index_def)
            lines.append(index_ddl)

        return lines

    def _generate_column_ddl(self, col_def: ColumnDef) -> str:
        """Generate column definition for PostgreSQL."""
        parts = [self.quote_identifier(col_def.name)]

        # Type
        pg_type = self._map_type_to_postgresql(col_def.type)
        parts.append(pg_type)

        # Handle SERIAL for auto-increment primary keys
        if col_def.primary_key and (col_def.autoincrement or "INTEGER" in col_def.type.upper()):
            # Replace INTEGER with SERIAL
            parts[1] = "SERIAL"
            # Remove NOT NULL (SERIAL implies NOT NULL)
            parts = parts[:2]  # Keep only name and type
        else:
            # NULL/NOT NULL
            if not col_def.nullable:
                parts.append("NOT NULL")

        # DEFAULT
        if col_def.default and not (col_def.primary_key and col_def.autoincrement):
            default_val = self._process_default_value(col_def.default)
            parts.append(f"DEFAULT {default_val}")

        return " ".join(parts)

    def _map_type_to_postgresql(self, type_str: str) -> str:
        """Map type string to PostgreSQL-specific type."""
        import re
        match = re.match(r'(\w+)(?:\((\d+(?:,\s*\d+)?)\))?', type_str)
        if not match:
            return type_str.upper()

        base_type = match.group(1).upper()
        params = match.group(2)

        # Type mapping
        type_map = {
            'STRING': 'VARCHAR',
            'INTEGER': 'INTEGER',
            'BIGINT': 'BIGINT',
            'SMALLINT': 'SMALLINT',
            'SMALLINTEGER': 'SMALLINT',
            'DATETIME': 'TIMESTAMP',
            'BOOLEAN': 'BOOLEAN',
            'TEXT': 'TEXT',
            'JSON': 'JSON',
            'FLOAT': 'REAL',
        }

        # Get mapped type
        mapped_type = type_map.get(base_type, base_type)

        # Handle special cases
        if base_type == 'STRING' and params:
            # VARCHAR with length
            return f'VARCHAR({params})'

        elif base_type == 'TEXT':
            # PostgreSQL TEXT can handle any size
            return 'TEXT'

        elif mapped_type in ('INTEGER', 'BIGINT', 'SMALLINT') and not params:
            return mapped_type

        elif params:
            return f'{mapped_type}({params})'

        return mapped_type

    def _process_default_value(self, default: str) -> str:
        """Process default value for PostgreSQL."""
        # Handle datetime defaults
        if 'now' in default.lower() or 'datetime' in default.lower():
            return "CURRENT_TIMESTAMP"

        # Handle boolean defaults (PostgreSQL supports true/false literals)
        if default in ("True", "1"):
            return "true"
        if default in ("False", "0"):
            return "false"

        # Handle numeric defaults
        if default.lstrip('-').isdigit():
            return default

        # Handle None/null
        if default in ("None", "null"):
            return "NULL"

        # Default: treat as string literal
        return default

    def _generate_create_index(self, table_name: str, index_def: IndexDef) -> str:
        """Generate CREATE INDEX statement for PostgreSQL."""
        unique_keyword = "UNIQUE " if index_def.unique else ""
        cols = ", ".join([self.quote_identifier(col) for col in index_def.columns])

        return (
            f"CREATE {unique_keyword}INDEX {self.quote_identifier(index_def.name)} "
            f"ON {self.quote_identifier(table_name)} ({cols});"
        )

    def generate_incremental_ddl(
        self, old_schema: UnifiedSchema, new_schema: UnifiedSchema
    ) -> List[str]:
        """Generate incremental PostgreSQL DDL for schema migration."""
        from .comparator import SchemaComparator, ChangeType

        comparator = SchemaComparator()
        diff = comparator.compare(old_schema, new_schema)

        if not diff.has_changes():
            logger.info("No schema changes detected")
            return []

        statements = []

        # Header
        statements.append("-- ============================================================")
        statements.append("-- PostgreSQL Incremental DDL Script for Derisk")
        statements.append(f"-- Upgrade from {diff.old_version} to {diff.new_version}")
        if diff.old_generated:
            statements.append(f"-- Source schema generated: {diff.old_generated}")
        statements.append(f"-- Generated: {diff.new_generated}")
        statements.append("-- ============================================================")
        statements.append("")

        # New tables
        if diff.added_tables:
            statements.append("-- ============================================================")
            statements.append("-- New Tables")
            statements.append("-- ============================================================")
            statements.append("")

            for table_name in sorted(diff.added_tables):
                table_def = new_schema.tables[table_name]
                ddl_lines = self._generate_create_table(table_def)
                statements.extend(ddl_lines)
                statements.append("")

        # Modified tables
        if diff.modified_tables:
            statements.append("-- ============================================================")
            statements.append("-- Modified Tables")
            statements.append("-- ============================================================")
            statements.append("")

            for table_name in sorted(diff.modified_tables.keys()):
                table_change = diff.modified_tables[table_name]
                statements.append(f"-- Table: {table_name}")

                # Column changes
                for col_change in table_change.column_changes:
                    if col_change.change_type == ChangeType.ADDED:
                        col_ddl = self._generate_column_ddl(col_change.new_def)
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"ADD COLUMN {col_ddl};"
                        )
                    elif col_change.change_type == ChangeType.MODIFIED:
                        col_ddl = self._generate_column_ddl(col_change.new_def)
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"ALTER COLUMN {col_ddl};"
                        )
                    elif col_change.change_type == ChangeType.REMOVED:
                        # Safe mode: comment out DROP statements
                        statements.append(
                            f"-- ALTER TABLE {self.quote_identifier(table_name)} "
                            f"DROP COLUMN {self.quote_identifier(col_change.column_name)};"
                        )

                # Index changes
                for idx_change in table_change.index_changes:
                    if idx_change.change_type == ChangeType.ADDED:
                        statements.append(
                            self._generate_create_index(table_name, idx_change.new_def)
                        )
                    elif idx_change.change_type == ChangeType.REMOVED:
                        statements.append(
                            f"DROP INDEX {self.quote_identifier(idx_change.index_name)};"
                        )
                    elif idx_change.change_type == ChangeType.MODIFIED:
                        # PostgreSQL requires DROP and re-create for modified indexes
                        statements.append(
                            f"DROP INDEX {self.quote_identifier(idx_change.index_name)};"
                        )
                        statements.append(
                            self._generate_create_index(table_name, idx_change.new_def)
                        )

                # Constraint changes
                for const_change in table_change.constraint_changes:
                    if const_change.change_type == ChangeType.ADDED:
                        const_def = const_change.new_def
                        cols = ", ".join(
                            [self.quote_identifier(c) for c in const_def.columns]
                        )
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"ADD CONSTRAINT {self.quote_identifier(const_def.name)} "
                            f"UNIQUE ({cols});"
                        )
                    elif const_change.change_type == ChangeType.REMOVED:
                        statements.append(
                            f"ALTER TABLE {self.quote_identifier(table_name)} "
                            f"DROP CONSTRAINT {self.quote_identifier(const_change.constraint_name)};"
                        )

                statements.append("")

        # Removed tables (commented out for safety)
        if diff.removed_tables:
            statements.append("-- ============================================================")
            statements.append("-- Removed Tables (commented out for safety)")
            statements.append("-- ============================================================")
            statements.append("")

            for table_name in sorted(diff.removed_tables):
                statements.append(
                    f"-- DROP TABLE IF EXISTS {self.quote_identifier(table_name)};"
                )
            statements.append("")

        # Footer
        statements.append("-- ============================================================")
        statements.append("-- End of Incremental DDL Script")
        statements.append("-- ============================================================")

        return statements


# ============================================================================
# DDL Generator Main Class
# ============================================================================

class DDLGenerator:
    """Main DDL generator class."""

    def __init__(self, metadata: MetaData, version: str = "0.0.0"):
        """
        Initialize DDL generator.

        Args:
            metadata: SQLAlchemy MetaData object
            version: Current project version
        """
        self.metadata = metadata
        self.version = version
        self.reflector = SchemaReflector(metadata)

        # Register dialect adapters
        self.adapters: Dict[str, DialectAdapter] = {
            "mysql": MySQLAdapter(),
            "postgresql": PostgreSQLAdapter(),
        }

    def generate_full_ddl(
        self, dialect: str, output_file: Optional[Path] = None
    ) -> str:
        """
        Generate full DDL for a specific dialect.

        Args:
            dialect: Database dialect ('mysql', 'postgresql')
            output_file: Optional output file path

        Returns:
            DDL content as string
        """
        if dialect not in self.adapters:
            raise ValueError(f"Unsupported dialect: {dialect}")

        # Reflect schema
        schema = self.reflector.reflect()
        schema.version = self.version

        # Generate DDL
        adapter = self.adapters[dialect]
        ddl_statements = adapter.generate_full_ddl(schema)
        ddl_content = "\n".join(ddl_statements)

        # Write to file if specified
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(ddl_content, encoding="utf-8")
            logger.info(f"Generated full DDL for {dialect}: {output_file}")

        return ddl_content

    def generate_all_dialects(self, output_dir: Path) -> Dict[str, Path]:
        """
        Generate full DDL for all registered dialects.

        Args:
            output_dir: Output directory root

        Returns:
            Dict mapping dialect name to output file path
        """
        output_files = {}

        for dialect in self.adapters.keys():
            # Create dialect-specific directory
            dialect_dir = output_dir / dialect
            dialect_dir.mkdir(parents=True, exist_ok=True)

            # Generate output file
            output_file = dialect_dir / "derisk.sql"
            self.generate_full_ddl(dialect, output_file)

            output_files[dialect] = output_file

        return output_files

    def generate_incremental_ddl(
        self,
        dialect: str,
        old_ddl_file: Path,
        output_file: Optional[Path] = None
    ) -> Optional[str]:
        """
        Generate incremental DDL by comparing with existing DDL file.

        Args:
            dialect: Database dialect
            old_ddl_file: Path to previous full DDL file
            output_file: Optional output file path for incremental DDL

        Returns:
            Incremental DDL content, or None if no changes detected
        """
        if dialect not in self.adapters:
            raise ValueError(f"Unsupported dialect: {dialect}")

        if not old_ddl_file.exists():
            logger.warning(f"Old DDL file not found: {old_ddl_file}")
            return None

        # Parse old DDL to extract schema info
        old_schema = self._parse_ddl_file(old_ddl_file, dialect)

        # Reflect current schema
        new_schema = self.reflector.reflect()
        new_schema.version = self.version

        # Generate incremental DDL
        adapter = self.adapters[dialect]
        ddl_statements = adapter.generate_incremental_ddl(old_schema, new_schema)

        if not ddl_statements:
            return None

        ddl_content = "\n".join(ddl_statements)

        # Write to file if specified
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(ddl_content, encoding="utf-8")
            logger.info(f"Generated incremental DDL for {dialect}: {output_file}")

        return ddl_content

    def _parse_ddl_file(self, ddl_file: Path, dialect: str) -> UnifiedSchema:
        """
        Parse existing DDL file to extract schema information.

        Args:
            ddl_file: Path to DDL file
            dialect: Database dialect

        Returns:
            UnifiedSchema object
        """
        import re
        from datetime import datetime

        content = ddl_file.read_text(encoding="utf-8")

        # Extract version and generation time
        version = "unknown"
        generated_at = datetime.now().isoformat()

        version_match = re.search(r'-- Version:\s*(\S+)', content)
        if version_match:
            version = version_match.group(1)

        generated_match = re.search(r'-- Generated:\s*(\d{4}-\d{2}-\d{2}T[\d:.]+)', content)
        if generated_match:
            generated_at = generated_match.group(1)

        # Create a minimal schema with metadata only
        # Note: For a full implementation, we would parse all table definitions
        # This is a simplified version that works with the comparator
        schema = UnifiedSchema(
            version=version,
            generated_at=generated_at
        )

        # Parse table names (simplified)
        # In a production system, we'd use a proper SQL parser
        table_pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"]?(\w+)[`"]?\s*\('
        for match in re.finditer(table_pattern, content, re.IGNORECASE):
            table_name = match.group(1)
            # Create empty table def (the comparator will handle the rest)
            schema.tables[table_name] = TableDef(name=table_name)

        logger.info(f"Parsed {len(schema.tables)} tables from existing DDL: {ddl_file}")

        return schema


# ============================================================================
# Utility Functions
# ============================================================================

def get_project_version(project_root: Path) -> str:
    """
    Get project version from packages/__init__.py.

    Args:
        project_root: Project root directory

    Returns:
        Version string (e.g., "0.1.0")
    """
    version_file = project_root / "packages" / "__init__.py"

    if not version_file.exists():
        logger.warning(f"Version file not found: {version_file}")
        return "0.0.0"

    content = version_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)

    if match:
        return match.group(1)

    logger.warning("Version not found in version file")
    return "0.0.0"


def discover_metadata() -> MetaData:
    """
    Discover and return SQLAlchemy MetaData from ORM models.

    This function scans the codebase for Model classes and returns
    their combined MetaData object.

    Returns:
        SQLAlchemy MetaData object
    """
    import importlib
    import sys

    # First, try the global db manager if initialized
    try:
        from derisk.storage.metadata import db

        if db.is_initialized and db.metadata.tables:
            logger.info("Using initialized database manager metadata")
            return db.metadata
    except ImportError as e:
        logger.debug(f"Database manager import failed: {e}")

    # Otherwise, discover models by importing them
    logger.info("Discovering ORM models by scanning packages...")

    # Add package paths to sys.path if needed
    package_roots = [
        Path(__file__).parent.parent.parent / "packages" / "derisk-core" / "src",
        Path(__file__).parent.parent.parent / "packages" / "derisk-serve" / "src",
    ]

    for pkg_root in package_roots:
        pkg_root_str = str(pkg_root)
        if pkg_root_str not in sys.path:
            sys.path.insert(0, pkg_root_str)

    # Model files to import (relative to package roots)
    model_modules = [
        "derisk.storage.chat_history.chat_history_db",
        "derisk_serve.conversation.models.models",
        "derisk_serve.artifact.models.models",
        "derisk_serve.cron.models.models",
        "derisk_serve.flow.models.models",
        "derisk_serve.datasource.file_learning.models",
        "derisk_serve.sql_guard.models",
    ]

    # Import all model modules
    imported_count = 0
    for module_name in model_modules:
        try:
            importlib.import_module(module_name)
            imported_count += 1
            logger.debug(f"Imported model module: {module_name}")
        except ImportError as e:
            logger.warning(f"Failed to import {module_name}: {e}")
        except Exception as e:
            logger.warning(f"Error importing {module_name}: {e}")

    logger.info(f"Successfully imported {imported_count}/{len(model_modules)} model modules")

    # Now collect all Model metadata
    try:
        from derisk.storage.metadata import db

        if db.metadata.tables:
            logger.info(f"Discovered {len(db.metadata.tables)} tables from metadata")
            return db.metadata
        else:
            logger.warning("No tables found in metadata after importing models")
            return MetaData()
    except ImportError:
        logger.error("Failed to import db manager after model discovery")
        return MetaData()