"""ECP serve configuration."""

from dataclasses import dataclass, field
from typing import Optional

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "ecp"
SERVE_APP_NAME = "derisk_serve_ecp"
SERVE_APP_NAME_HUMP = "derisk_serve_Ecp"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.ecp."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"

# Database table names
TABLE_SEMANTIC_OBJECT = "derisk_serve_ecp_semantic_object"
TABLE_RESOLUTION_CACHE = "derisk_serve_ecp_resolution_cache"
TABLE_SEMANTIC_EDGE = "derisk_serve_ecp_semantic_edge"
TABLE_CONFIRMER = "derisk_serve_ecp_confirmer"
TABLE_OP_LOG = "derisk_serve_ecp_op_log"
TABLE_ASSET_REF = "derisk_serve_ecp_asset_ref"
TABLE_WORKSPACE_CONFIG = "derisk_serve_ecp_workspace_config"

# Semantic object types
# 结构化(DB): entity/metric/relation/dimension
# 非结构化(文档,ECP-unstructured-design P0): claim/terminology/policy
OBJECT_TYPES = (
    "entity",
    "metric",
    "relation",
    "dimension",
    "claim",
    "terminology",
    "policy",
)

# Status state machine:
#   proposed --confirm--> confirmed --new version confirmed--> old version superseded
#   proposed --reject--> rejected
#   confirmed --deprecate--> deprecated
STATUS_PROPOSED = "proposed"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"
STATUS_DEPRECATED = "deprecated"
STATUS_SUPERSEDED = "superseded"

DEFAULT_WORKSPACE_ID = "default"


@auto_register_resource(
    label=_("ECP Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("Configuration for the ECP (enterprise semantic layer) serve module."),
    show_in_ui=False,
)
@dataclass
class ServeConfig(BaseServeConfig):
    """Configuration for the ECP serve module."""

    __type__ = APP_NAME

    enabled: bool = field(
        default=True,
        metadata={"help": _("Enable the ECP semantic layer serve")},
    )
    api_keys: Optional[str] = field(
        default=None,
        metadata={"help": _("Comma-separated API keys; empty means no auth")},
    )
    catalog_inject_threshold: int = field(
        default=500,
        metadata={
            "help": _(
                "Max confirmed objects injected into prompts as catalog; "
                "beyond this agents use search_semantics instead"
            )
        },
    )
