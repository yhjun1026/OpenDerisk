"""ECP semantic-layer resource for Agent editor binding.

This resource lets users bind an ECP workspace to an Agent in the editor UI.
The actual capability (catalog injection + 6 ECP tools) is built by
``ECPCapability`` via the v2 CapabilityFactory path when ``build_pack``
encounters ``AgentResource(type="ecp")``. This class only exists so the
resource type appears in the editor's resource options and can be persisted
to ``resource_tool``.
"""

import dataclasses
import logging
from typing import Any, List, Optional, Type

from derisk.agent.resource.base import Resource, ResourceParameters, ResourceType
from derisk.core.awel.flow import (
    FunctionDynamicOptions,
    OptionValue,
    Parameter,
    ResourceCategory,
    register_resource,
)
from derisk.util import ParameterDescription
from derisk.util.i18n_utils import _

logger = logging.getLogger(__name__)


def _load_ecp_workspaces() -> List[OptionValue]:
    """List bindable ECP workspaces.

    Sources (union, dedup):
    - ``default``: the global shared semantic library, always present.
    - Scene-space derived: ``ecp_<workspace_code>`` for every scene workspace
      (auto-bound at chat runtime by SceneResourceAssembler; listed here so
      custom agents can bind them explicitly too).
    - Legacy: workspaces that already have registered asset refs (covers
      ad-hoc workspaces created before the scene-space convention).
    """
    options: dict = {}

    def _put(value: str, label: str) -> None:
        options.setdefault(value, OptionValue(label=label, name=value, value=value))

    try:
        from derisk_serve.workspace.models.models import (
            WorkspaceDao,
            WorkspaceEntity,
        )

        session = WorkspaceDao().get_raw_session()
        try:
            codes = [
                row[0]
                for row in session.query(WorkspaceEntity.workspace_code).all()
            ]
        finally:
            session.close()
        from derisk_serve.workspace.ecp_derive import derived_ecp_workspace_id

        for code in codes:
            derived = derived_ecp_workspace_id(code)
            _put(derived, f"ECP workspace: {derived}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp_resource] load scene workspaces failed: {e}")

    try:
        from derisk_serve.ecp.models.models import (
            AssetRefDao,
            EcpAssetRefEntity,
        )

        session = AssetRefDao().get_raw_session()
        try:
            ws_set = {
                row[0]
                for row in session.query(EcpAssetRefEntity.workspace_id)
                .distinct()
                .all()
            }
        finally:
            session.close()
        for ws in sorted(ws_set):
            _put(ws, f"ECP workspace: {ws}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ecp_resource] load asset workspaces failed: {e}")

    _put("default", "ECP workspace: default (全局共享库)")
    default_opt = options.pop("default")
    return [default_opt, *options.values()]


@dataclasses.dataclass
class EcpResourceParameters(ResourceParameters):
    """Parameters for ECP resource."""

    workspace_id: str = dataclasses.field(
        metadata={"help": "ECP workspace id (e.g. default)"}
    )

    @classmethod
    def _resource_version(cls) -> str:
        return "v2"

    @classmethod
    def from_dict(cls, data: dict, ignore_extra_fields: bool = True) -> "EcpResourceParameters":
        copied = data.copy()
        if "workspace_id" not in copied and "value" in copied:
            import json

            val = copied.pop("value")
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict):
                        copied["workspace_id"] = parsed.get("workspace_id", "default")
                    else:
                        copied["workspace_id"] = str(parsed)
                except (json.JSONDecodeError, TypeError):
                    copied["workspace_id"] = val
            elif isinstance(val, dict):
                copied["workspace_id"] = val.get("workspace_id", "default")
        if "name" not in copied:
            copied["name"] = "ecp"
        return super().from_dict(copied, ignore_extra_fields=ignore_extra_fields)


@register_resource(
    _("ECP Semantic Layer"),
    "ecp",
    category=ResourceCategory.COMMON,
    description=_(
        "Enterprise semantic layer: injects confirmed metric/entity/dimension "
        "catalog + 6 ECP query tools (verified metric queries, raw SQL fallback)."
    ),
    parameters=[
        Parameter.build_from(
            _("Workspace ID"),
            "workspace_id",
            str,
            description=_("ECP workspace id (e.g. default)"),
            options=FunctionDynamicOptions(func=_load_ecp_workspaces),
        ),
    ],
)
class EcpResource(Resource[EcpResourceParameters]):
    """ECP semantic-layer resource.

    Lightweight: no live state (no connector). The real work is done by
    ``ECPCapability`` which is built from ``AgentResource(type="ecp")``
    during ``build_pack``.
    """

    def __init__(self, name: str, workspace_id: str = "default", **kwargs):
        self._name = name
        self._workspace_id = workspace_id

    @classmethod
    def type(cls) -> ResourceType:
        return ResourceType.ECP

    @property
    def name(self) -> str:
        return self._name

    @property
    def workspace_id(self) -> str:
        return self._workspace_id

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[EcpResourceParameters]:
        options = _load_ecp_workspaces()
        results = [{"label": o.label, "key": o.value, "description": ""} for o in options]

        @dataclasses.dataclass
        class _DynEcpParameters(EcpResourceParameters):
            workspace_id: str = dataclasses.field(
                default="default",
                metadata={"help": "ECP workspace id", "valid_values": results},
            )

        return _DynEcpParameters

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "EcpResource":
        params = EcpResourceParameters.from_dict(data, ignore_extra_fields)
        return cls(
            name=params.name,
            workspace_id=getattr(params, "workspace_id", "default"),
        )

    def to_dict(self) -> dict:
        return {
            "name": self._name,
            "type": self.type().value,
            "value": {"workspace_id": self._workspace_id},
        }
