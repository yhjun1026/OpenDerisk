"""
Schema Comparator for DDL Generator

This module provides functionality to compare two database schemas and detect changes.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from enum import Enum

from .core import UnifiedSchema, TableDef, ColumnDef, IndexDef, ConstraintDef

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Type of schema change."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass
class ColumnChange:
    """Represents a column change."""
    change_type: ChangeType
    column_name: str
    old_def: Optional[ColumnDef] = None
    new_def: Optional[ColumnDef] = None

    def __repr__(self):
        if self.change_type == ChangeType.ADDED:
            return f"ADD COLUMN {self.column_name}"
        elif self.change_type == ChangeType.REMOVED:
            return f"DROP COLUMN {self.column_name}"
        else:
            return f"MODIFY COLUMN {self.column_name}"


@dataclass
class IndexChange:
    """Represents an index change."""
    change_type: ChangeType
    index_name: str
    old_def: Optional[IndexDef] = None
    new_def: Optional[IndexDef] = None

    def __repr__(self):
        if self.change_type == ChangeType.ADDED:
            return f"ADD INDEX {self.index_name}"
        elif self.change_type == ChangeType.REMOVED:
            return f"DROP INDEX {self.index_name}"
        else:
            return f"MODIFY INDEX {self.index_name}"


@dataclass
class ConstraintChange:
    """Represents a constraint change."""
    change_type: ChangeType
    constraint_name: str
    old_def: Optional[ConstraintDef] = None
    new_def: Optional[ConstraintDef] = None

    def __repr__(self):
        if self.change_type == ChangeType.ADDED:
            return f"ADD CONSTRAINT {self.constraint_name}"
        elif self.change_type == ChangeType.REMOVED:
            return f"DROP CONSTRAINT {self.constraint_name}"
        else:
            return f"MODIFY CONSTRAINT {self.constraint_name}"


@dataclass
class TableChange:
    """Represents changes to a single table."""
    table_name: str
    added: bool = False
    removed: bool = False
    column_changes: List[ColumnChange] = field(default_factory=list)
    index_changes: List[IndexChange] = field(default_factory=list)
    constraint_changes: List[ConstraintChange] = field(default_factory=list)

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return (
            self.added
            or self.removed
            or bool(self.column_changes)
            or bool(self.index_changes)
            or bool(self.constraint_changes)
        )

    def get_summary(self) -> str:
        """Get a summary of changes."""
        if self.added:
            return "Table added"
        elif self.removed:
            return "Table removed"
        else:
            changes = []
            if self.column_changes:
                changes.append(f"{len(self.column_changes)} column changes")
            if self.index_changes:
                changes.append(f"{len(self.index_changes)} index changes")
            if self.constraint_changes:
                changes.append(f"{len(self.constraint_changes)} constraint changes")
            return ", ".join(changes) if changes else "No changes"


@dataclass
class SchemaDiff:
    """Represents the difference between two schemas."""

    old_version: str = "unknown"
    new_version: str = "unknown"
    old_generated: Optional[str] = None
    new_generated: Optional[str] = None

    added_tables: Set[str] = field(default_factory=set)
    removed_tables: Set[str] = field(default_factory=set)
    modified_tables: Dict[str, TableChange] = field(default_factory=dict)

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.added_tables or self.removed_tables or self.modified_tables)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all changes."""
        return {
            "tables_added": len(self.added_tables),
            "tables_removed": len(self.removed_tables),
            "tables_modified": len(self.modified_tables),
            "total_changes": len(self.added_tables) + len(self.removed_tables) + len(self.modified_tables),
        }


