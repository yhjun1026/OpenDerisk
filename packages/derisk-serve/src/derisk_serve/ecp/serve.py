"""ECP serve component."""

import logging
from typing import List, Optional, Union

from sqlalchemy import URL

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager
from derisk_serve.core import BaseServe

from .api.endpoints import init_endpoints, router
from .config import (
    APP_NAME,
    SERVE_APP_NAME,
    SERVE_APP_NAME_HUMP,
    SERVE_CONFIG_KEY_PREFIX,
    ServeConfig,
)

logger = logging.getLogger(__name__)


class Serve(BaseServe):
    """ECP serve component.

    - Mounts REST API under /api/v1/serve/ecp
    - Creates the five ECP tables (semantic object / resolution cache /
      semantic edge / confirmer / op log)
    """

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = f"/api/v1/serve/{APP_NAME}",
        api_tags: Optional[List[str]] = None,
        db_url_or_db: Union[str, URL, DatabaseManager] = None,
        try_create_tables: Optional[bool] = False,
    ):
        if api_tags is None:
            api_tags = [SERVE_APP_NAME_HUMP]
        super().__init__(
            system_app, api_prefix, api_tags, db_url_or_db, try_create_tables
        )
        self._config = config
        self._db_manager: Optional[DatabaseManager] = None

    def init_app(self, system_app: SystemApp):
        if self._app_has_initiated:
            return
        self._system_app = system_app
        self._system_app.app.include_router(
            router, prefix=self._api_prefix, tags=self._api_tags
        )
        self._config = self._config or ServeConfig.from_app_config(
            system_app.config, SERVE_CONFIG_KEY_PREFIX
        )
        init_endpoints(self._system_app, self._config)
        self._app_has_initiated = True

    def on_init(self):
        """Load the DB models so SQLAlchemy metadata registers them."""
        from .models.models import (  # noqa: F401
            EcpAssetRefEntity,
            EcpConfirmerEntity,
            EcpOpLogEntity,
            EcpResolutionCacheEntity,
            EcpSemanticEdgeEntity,
            EcpSemanticObjectEntity,
            EcpWorkspaceConfigEntity,
        )

    def before_start(self):
        """Create tables and register ECP agent tools."""
        if not (self._config and self._config.enabled):
            return
        try:
            init_db = self.create_or_get_db_manager()
            init_db.create_all()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to create ECP tables: {e}")

        try:
            from . import tools as _ecp_tools  # noqa: F401

            logger.info("ECP agent tools registered")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to register ECP tools: {e}")

        # Register the ECP resource type in the agent ResourceManager so it
        # appears in the resource-type catalog (GET /api/v1/resource-type/list),
        # alongside DatasourceResource / KnowledgePackSearchResource. The
        # @register_resource decorator on EcpResource only adds it to the AWEL
        # flow operator registry; the agent catalog needs this explicit call.
        # Importing EcpResource also fires that decorator as a side effect.
        try:
            from derisk.agent.resource.manage import get_resource_manager
            from derisk_serve.agent.resource.ecp import EcpResource

            get_resource_manager(self._system_app).register_resource(
                EcpResource, resource_type_alias="ecp"
            )
            logger.info("ECP resource type registered in agent ResourceManager")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to register ECP resource type: {e}")

        # Register the ECP proposal Agent code template (BAIZE subclass) so it
        # appears as a selectable agent template in the Agent editor.
        try:
            from derisk.agent import get_agent_manager

            from .agent.ecp_proposal_agent import EcpProposalAgent

            get_agent_manager(self._system_app).register_agent(
                EcpProposalAgent, ignore_duplicate=True
            )
            logger.info("ECP proposal agent template registered (EcpProposalAgent)")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to register ECP proposal agent template: {e}")
