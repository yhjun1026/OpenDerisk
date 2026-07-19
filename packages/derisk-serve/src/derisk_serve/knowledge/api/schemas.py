"""Pydantic schemas for the knowledge HTTP API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SpaceInfo(BaseModel):
    slug: str
    root: str
    backend: Optional[str] = "local"  # "local" | "distributed"
    # RFC-005: dual-form space ("personal" | "agent_memory")
    space_type: Optional[str] = "personal"
    # v2 ingest pipeline config (RFC 004 §6). All optional.
    default_agent_id: Optional[str] = None
    llm_model: Optional[str] = None
    multimodal_model: Optional[str] = None
    embedder_model: Optional[str] = None
    # Access control (owner empty = legacy world-accessible space)
    visibility: Optional[str] = None  # private | shared | public
    owner_id: Optional[str] = None
    # v5 retrieval tuning (both default off)
    rerank_model: Optional[str] = None
    embed_verbats: Optional[bool] = None


class CreateSpaceRequest(BaseModel):
    slug: str
    backend: Optional[str] = None  # "local" | "distributed"; None = server default
    space_type: Optional[str] = None  # "personal" | "agent_memory"; None = personal
    default_agent_id: Optional[str] = None
    llm_model: Optional[str] = None
    multimodal_model: Optional[str] = None
    embedder_model: Optional[str] = None
    rerank_model: Optional[str] = None
    embed_verbats: Optional[bool] = None
    visibility: Optional[str] = None  # private | shared | public; None = private


class UpdateSpaceRequest(BaseModel):
    """PATCH /spaces/{slug} — all fields optional, only set fields are updated."""

    default_agent_id: Optional[str] = None
    llm_model: Optional[str] = None
    multimodal_model: Optional[str] = None
    embedder_model: Optional[str] = None
    rerank_model: Optional[str] = None
    embed_verbats: Optional[bool] = None


class TreeNode(BaseModel):
    """One node in a wiki/ or raw/ directory tree."""

    name: str
    path: str  # path relative to the space root
    is_dir: bool
    size: Optional[int] = None
    children: Optional[List["TreeNode"]] = None


TreeNode.model_rebuild()


class DocReadResponse(BaseModel):
    id: str
    path: str
    type: str
    title: str
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    content: str
    version: int


class DocCreateRequest(BaseModel):
    path: str
    content: str


class DocEditRequest(BaseModel):
    content: str


class DocListResponse(BaseModel):
    items: List[Dict[str, Any]]


class EdgeOut(BaseModel):
    id: str
    subject: str
    predicate: str
    object: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    source_document_id: Optional[str] = None
    weight: float = 1.0


class SubgraphResponse(BaseModel):
    nodes: List[str] = Field(default_factory=list)
    edges: List[EdgeOut] = Field(default_factory=list)
    root: Optional[str] = None


class VerbatOut(BaseModel):
    id: str
    source_file: str
    extract_mode: str
    deprecated: bool = False
    content_preview: Optional[str] = None
    content_date: Optional[str] = None
    filed_at: Optional[str] = None
    # 记忆元数据 (author/user_id/conv_id/turn_round 等)
    metadata: Optional[Dict[str, Any]] = None


class VerbatListResponse(BaseModel):
    items: List[VerbatOut]


class VerbatHitOut(BaseModel):
    verbat_id: str
    score: float = 0.0
    snippet: str = ""
    source_file: str = ""
    extract_mode: str = ""


class VerbatSearchResponse(BaseModel):
    hits: List[VerbatHitOut]
    mode: str
    total: int


class SchemaMdResponse(BaseModel):
    schema_md: str


class SchemaMdUpdate(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Ingest pipeline (v2)
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Returned by POST /spaces/{slug}/files. Wiki generation is async."""

    job_id: str
    verbat_ids: List[str] = Field(default_factory=list)
    wiki_doc_ids: List[str] = Field(default_factory=list)  # partial, may fill in later


