"""Workspace-owned dataset service.

Manages self-owned data assets of a scene workspace: uploaded Excel/CSV
files are materialized as per-dataset DuckDB files inside the workspace
sandbox directory, registered as `connect_config` records
(db_type=excel/csv, owner_workspace_id set) and auto-bound to the
workspace via `workspace_resource`. This makes them first-class
datasources: schema learning (table_spec/db_spec) and structured
proposals work on them unchanged.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from derisk_serve.datasource.manages.connect_config_db import ConnectConfigDao
from derisk_serve.datasource.service.file_dataset import (
    db_type_for_file,
    materialize_file_to_duckdb,
    sanitize_asset_name,
)

from .api.schemas import WorkspaceResourceRequest
from .models.models import WorkspaceResourceDao

logger = logging.getLogger(__name__)

# Sandbox root for workspace-owned assets; relative to the server working
# directory (matches the `pilot/data` convention).
DEFAULT_SANDBOX_ROOT = "pilot/data/workspaces"

SANDBOX_SUBDIRS = ("files", "db", "runtime")

__all__ = [
    "WorkspaceDatasetService",
    "sanitize_asset_name",
    "DEFAULT_SANDBOX_ROOT",
    "SANDBOX_SUBDIRS",
]


class WorkspaceDatasetService:
    """Import and list workspace-owned Excel/CSV datasets."""

    def __init__(self, system_app=None, sandbox_root: Optional[str] = None):
        self._system_app = system_app
        self._sandbox_root = sandbox_root or os.environ.get(
            "DERISK_WORKSPACE_SANDBOX_ROOT", DEFAULT_SANDBOX_ROOT
        )
        self._dao = ConnectConfigDao()
        self._resource_dao = WorkspaceResourceDao()

    # ---------------- sandbox ----------------

    def sandbox_dir(self, workspace_id: int) -> str:
        """Return the workspace sandbox dir, creating files/db/runtime."""
        root = os.path.join(self._sandbox_root, str(workspace_id))
        for sub in SANDBOX_SUBDIRS:
            os.makedirs(os.path.join(root, sub), exist_ok=True)
        return root

    # ---------------- import ----------------

    def import_dataset(
        self,
        workspace_id: int,
        file_name: str,
        file_content: bytes,
        display_name: Optional[str] = None,
        user_id: Optional[str] = None,
        trigger_learning: bool = True,
    ) -> Dict[str, Any]:
        """Import an uploaded Excel/CSV file as a workspace-owned dataset.

        Steps: save original -> materialize into per-dataset DuckDB file ->
        upsert connect_config -> ensure workspace_resource binding ->
        best-effort schema learning.

        Returns:
            Dict with datasource_id, db_name, db_type, tables, learning.
        """
        ext = os.path.splitext(file_name)[1].lower()
        db_type = db_type_for_file(file_name)
        if db_type is None:
            raise ValueError(f"Unsupported file type '{ext}', expected Excel/CSV")

        asset_name = sanitize_asset_name(os.path.splitext(os.path.basename(file_name))[0])
        display_name = display_name or asset_name
        db_name = f"ws{workspace_id}_{asset_name}"

        root = self.sandbox_dir(workspace_id)
        original_path = os.path.join(root, "files", f"{asset_name}{ext}")
        with open(original_path, "wb") as f:
            f.write(file_content)

        duckdb_path = os.path.abspath(os.path.join(root, "db", f"{asset_name}.duckdb"))
        tables = materialize_file_to_duckdb(file_content, ext, duckdb_path)

        datasource_id = self._upsert_connect_config(
            db_name=db_name,
            db_type=db_type,
            db_path=duckdb_path,
            workspace_id=workspace_id,
            comment=display_name,
            user_id=user_id,
        )
        self._ensure_resource_binding(workspace_id, datasource_id, display_name)

        learning = self._trigger_learning(datasource_id, db_name, tables, trigger_learning)

        return {
            "datasource_id": datasource_id,
            "db_name": db_name,
            "db_type": db_type,
            "display_name": display_name,
            "tables": tables,
            "duckdb_path": duckdb_path,
            "original_path": original_path,
            "learning": learning,
        }

    def _upsert_connect_config(
        self,
        db_name: str,
        db_type: str,
        db_path: str,
        workspace_id: int,
        comment: str,
        user_id: Optional[str],
    ) -> int:
        existing = self._dao.get_by_names(db_name)
        if existing is not None:
            if existing.owner_workspace_id != workspace_id:
                raise ValueError(
                    f"Dataset name conflict: '{db_name}' is owned by another "
                    f"workspace ({existing.owner_workspace_id})"
                )
            # Re-import of the same dataset: tables already replaced in the
            # backing file, reuse the existing connect_config record.
            return existing.id
        entity = self._dao.add_workspace_file_db(
            db_name=db_name,
            db_type=db_type,
            db_path=db_path,
            owner_workspace_id=workspace_id,
            comment=comment,
            user_id=user_id,
        )
        return entity.id

    def _ensure_resource_binding(
        self, workspace_id: int, datasource_id: int, display_name: str
    ) -> None:
        physical_ref = str(datasource_id)
        for entity in self._resource_dao.list_by_workspace(workspace_id, "data_source"):
            if entity.physical_ref == physical_ref:
                return
        self._resource_dao.create(
            WorkspaceResourceRequest(
                workspace_id=workspace_id,
                type="data_source",
                name=display_name,
                category="scenario_specific",
                physical_ref=physical_ref,
                access_mode="read",
            )
        )

    def _trigger_learning(
        self,
        datasource_id: int,
        db_name: str,
        tables: List[str],
        trigger_learning: bool,
    ) -> Dict[str, Any]:
        """Best-effort schema learning; failures never break the import."""
        if not trigger_learning:
            return {"status": "skipped"}
        if self._system_app is None:
            return {"status": "skipped", "reason": "no system_app"}
        try:
            from derisk.component import ComponentType

            from derisk_serve.datasource.manages.connector_manager import (
                ConnectorManager,
            )
            from derisk_serve.datasource.service.learning_service import (
                SchemaLearningService,
            )

            connector_manager = self._system_app.get_component(
                ComponentType.CONNECTOR_MANAGER, ConnectorManager
            )
            learning_service = SchemaLearningService(connector_manager, self._system_app)
            for table in tables:
                learning_service.learn_single_table(datasource_id, db_name, table)
            return {"status": "completed", "tables": tables}
        except Exception as e:
            logger.warning(f"[Dataset] schema learning failed for {db_name}: {e}")
            return {"status": "failed", "error": str(e)}

    # ---------------- list ----------------

    def list_datasets(self, workspace_id: int) -> List[Dict[str, Any]]:
        """List workspace-owned datasets."""
        return [
            {
                "datasource_id": e.id,
                "db_name": e.db_name,
                "db_type": e.db_type,
                "display_name": e.comment,
                "db_path": e.db_path,
                "gmt_created": e.gmt_created.isoformat() if e.gmt_created else None,
                "gmt_modified": e.gmt_modified.isoformat() if e.gmt_modified else None,
            }
            for e in self._dao.list_by_workspace(workspace_id)
        ]
