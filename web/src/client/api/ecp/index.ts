/**
 * ECP (Enterprise Context Protocol) 语义资产 API Client
 * 对应后端 /api/v1/serve/ecp/*
 */

import { GET, POST, PUT, DELETE } from '../index';

// =============================================================================
// Types
// =============================================================================

export interface EcpSemanticObject {
  id: string;
  version: number;
  workspace_id: string;
  obj_type: 'entity' | 'metric' | 'relation' | 'dimension' | 'claim' | 'terminology' | 'policy';
  status: 'proposed' | 'confirmed' | 'rejected' | 'deprecated' | 'superseded';
  name?: string | null;
  payload: Record<string, any>;
  confidence?: number | null;
  evidence?: Array<{ source?: string; quote?: string }> | null;
  created_by: string;
  created_at?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  source?: string | null;
  supersedes?: number | null;
}

export interface EcpObjectListResult {
  items: EcpSemanticObject[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface EcpCatalogEntry {
  id: string;
  obj_type: string;
  name?: string | null;
  aliases: string[];
  one_line?: string | null;
  grain?: string[] | null;
}

export interface EcpConfirmer {
  id: number;
  workspace_id: string;
  user_id: string;
  scope?: string | null;
}

export interface EcpOpLogEntry {
  id: number;
  workspace_id: string;
  ts?: string | null;
  op: string;
  detail?: Record<string, any> | null;
}

export interface EcpObjectFilters {
  workspace_id?: string;
  obj_type?: string;
  status?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

// =============================================================================
// API
// =============================================================================

const API_PREFIX = '/api/v1/serve/ecp';

export const getEcpInbox = (params: EcpObjectFilters) =>
  GET<EcpObjectFilters, EcpObjectListResult>(`${API_PREFIX}/inbox`, params);

export const listEcpObjects = (params: EcpObjectFilters) =>
  GET<EcpObjectFilters, EcpObjectListResult>(`${API_PREFIX}/objects`, params);

export const getEcpObject = (id: string, workspace_id?: string) =>
  GET<{ workspace_id?: string }, EcpSemanticObject>(
    `${API_PREFIX}/objects/${encodeURIComponent(id)}`,
    { workspace_id },
  );

export const getEcpObjectVersions = (id: string, workspace_id?: string) =>
  GET<{ workspace_id?: string }, EcpSemanticObject[]>(
    `${API_PREFIX}/objects/${encodeURIComponent(id)}/versions`,
    { workspace_id },
  );

export const confirmEcpObject = (
  id: string,
  version: number,
  data: { user_id: string; workspace_id?: string; edited_payload?: Record<string, any> },
) =>
  POST<typeof data, EcpSemanticObject>(
    `${API_PREFIX}/objects/${encodeURIComponent(id)}/versions/${version}/confirm`,
    data,
  );

export const rejectEcpObject = (
  id: string,
  version: number,
  data: { user_id: string; workspace_id?: string; reason?: string },
) =>
  POST<typeof data, EcpSemanticObject>(
    `${API_PREFIX}/objects/${encodeURIComponent(id)}/versions/${version}/reject`,
    data,
  );

export const deprecateEcpObject = (
  id: string,
  data: { user_id: string; workspace_id?: string; reason?: string },
) =>
  POST<typeof data, EcpSemanticObject>(
    `${API_PREFIX}/objects/${encodeURIComponent(id)}/deprecate`,
    data,
  );

export const getEcpCatalog = (params?: { workspace_id?: string; keyword?: string }) =>
  GET<typeof params, EcpCatalogEntry[]>(`${API_PREFIX}/catalog`, params);

export const generateEcpProposals = (data: {
  datasource_id?: number;
  workspace_id?: string;
  table_names?: string[];
  max_tables?: number;
  domain_hint?: string;
}) =>
  POST<typeof data, {
    datasource_id: number;
    tables_processed: number;
    proposals_created: number;
    proposal_ids: string[];
    errors: string[];
  }>(`${API_PREFIX}/proposals/generate`, data);

export const listEcpConfirmers = (workspace_id?: string) =>
  GET<{ workspace_id?: string }, EcpConfirmer[]>(`${API_PREFIX}/confirmers`, {
    workspace_id,
  });

export const addEcpConfirmer = (data: {
  user_id: string;
  workspace_id?: string;
  scope?: string;
}) => POST<typeof data, boolean>(`${API_PREFIX}/confirmers`, data);

export const removeEcpConfirmer = (id: number) =>
  DELETE<Record<string, never>, boolean>(`${API_PREFIX}/confirmers/${id}`);

export const getEcpOpLog = (params: {
  workspace_id?: string;
  op?: string;
  page?: number;
  page_size?: number;
}) => GET<typeof params, EcpOpLogEntry[]>(`${API_PREFIX}/op-log`, params);

// =============================================================================
// Asset refs / readiness / graph / space
// =============================================================================

export interface EcpAssetRef {
  id: number;
  workspace_id: string;
  kind: 'db' | 'document' | 'space' | 'api';
  ref_id: string;
  ref_meta: Record<string, any>;
  status: string;
  last_checked_at?: string | null;
}

export interface EcpReadinessCheck {
  item: string;
  ready: boolean;
  detail?: string | null;
}

export interface EcpReadiness {
  kind: string;
  ref_id: string;
  ready: boolean;
  checks: EcpReadinessCheck[];
}

export interface EcpGraphNode {
  id: string;
  obj_type: string;
  name?: string | null;
  status: string;
  version: number;
}

export interface EcpGraphLink {
  source: string;
  target: string;
  edge_type: string;
  status?: string | null;
}

export interface EcpGraph {
  nodes: EcpGraphNode[];
  links: EcpGraphLink[];
}

export interface EcpSpaceInfo {
  slug: string;
  workspace_id: string;
  created: boolean;
}

export const registerEcpAsset = (data: {
  kind: string;
  ref_id: string;
  workspace_id?: string;
  ref_meta?: Record<string, any>;
}) => POST<typeof data, EcpAssetRef>(`${API_PREFIX}/assets`, data);

export const listEcpAssets = (params?: { workspace_id?: string; kind?: string }) =>
  GET<typeof params, EcpAssetRef[]>(`${API_PREFIX}/assets`, params);

export const getEcpReadiness = (datasource_id: number, workspace_id?: string) =>
  GET<{ datasource_id: number; workspace_id?: string }, EcpReadiness>(
    `${API_PREFIX}/readiness`,
    { datasource_id, workspace_id },
  );

export const getEcpGraph = (workspace_id?: string) =>
  GET<{ workspace_id?: string }, EcpGraph>(`${API_PREFIX}/graph`, { workspace_id });

export const getOrCreateEcpSpace = (workspace_id?: string) =>
  POST<Record<string, never>, EcpSpaceInfo>(
    `${API_PREFIX}/space${workspace_id ? `?workspace_id=${encodeURIComponent(workspace_id)}` : ''}`,
    {},
  );

// =============================================================================
// Workspace config (proposal agent settings)
// =============================================================================

export interface EcpWorkspaceConfig {
  workspace_id: string;
  proposal_agent_id?: string | null;
}

export const getEcpWorkspaceConfig = (workspace_id?: string) =>
  GET<{ workspace_id?: string }, EcpWorkspaceConfig>(
    `${API_PREFIX}/workspace-config`,
    { workspace_id },
  );

export const saveEcpWorkspaceConfig = (data: Partial<EcpWorkspaceConfig>) =>
  PUT<typeof data, EcpWorkspaceConfig>(`${API_PREFIX}/workspace-config`, data);

export interface EcpLinkedResource {
  datasource_id: number;
  db_name: string;
  db_type: string;
}

export const getEcpLinkedResources = (workspace_id?: string) =>
  GET<{ workspace_id?: string }, EcpLinkedResource[]>(
    `${API_PREFIX}/linked-resources`,
    { workspace_id },
  );

// =============================================================================
// Admin: contract check / normalize / miss flywheel
// =============================================================================

export interface EcpMissCluster {
  datasource_id?: number | null;
  pattern: string;
  count: number;
  example_sql: string;
  reasonings: string[];
  last_seen?: string | null;
}

export interface EcpMissReport {
  workspace_id: string;
  total_fallbacks: number;
  cluster_count: number;
  clusters: EcpMissCluster[];
}

export interface EcpContractCheck {
  workspace_id: string;
  total: number;
  non_compliant_count: number;
  non_compliant: Array<{
    id: string;
    obj_type: string;
    version: number;
    problems: string[];
  }>;
}

export const getEcpMissReport = (params?: { workspace_id?: string; limit?: number }) =>
  GET<typeof params, EcpMissReport>(`${API_PREFIX}/admin/miss_report`, params);

export const learnEcpFromMisses = (params?: { workspace_id?: string; top?: number }) =>
  POST<Record<string, never>, {
    datasource_id: number;
    tables_processed: number;
    proposals_created: number;
    proposal_ids: string[];
    errors: string[];
  }>(
    `${API_PREFIX}/admin/learn_from_misses${params?.workspace_id ? `?workspace_id=${encodeURIComponent(params.workspace_id)}` : ''}${params?.top ? `${params?.workspace_id ? '&' : '?'}top=${params.top}` : ''}`,
    {},
  );

export const getEcpContractCheck = (workspace_id?: string) =>
  GET<{ workspace_id?: string }, EcpContractCheck>(`${API_PREFIX}/admin/contract_check`, {
    workspace_id,
  });

export const normalizeEcpConfirmed = (workspace_id?: string) =>
  POST<Record<string, never>, {
    workspace_id: string;
    checked: number;
    fixed: Array<{ id: string; version: number }>;
    skipped: Array<{ id: string; problems: string[] }>;
  }>(
    `${API_PREFIX}/admin/normalize${workspace_id ? `?workspace_id=${encodeURIComponent(workspace_id)}` : ''}`,
    {},
  );
