import { POST, GET, PATCH } from '..';

export const createWorkspace = (data: any) => POST('/api/v1/serve_workspace_service/workspaces/create', data);
export const getOrCreateHomeWorkspace = (data: { user_id: number }) =>
  POST('/api/v1/serve_workspace_service/workspaces/default-or-create', data);
export const listWorkspaces = (data: any) => POST('/api/v1/serve_workspace_service/workspaces/list', data);
export const getWorkspaceInfo = (workspace_code: string) => GET(`/api/v1/serve_workspace_service/workspaces/info?workspace_code=${encodeURIComponent(workspace_code)}`);
export const updateWorkspace = (data: any) => POST('/api/v1/serve_workspace_service/workspaces/update', data);
export const archiveWorkspace = (data: any) => POST('/api/v1/serve_workspace_service/workspaces/archive', data);

export const listMembers = (data: any) => POST('/api/v1/serve_workspace_service/members/list', data);
export const addMember = (data: any) => POST('/api/v1/serve_workspace_service/members/add', data);
export const removeMember = (data: any) => POST('/api/v1/serve_workspace_service/members/remove', data);
export const updateMemberRole = (data: any) => POST('/api/v1/serve_workspace_service/members/update_role', data);

export const listResources = (data: any) => POST('/api/v1/serve_workspace_service/resources/list', data);
export const addResource = (data: any) => POST('/api/v1/serve_workspace_service/resources/add', data);
export const removeResource = (data: any) => POST('/api/v1/serve_workspace_service/resources/remove', data);
export const updateResource = (data: any) => POST('/api/v1/serve_workspace_service/resources/update', data);

export const linkConversation = (data: any) => POST('/api/v1/serve_workspace_service/conversations/link', data);
export const listConversations = (data: any) => POST('/api/v1/serve_workspace_service/conversations/list', data);
export const lookupConversation = (conv_uid: string) => GET(`/api/v1/serve_workspace_service/conversations/lookup?conv_uid=${encodeURIComponent(conv_uid)}`);

export const createConversation = (data: { workspace_id?: number; task_id?: number; app_code?: string }) =>
  POST('/api/v1/chat/dialogue/new', data);

export const getCurrentConversation = (workspace_id: number) =>
  GET(`/api/v1/serve_workspace_service/workspaces/${workspace_id}/conversations/current`);

export const setCurrentConversation = (workspace_id: number, conv_uid: string) =>
  POST(`/api/v1/serve_workspace_service/workspaces/${workspace_id}/conversations/set-current`, { conv_uid });

export const renameConversation = (conv_uid: string, title: string) =>
  PATCH(`/api/v1/serve_workspace_service/conversations/${conv_uid}/rename`, { title });

export const resolveAndExecuteIntervention = (
  intervention_id: number,
  data: { decision: Record<string, any>; distillation?: Record<string, any>; resolved_by_user_id?: number; linked_asset_id?: number },
) => POST(`/api/v1/serve_intervention_service/interventions/${intervention_id}/resolve-and-execute`, data);

// ----------------------- Inbox(个人待办收件箱)-----------------------
export interface InboxItem {
  id: number;
  workspace_id: number;
  user_id: number;
  source_type: 'task' | 'intervention' | 'ecp_proposal' | 'manual' | string;
  source_id: string;
  title: string;
  summary?: string | null;
  inbox_status: 'unread' | 'doing' | 'done' | 'archived' | string;
  visibility: 'personal' | 'shared' | string;
  created_at: string;
  resolved_at?: string | null;
  gmt_created: string;
  gmt_modified: string;
}

export const listInbox = (
  workspace_id: number,
  params?: { status?: string; source_type?: string; limit?: number },
) => {
  const qs = new URLSearchParams();
  if (params?.status) qs.set('status', params.status);
  if (params?.source_type) qs.set('source_type', params.source_type);
  qs.set('limit', String(params?.limit ?? 100));
  return GET(`/api/v1/serve_workspace_service/workspaces/${workspace_id}/inbox?${qs.toString()}`);
};

export const resolveInbox = (
  workspace_id: number,
  data: { source_type: string; source_id: string; user_id?: number },
) => POST(`/api/v1/serve_workspace_service/workspaces/${workspace_id}/inbox/resolve`, data);

export const updateInboxStatus = (
  workspace_id: number,
  item_id: number,
  new_status: string,
) => POST(`/api/v1/serve_workspace_service/workspaces/${workspace_id}/inbox/${item_id}/status`, { new_status });

// ----------------------- Datasets(空间自持数据资产)-----------------------
export interface DatasetItem {
  id?: number;
  name?: string;
  display_name?: string;
  db_type?: string;
  file_name?: string;
  gmt_created?: string;
  [key: string]: any;
}

export const uploadDataset = (workspace_id: number, file: File, display_name?: string) => {
  const formData = new FormData();
  formData.append('file', file);
  if (display_name) formData.append('display_name', display_name);
  return POST<FormData, Record<string, any>>(
    `/api/v1/serve_workspace_service/workspaces/${workspace_id}/datasets/upload`,
    formData,
  );
};

export const listDatasets = (workspace_id: number) =>
  GET<null, DatasetItem[]>(`/api/v1/serve_workspace_service/workspaces/${workspace_id}/datasets`);
