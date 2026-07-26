/**
 * LLM Usage (token/cost) Dashboard API Client
 * 对应后端 /api/v1/serve/usage/*
 */

import { DELETE, GET } from '../index';

// =============================================================================
// Types
// =============================================================================

export interface UsageCall {
  id: number;
  conv_id?: string;
  agent_id?: string;
  user_id?: string;
  session_id?: string;
  trace_id?: string;
  model_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  first_token_ms?: number | null;
  tokens_per_sec?: number | null;
  stream: number;
  error_code: number;
  cost_usd: number;
  started_at: number;
  gmt_created?: string | null;
}

export interface UsageOverview {
  total_calls: number;
  error_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_latency_ms?: number | null;
  avg_tokens_per_sec?: number | null;
}

export interface ConversationUsage {
  conv_id: string;
  agent_id?: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_latency_ms?: number | null;
  avg_tokens_per_sec?: number | null;
  error_calls: number;
}

export interface AgentUsage {
  agent_id: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_latency_ms?: number | null;
  avg_tokens_per_sec?: number | null;
  error_calls: number;
}

export interface ModelUsage {
  model_name: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_latency_ms?: number | null;
  avg_tokens_per_sec?: number | null;
  error_calls: number;
}

export interface TimeSeriesPoint {
  bucket_ms: number;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface UsageListResult {
  items: UsageCall[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface UsageFilters {
  conv_id?: string;
  agent_id?: string;
  model_name?: string;
  start_ms?: number;
  end_ms?: number;
}

// =============================================================================
// API endpoints
// =============================================================================

const API_PREFIX = '/api/v1/serve/usage';

export const getUsageOverview = (params: UsageFilters = {}) =>
  GET<UsageFilters, UsageOverview>(`${API_PREFIX}/overview`, params);

export const listUsageCalls = (
  params: UsageFilters & { page?: number; page_size?: number } = {}
) =>
  GET<UsageFilters & { page?: number; page_size?: number }, UsageListResult>(
    `${API_PREFIX}/calls`,
    params
  );

export const getUsageByConversation = (params: UsageFilters = {}) =>
  GET<UsageFilters, ConversationUsage[]>(`${API_PREFIX}/by-conversation`, params);

export const getUsageByAgent = (params: UsageFilters = {}) =>
  GET<UsageFilters, AgentUsage[]>(`${API_PREFIX}/by-agent`, params);

export const getUsageByModel = (params: UsageFilters = {}) =>
  GET<UsageFilters, ModelUsage[]>(`${API_PREFIX}/by-model`, params);

export const getUsageTimeSeries = (
  params: UsageFilters & { start_ms: number; end_ms: number; bucket_sec: number }
) =>
  GET<
    UsageFilters & { start_ms: number; end_ms: number; bucket_sec: number },
    TimeSeriesPoint[]
  >(`${API_PREFIX}/time-series`, params);

export const deleteUsageRecords = (
  params: { conv_id?: string; before_ms?: number }
) => DELETE<{ conv_id?: string; before_ms?: number }, { deleted: number }>(
  `${API_PREFIX}/records`,
  params
);
