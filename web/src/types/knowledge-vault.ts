/**
 * Types for the new knowledge-vault frontend (three-layer model: L0/L1/L2).
 *
 * Backend: derisk_serve.knowledge HTTP API at /api/v1/serve/knowledge.
 */

export type SpaceVisibility = 'private' | 'shared' | 'public';

export type SpaceType = 'personal' | 'agent_memory';

export interface SpaceInfo {
  slug: string;
  root: string;
  backend?: 'local' | 'distributed' | null;
  // v2 ingest pipeline config (RFC 004 §6). All optional.
  default_agent_id?: string | null;
  llm_model?: string | null;
  multimodal_model?: string | null;
  embedder_model?: string | null;
  // Access control (owner_id empty/null = legacy world-accessible space)
  visibility?: SpaceVisibility | null;
  owner_id?: string | null;
  space_type?: SpaceType | null;
  // v5 retrieval tuning (both default off)
  rerank_model?: string | null;
  embed_verbats?: boolean | null;
}

export interface UpdateSpaceRequest {
  default_agent_id?: string | null;
  llm_model?: string | null;
  multimodal_model?: string | null;
  embedder_model?: string | null;
  rerank_model?: string | null;
  embed_verbats?: boolean | null;
}

export interface CreateSpaceRequest {
  slug: string;
  backend?: 'local' | 'distributed' | null;
  default_agent_id?: string | null;
  llm_model?: string | null;
  multimodal_model?: string | null;
  embedder_model?: string | null;
  rerank_model?: string | null;
  embed_verbats?: boolean | null;
  visibility?: SpaceVisibility | null;
  space_type?: SpaceType | null;
}

export interface IngestJob {
  id: string;
  space_slug: string;
  source_file: string;
  verbat_ids: string[];
  wiki_doc_ids: string[];
  status: 'pending' | 'extracting' | 'embedding' | 'generating_wiki' | 'done' | 'failed';
  error?: string | null;
  started_at: string;
  finished_at?: string | null;
  /** Token usage aggregated from the llm_call_log ledger by job_id. */
  total_tokens: number;
  by_task: Record<string, number>;
  by_model: Record<string, number>;
}

export interface IngestJobListResponse {
  items: IngestJob[];
}

export type LlmUsageBucket = {
  tokens: number;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
};

export interface LlmUsageSummary {
  total_calls: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  by_task: Record<string, LlmUsageBucket>;
  by_model: Record<string, LlmUsageBucket>;
}

export interface UploadResponse {
  job_id: string;
  verbat_ids: string[];
  wiki_doc_ids: string[];
}

export type LintRule =
  | 'orphan_doc'
  | 'broken_wikilink'
  | 'verbat_without_wiki'
  | 'stale_edge'
  | 'frontmatter_missing'
  | 'contradiction';

export interface LintIssue {
  rule: LintRule | string;
  severity: 'info' | 'warning' | 'error';
  path?: string | null;
  verbat_id?: string | null;
  edge_id?: string | null;
  message: string;
}

export interface LintResponse {
  issues: LintIssue[];
}

export interface TreeNode {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number | null;
  children?: TreeNode[] | null;
}

export interface DocMeta {
  id: string;
  path: string;
  type: string;
  title: string;
  status: string;
}

export interface DocRead {
  id: string;
  path: string;
  type: string;
  title: string;
  frontmatter: Record<string, unknown>;
  content: string;
  version: number;
}

export interface EdgeOut {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  valid_from?: string | null;
  valid_to?: string | null;
  source_document_id?: string | null;
  weight: number;
}

export interface Subgraph {
  nodes: string[];
  edges: EdgeOut[];
  root?: string | null;
}

export type ExtractMode = 'mine' | 'clip' | 'upload' | 'convo' | 'legacy_chunk';

export interface VerbatOut {
  id: string;
  source_file: string;
  extract_mode: ExtractMode;
  deprecated: boolean;
  content_preview?: string | null;
  content_date?: string | null;
  filed_at?: string | null;
  /** 记忆元数据 (author/user_id/conv_id/turn_round 等) */
  metadata?: Record<string, unknown> | null;
}

export interface VerbatFull {
  id: string;
  source_file: string;
  extract_mode: ExtractMode;
  content: string;
  deprecated: boolean;
  filed_at?: string | null;
}

export interface VerbatListResponse {
  items: VerbatOut[];
}

export interface SchemaMdResponse {
  schema_md: string;
}

export interface RawFileCreateRequest {
  path: string;
  content: string;
}

export interface RawFileEditRequest {
  content: string;
}

export type DocSearchMode = 'documents' | 'semantic' | 'hybrid' | 'references';

/** L0 verbat search mode (requires spaces.embed_verbats for semantic/hybrid). */
export type VerbatSearchMode = 'keyword' | 'semantic' | 'hybrid';

export interface VerbatHit {
  verbat_id: string;
  score: number;
  snippet: string;
  source_file: string;
  extract_mode: string;
}

export interface VerbatSearchResponse {
  hits: VerbatHit[];
  mode: string;
  total: number;
}

export interface DocHit {
  document_id: string;
  path: string;
  title: string;
  type: string;
  score: number;
  snippet: string;
  verbats: string[];
}

export interface SearchRequest {
  query: string;
  mode: DocSearchMode;
  limit?: number;
}

export interface SearchResponse {
  hits: DocHit[];
  mode: DocSearchMode;
  total: number;
}

export interface CurateReport {
  content: string;
  path?: string | null;
  timestamp?: string | null;
}
