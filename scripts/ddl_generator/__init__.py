"""
DDL Generator Package

Enterprise-grade multi-database DDL generator for Derisk project.
"""

from .core import (
    DDLGenerator,
    SchemaReflector,
    UnifiedSchema,
    TableDef,
    ColumnDef,
    IndexDef,
    ConstraintDef,
    MySQLAdapter,
    PostgreSQLAdapter,
)

__version__ = "1.0.0"

__all__ = [
    "DDLGenerator",
    "SchemaReflector",
    "UnifiedSchema",
    "TableDef",
    "ColumnDef",
    "IndexDef",
    "ConstraintDef",
    "MySQLAdapter",
    "PostgreSQLAdapter",
]