class IngestJobResponse(BaseModel):
    id: str
    space_slug: str
    source_file: str
    verbat_ids: List[str] = Field(default_factory=list)
    wiki_doc_ids: List[str] = Field(default_factory=list)
    status: str
    error: Optional[str] = None
    started_at: str
    finished_at: Optional[str] = None
    # Token usage aggregated from llm_call_log by job_id
    total_tokens: int = 0
    by_task: Dict[str, int] = Field(default_factory=dict)
    by_model: Dict[str, int] = Field(default_factory=dict)


class IngestJobListResponse(BaseModel):
    items: List[IngestJobResponse]


# ---------------------------------------------------------------------------
# LLM usage ledger (RFC-005)
# ---------------------------------------------------------------------------


class LlmUsageBucket(BaseModel):
    tokens: int = 0
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LlmUsageSummaryResponse(BaseModel):
    total_calls: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    by_task: Dict[str, LlmUsageBucket] = Field(default_factory=dict)
    by_model: Dict[str, LlmUsageBucket] = Field(default_factory=dict)


class LlmCallLogItem(BaseModel):
    id: str
    job_id: Optional[str] = None
    task_name: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    error_code: int = 0
    created_at: str


class LlmCallLogListResponse(BaseModel):
    items: List[LlmCallLogItem]


class CurateReportResponse(BaseModel):
    """Latest tier3 curate REPORT.md for a memory space (empty when absent)."""

    content: str = ""
    path: Optional[str] = None
    timestamp: Optional[str] = None


class LintIssueOut(BaseModel):
    rule: str  # orphan_doc | broken_wikilink | verbat_without_wiki | orphan_edge
    severity: str  # info | warning | error
    path: Optional[str] = None
    verbat_id: Optional[str] = None
    edge_id: Optional[str] = None
    message: str = ""


class LintResponse(BaseModel):
    issues: List[LintIssueOut]


class SetEmbedderRequest(BaseModel):
    """Force-set the embedder identity for a space (wipes vectors if mismatched)."""

    model_name: str
    dimension: int
    force_swap: bool = False


# ---------------------------------------------------------------------------
# Raw file CRUD (L0 manual editing)
# ---------------------------------------------------------------------------


class RawFileCreateRequest(BaseModel):
    path: str
    content: str


class RawFileEditRequest(BaseModel):
    content: str


class RawFileReadResponse(BaseModel):
    content: str


class SearchRequest(BaseModel):
    """Search request for /spaces/{slug}/search.

    mode:
    - "documents": FTS only (default; backward-compatible)
    - "references": edge-based backlink search
    - "semantic": vector recall only (requires embedder configured)
    - "hybrid": FTS + vector via reciprocal rank fusion
    - "graph": hybrid seeds + entity-graph expansion (RFC-005 Phase 3)
    """

    query: str
    mode: str = "documents"
    limit: int = 10
    include_invalid: bool = False  # graph mode: recall superseded/expired too


class DocHitOut(BaseModel):
    document_id: str
    path: str
    title: str
    type: str = ""
    score: float = 0.0
    snippet: str = ""
    verbats: List[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    hits: List[DocHitOut]
    mode: str
    total: int


__all__ = [
    "SpaceInfo",
    "CreateSpaceRequest",
    "UpdateSpaceRequest",
    "TreeNode",
    "DocReadResponse",
    "DocCreateRequest",
    "DocEditRequest",
    "DocListResponse",
    "EdgeOut",
    "SubgraphResponse",
    "VerbatOut",
    "VerbatListResponse",
    "VerbatHitOut",
    "VerbatSearchResponse",
    "SchemaMdResponse",
    "SchemaMdUpdate",
    "UploadResponse",
    "IngestJobResponse",
    "IngestJobListResponse",
    "LlmUsageBucket",
    "LlmUsageSummaryResponse",
    "LlmCallLogItem",
    "LlmCallLogListResponse",
    "CurateReportResponse",
    "LintIssueOut",
    "LintResponse",
    "SetEmbedderRequest",
    "SearchRequest",
    "DocHitOut",
    "SearchResponse",
    "RawFileCreateRequest",
    "RawFileEditRequest",
    "RawFileReadResponse",
]