class SchemaComparator:
    """Compare two database schemas and detect changes."""

    def compare(self, old_schema: UnifiedSchema, new_schema: UnifiedSchema) -> SchemaDiff:
        """
        Compare two schemas and return the differences.

        Args:
            old_schema: Previous schema version
            new_schema: Current schema version

        Returns:
            SchemaDiff object containing all detected changes
        """
        diff = SchemaDiff(
            old_version=old_schema.version,
            new_version=new_schema.version,
            old_generated=old_schema.generated_at,
            new_generated=new_schema.generated_at,
        )

        old_tables = set(old_schema.tables.keys())
        new_tables = set(new_schema.tables.keys())

        # Detect added and removed tables
        diff.added_tables = new_tables - old_tables
        diff.removed_tables = old_tables - new_tables

        # Detect changes in common tables
        common_tables = old_tables & new_tables
        for table_name in common_tables:
            table_change = self._compare_table(
                old_schema.tables[table_name],
                new_schema.tables[table_name]
            )

            if table_change.has_changes():
                diff.modified_tables[table_name] = table_change

        logger.info(
            f"Schema comparison: "
            f"{len(diff.added_tables)} added, "
            f"{len(diff.removed_tables)} removed, "
            f"{len(diff.modified_tables)} modified tables"
        )

        return diff

    def _compare_table(self, old_table: TableDef, new_table: TableDef) -> TableChange:
        """Compare two versions of the same table."""
        table_change = TableChange(table_name=old_table.name)

        # Compare columns
        self._compare_columns(old_table, new_table, table_change)

        # Compare indexes
        self._compare_indexes(old_table, new_table, table_change)

        # Compare constraints
        self._compare_constraints(old_table, new_table, table_change)

        return table_change

    def _compare_columns(
        self, old_table: TableDef, new_table: TableDef, table_change: TableChange
    ):
        """Compare columns between two table versions."""
        old_columns = set(old_table.columns.keys())
        new_columns = set(new_table.columns.keys())

        # Added columns
        for col_name in new_columns - old_columns:
            table_change.column_changes.append(
                ColumnChange(
                    change_type=ChangeType.ADDED,
                    column_name=col_name,
                    new_def=new_table.columns[col_name]
                )
            )

        # Removed columns
        for col_name in old_columns - new_columns:
            table_change.column_changes.append(
                ColumnChange(
                    change_type=ChangeType.REMOVED,
                    column_name=col_name,
                    old_def=old_table.columns[col_name]
                )
            )

        # Modified columns
        for col_name in old_columns & new_columns:
            old_col = old_table.columns[col_name]
            new_col = new_table.columns[col_name]

            if self._column_changed(old_col, new_col):
                table_change.column_changes.append(
                    ColumnChange(
                        change_type=ChangeType.MODIFIED,
                        column_name=col_name,
                        old_def=old_col,
                        new_def=new_col
                    )
                )

    def _column_changed(self, old_col: ColumnDef, new_col: ColumnDef) -> bool:
        """Check if column definition changed."""
        # Compare each attribute
        return (
            old_col.type != new_col.type
            or old_col.nullable != new_col.nullable
            or old_col.primary_key != new_col.primary_key
            or old_col.autoincrement != new_col.autoincrement
            or old_col.unique != new_col.unique
            or old_col.default != new_col.default
            # Note: comment changes usually don't require ALTER TABLE
        )

    def _compare_indexes(
        self, old_table: TableDef, new_table: TableDef, table_change: TableChange
    ):
        """Compare indexes between two table versions."""
        old_indexes = set(old_table.indexes.keys())
        new_indexes = set(new_table.indexes.keys())

        # Added indexes
        for idx_name in new_indexes - old_indexes:
            table_change.index_changes.append(
                IndexChange(
                    change_type=ChangeType.ADDED,
                    index_name=idx_name,
                    new_def=new_table.indexes[idx_name]
                )
            )

        # Removed indexes
        for idx_name in old_indexes - new_indexes:
            table_change.index_changes.append(
                IndexChange(
                    change_type=ChangeType.REMOVED,
                    index_name=idx_name,
                    old_def=old_table.indexes[idx_name]
                )
            )

        # Modified indexes
        for idx_name in old_indexes & new_indexes:
            old_idx = old_table.indexes[idx_name]
            new_idx = new_table.indexes[idx_name]

            if old_idx.columns != new_idx.columns or old_idx.unique != new_idx.unique:
                table_change.index_changes.append(
                    IndexChange(
                        change_type=ChangeType.MODIFIED,
                        index_name=idx_name,
                        old_def=old_idx,
                        new_def=new_idx
                    )
                )

    def _compare_constraints(
        self, old_table: TableDef, new_table: TableDef, table_change: TableChange
    ):
        """Compare constraints between two table versions."""
        old_constraints = set(old_table.constraints.keys())
        new_constraints = set(new_table.constraints.keys())

        # Added constraints
        for const_name in new_constraints - old_constraints:
            table_change.constraint_changes.append(
                ConstraintChange(
                    change_type=ChangeType.ADDED,
                    constraint_name=const_name,
                    new_def=new_table.constraints[const_name]
                )
            )

        # Removed constraints
        for const_name in old_constraints - new_constraints:
            table_change.constraint_changes.append(
                ConstraintChange(
                    change_type=ChangeType.REMOVED,
                    constraint_name=const_name,
                    old_def=old_table.constraints[const_name]
                )
            )

        # Modified constraints
        for const_name in old_constraints & new_constraints:
            old_const = old_table.constraints[const_name]
            new_const = new_table.constraints[const_name]

            if self._constraint_changed(old_const, new_const):
                table_change.constraint_changes.append(
                    ConstraintChange(
                        change_type=ChangeType.MODIFIED,
                        constraint_name=const_name,
                        old_def=old_const,
                        new_def=new_const
                    )
                )

    def _constraint_changed(self, old_const: ConstraintDef, new_const: ConstraintDef) -> bool:
        """Check if constraint definition changed."""
        return (
            old_const.type != new_const.type
            or old_const.columns != new_const.columns
            or old_const.reference_table != new_const.reference_table
            or old_const.reference_columns != new_const.reference_columns
        )