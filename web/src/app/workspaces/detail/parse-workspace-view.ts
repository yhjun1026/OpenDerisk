import type { WorkspaceExecutionStep, WorkspaceView } from './agent-workspace-types';

const VALID_TYPES = ['tool_call', 'thinking', 'artifact', 'delivery', 'user'];
const VALID_STATUS = ['running', 'done', 'failed'];

function normalizeStep(raw: unknown): WorkspaceExecutionStep | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.id !== 'string' || typeof r.title !== 'string') return null;
  const type = VALID_TYPES.includes(r.type as string) ? (r.type as WorkspaceExecutionStep['type']) : 'tool_call';
  const status = VALID_STATUS.includes(r.status as string) ? (r.status as WorkspaceExecutionStep['status']) : 'running';
  return {
    id: r.id,
    type,
    title: r.title,
    status,
    ts: typeof r.ts === 'string' ? r.ts : null,
    action: typeof r.action === 'string' ? r.action : null,
    action_input: r.action_input && typeof r.action_input === 'object' ? (r.action_input as Record<string, unknown>) : null,
    output: typeof r.output === 'string' ? r.output : null,
    artifact: r.artifact && typeof r.artifact === 'object' ? (r.artifact as WorkspaceExecutionStep['artifact']) : null,
    vis: r.vis ?? null,
  };
}

/**
 * ts 归一化为毫秒数。服务端步骤是本地时间 naive ISO(可能带 6 位微秒或空格
 * 分隔),乐观用户步骤是 UTC ISO(带 Z);Date.parse 对 naive 按本地时区、
 * 带 Z 按 UTC 解析,两者可正确对齐。无法解析返回 null(排最后)。
 */
function tsToMs(ts: string | null | undefined): number | null {
  if (!ts) return null;
  let norm = ts.includes(' ') ? ts.replace(' ', 'T') : ts;
  // 微秒(>3 位小数)截断为毫秒,避免老引擎解析失败
  norm = norm.replace(/\.(\d{3})\d+/, '.$1');
  const ms = Date.parse(norm);
  return Number.isNaN(ms) ? null : ms;
}

export function parseWorkspaceView(chunk: unknown, prev: WorkspaceView | null): WorkspaceView {
  if (!chunk || typeof chunk !== 'object') return prev ?? { planning: null, execution: [], summary: null };
  const c = chunk as Record<string, unknown>;
  if (!Array.isArray(c.execution)) return prev ?? { planning: null, execution: [], summary: null };

  const prevById = new Map((prev?.execution ?? []).map(e => [e.id, e]));
  const execution: WorkspaceExecutionStep[] = [];
  for (const raw of c.execution) {
    const step = normalizeStep(raw);
    if (!step) continue;
    const existing = prevById.get(step.id);
    execution.push(existing ? { ...existing, ...step } : step);
    prevById.delete(step.id);
  }
  // 保留 prev 中未被本 chunk 覆盖的旧步骤(前轮 agent conv 的步骤)
  for (const leftover of prevById.values()) {
    execution.push(leftover);
  }
  // 跨轮次合并按时间戳交错(用户消息/工具/回复按真实时序排列);
  // 必须解析成毫秒再比:字符串直接比较会把 UTC(带 Z)和本地 naive 两种格式
  // 排错(时区偏移导致 user 气泡聚堆、当前步骤被埋进历史中间)。无 ts 排后。
  execution.sort((a, b) => {
    const ma = tsToMs(a.ts);
    const mb = tsToMs(b.ts);
    if (ma === null && mb === null) return 0;
    if (ma === null) return 1;
    if (mb === null) return -1;
    return ma - mb;
  });

  const planning = c.planning && typeof c.planning === 'object'
    ? (c.planning as WorkspaceView['planning'])
    : (prev?.planning ?? null);
  const summary = typeof c.summary === 'string' ? c.summary : (prev?.summary ?? null);

  return { planning, execution, summary };
}