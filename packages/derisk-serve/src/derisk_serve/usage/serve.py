"""LLM usage serve component."""

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
    SERVE_SERVICE_COMPONENT_NAME,
    ServeConfig,
)

logger = logging.getLogger(__name__)


class Serve(BaseServe):
    """LLM usage serve component.

    - Mounts REST API under /api/v1/serve/usage
    - Registers a DB-backed recorder to derisk-core's AIWrapper.create on startup
    - Creates the derisk_serve_llm_usage table
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
        """Load the DB model so SQLAlchemy metadata registers it."""
        from .models.models import LLMUsageEntity  # noqa: F401

    def before_start(self):
        """Create table and register the DB recorder to derisk-core."""
        from .service.service import Service

        # Ensure table exists (works for SQLite/MySQL).
        try:
            init_db = self.create_or_get_db_manager()
            init_db.create_all()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to create usage tables: {e}")

        if not (self._config and self._config.enabled):
            return

        try:
            service = self._system_app.get_component(
                SERVE_SERVICE_COMPONENT_NAME, Service
            )
            from derisk.agent.util.llm.usage_recorder import (
                register_llm_usage_recorder,
            )

            register_llm_usage_recorder(service.insert_usage)
            logger.info("LLM usage recorder registered")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to register LLM usage recorder: {e}")
