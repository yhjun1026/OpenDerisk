export interface WorkspaceArtifact {
  file_path: string;
  mime_type?: string;
  preview_url?: string;
}

export interface WorkspaceExecutionStep {
  id: string;
  type: 'tool_call' | 'thinking' | 'artifact' | 'delivery' | 'user';
  title: string;
  status: 'running' | 'done' | 'failed';
  /** 时间戳(ISO 字符串),跨轮次合并时按此交错排序 */
  ts?: string | null;
  action?: string | null;
  action_input?: Record<string, unknown> | null;
  output?: string | null;
  artifact?: WorkspaceArtifact | null;
  vis?: unknown;
}

export interface WorkspacePlanning {
  goal: string;
  steps: { id: string; title: string; status: 'pending' | 'running' | 'done' | 'failed' }[];
}

export interface WorkspaceView {
  planning: WorkspacePlanning | null;
  execution: WorkspaceExecutionStep[];
  summary: string | null;
}

export interface PlaybookCommand {
  playbook_id: number;
  playbook_name: string;
}

export interface AgentWorkspaceInputHandle {
  focus: () => void;
  insertText: (text: string) => void;
}