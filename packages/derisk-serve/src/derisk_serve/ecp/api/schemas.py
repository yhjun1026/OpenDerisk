"""ECP API schemas (request/response view objects)."""

from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field


class SemanticObjectVO(BaseModel):
    """One version of a semantic object."""

    model_config = ConfigDict(title="EcpSemanticObject")

    id: str
    version: int
    workspace_id: str = "default"
    obj_type: str
    status: str
    name: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = None
    evidence: Optional[List[Dict[str, Any]]] = None
    created_by: str = "llm"
    created_at: Optional[str] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None
    source: Optional[str] = None
    supersedes: Optional[int] = None


class SemanticObjectListVO(BaseModel):
    """Paginated semantic object list."""

    model_config = ConfigDict(title="EcpSemanticObjectList")

    items: List[SemanticObjectVO] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20


class ProposeRequest(BaseModel):
    """Create a semantic object proposal (LLM or user)."""

    model_config = ConfigDict(title="EcpProposeRequest")

    id: str = Field(..., description="Object id, e.g. 'ent.order' / 'mtr.net_sales'")
    obj_type: str = Field(..., description="entity | metric | relation | dimension")
    payload: Dict[str, Any] = Field(default_factory=dict)
    workspace_id: Optional[str] = None
    confidence: Optional[float] = None
    evidence: Optional[List[Dict[str, Any]]] = None
    created_by: str = "llm"
    source: Optional[str] = None


class ConfirmRequest(BaseModel):
    """Confirm a proposed object version."""

    model_config = ConfigDict(title="EcpConfirmRequest")

    user_id: str
    workspace_id: Optional[str] = None
    # When set, confirm with edited payload: creates a new version created by
    # the user and confirms it ("edit then confirm").
    edited_payload: Optional[Dict[str, Any]] = None


class RejectRequest(BaseModel):
    """Reject a proposed object version."""

    model_config = ConfigDict(title="EcpRejectRequest")

    user_id: str
    workspace_id: Optional[str] = None
    reason: Optional[str] = None


class DeprecateRequest(BaseModel):
    """Deprecate a confirmed object."""

    model_config = ConfigDict(title="EcpDeprecateRequest")

    user_id: str
    workspace_id: Optional[str] = None
    reason: Optional[str] = None


class CatalogEntryVO(BaseModel):
    """One-line catalog entry for prompt injection / search results."""

    model_config = ConfigDict(title="EcpCatalogEntry")

    id: str
    obj_type: str
    name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    one_line: Optional[str] = None
    grain: Optional[List[str]] = None


class ConfirmerVO(BaseModel):
    """A confirmer entry."""

    model_config = ConfigDict(title="EcpConfirmer")

    id: int
    workspace_id: str
    user_id: str
    scope: Optional[str] = None


class ConfirmerCreateRequest(BaseModel):
    """Add a confirmer."""

    model_config = ConfigDict(title="EcpConfirmerCreate")

    workspace_id: Optional[str] = None
    user_id: str
    scope: Optional[str] = None


class OpLogVO(BaseModel):
    """One op-log entry."""

    model_config = ConfigDict(title="EcpOpLog")

    id: int
    workspace_id: str
    ts: Optional[str] = None
    op: str
    detail: Optional[Dict[str, Any]] = None


class GenerateProposalsRequest(BaseModel):
    """Trigger proposal generation for a datasource (batch) or workspace (agent)."""

    model_config = ConfigDict(title="EcpGenerateProposals")

    datasource_id: Optional[int] = Field(
        default=None,
        description="Datasource to propose for (batch path). Omit for workspace-level "
        "agent run over all registered assets (when proposal_agent_id is configured).",
    )
    workspace_id: Optional[str] = None
    table_names: Optional[List[str]] = Field(
        default=None, description="Restrict to these tables; None means all learned"
    )
    max_tables: int = Field(default=50, ge=1, le=500)
    domain_hint: Optional[str] = Field(
        default=None,
        description="Workspace-level domain context injected into the proposal "
        "prompt (e.g. industry, authoritative caliber documents)",
    )


class GenerateProposalsVO(BaseModel):
    """Result of a proposal generation run."""

    model_config = ConfigDict(title="EcpGenerateProposalsResult")

    datasource_id: int
    tables_processed: int = 0
    proposals_created: int = 0
    proposal_ids: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class AssetRefVO(BaseModel):
    """A registered original-asset reference."""

    model_config = ConfigDict(title="EcpAssetRef")

    id: int
    workspace_id: str
    kind: str
    ref_id: str
    ref_meta: Dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    last_checked_at: Optional[str] = None


class AssetRefRegisterRequest(BaseModel):
    """Register an original-asset reference."""

    model_config = ConfigDict(title="EcpAssetRefRegister")

    kind: str = Field(..., description="db | document | space | api")
    ref_id: str = Field(
        ...,
        description="datasource_id | space_slug | space_slug:verbat_id | api_resource_id",
    )
    workspace_id: Optional[str] = None
    ref_meta: Optional[Dict[str, Any]] = None


class ReadinessCheckVO(BaseModel):
    """One readiness check item."""

    model_config = ConfigDict(title="EcpReadinessCheck")

    item: str
    ready: bool
    detail: Optional[str] = None


class ReadinessVO(BaseModel):
    """Readiness of an asset for proposal generation."""

    model_config = ConfigDict(title="EcpReadiness")

    kind: str
    ref_id: str
    ready: bool
    checks: List[ReadinessCheckVO] = Field(default_factory=list)


class GraphNodeVO(BaseModel):
    """A node in the semantic graph view."""

    model_config = ConfigDict(title="EcpGraphNode")

    id: str
    obj_type: str
    name: Optional[str] = None
    status: str
    version: int


class GraphLinkVO(BaseModel):
    """A link in the semantic graph view."""

    model_config = ConfigDict(title="EcpGraphLink")

    source: str
    target: str
    edge_type: str
    status: Optional[str] = None


class GraphVO(BaseModel):
    """Semantic graph: objects as nodes, materialized edges as links."""

    model_config = ConfigDict(title="EcpGraph")

    nodes: List[GraphNodeVO] = Field(default_factory=list)
    links: List[GraphLinkVO] = Field(default_factory=list)


class SpaceInfoVO(BaseModel):
    """The ECP soft-layer knowledge space of a workspace."""

    model_config = ConfigDict(title="EcpSpaceInfo")

    slug: str
    workspace_id: str
    created: bool = False


class WorkspaceConfigVO(BaseModel):
    """Per-workspace ECP settings.

    The proposal agent is a standard agent from the agent store; ECP does
    not duplicate the agent platform's model/prompt configuration.
    """

    model_config = ConfigDict(title="EcpWorkspaceConfig")

    workspace_id: str = "default"
    proposal_agent_id: Optional[str] = Field(
        default=None,
        description="提案 Agent（Agent 空间中的标准 Agent，绑定 ECP 工具）；"
        "空则使用内置批处理提案管线",
    )


class WorkspaceConfigUpdateRequest(BaseModel):
    """Update workspace ECP settings."""

    model_config = ConfigDict(title="EcpWorkspaceConfigUpdate")

    workspace_id: Optional[str] = None
    proposal_agent_id: Optional[str] = None
