'use client';

import { useEffect, useMemo, useState } from 'react';
import { App, Button, Dropdown, Form, Input, Modal } from 'antd';
import { CheckOutlined, CommentOutlined, LinkOutlined, MoreOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { apiInterceptors, createAsset, resolveAndExecuteIntervention, abortIntervention, terminateTask, deleteTask, reassignTask } from '@/client/api';
import { listInbox, updateInboxStatus, listMembers, type InboxItem } from '@/client/api/workspace';
import { getUserId } from '@/utils';

export type TaskTabKey = 'all' | 'running' | 'awaiting' | 'done' | 'failed';

/** 每次渲染的卡片数,避免任务多了一次渲染全部导致卡顿 */
const PAGE_SIZE = 20;

/** 时间分段标签:今天/昨天/本周/更早(列表已按 updatedAt 倒序) */
function segLabel(iso: string): string {
  const d = dayjs(iso);
  const now = dayjs();
  if (d.isSame(now, 'day')) return '今天';
  if (d.isSame(now.subtract(1, 'day'), 'day')) return '昨天';
  if (d.isAfter(now.startOf('week'))) return '本周';
  return '更早';
}

const TRIGGER_LABEL: Record<string, string> = {
  manual: '手动',
  timer: '定时',
  webhook: 'Webhook',
  alert: '告警',
};

const INBOX_SOURCE_LABEL: Record<string, string> = {
  task: '任务',
  intervention: '介入',
  ecp_proposal: '提案',
  manual: '手动',
};

/**
 * 解析 ECP 提案待办的 source_id -> {workspaceId, objId, version}。
 *
 * source_id 由后端 ecp_sync 构造为 `f"{ecp_ws}:{obj.id}@v{version}"`
 * (见 workspace/inbox/ecp_sync.py:_desired_proposals),已编码派生 ECP
 * workspace、提案 id 与版本,故场景空间就地确认无需额外传 workspace_code。
 * 解析失败返回 null(降级为不开抽屉,不阻塞)。
 */
export function parseEcpProposalSource(sourceId: string): { workspaceId: string; objId: string; version: number } | null {
  const m = sourceId.match(/^(.+):(.+)@v(\d+)$/);
  if (!m) return null;
  return { workspaceId: m[1], objId: m[2], version: Number(m[3]) };
}

function triggerLabel(task: any): string {
  return TRIGGER_LABEL[task?.triggered_by] || task?.triggered_by || '手动';
}

export { triggerLabel };

export function statusToTab(status: string | undefined): TaskTabKey {
  switch (status) {
    case 'running':
    case 'pending_trigger':
    case 'blocked':
    case 'draft':
      return 'running';
    case 'awaiting_human':
      return 'awaiting';
    case 'delivered':
    case 'closed':
      return 'done';
    case 'failed':
      return 'failed';
    default:
      return 'all';
  }
}

export function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'running': return '运行中';
    case 'pending_trigger': return '等待触发';
    case 'blocked': return '阻塞';
    case 'draft': return '准备中';
    case 'awaiting_human': return '待你介入';
    case 'delivered': return '已交付';
    case 'closed': return '已关闭';
    case 'failed': return '失败';
    default: return status || '未知';
  }
}

const TAB_LABEL: Record<TaskTabKey, string> = {
  all: '全部',
  running: '运行中',
  awaiting: '待介入',
  done: '已完成',
  failed: '失败',
};

const TAB_CLASS: Record<TaskTabKey, string> = {
  all: 'ws-rail-tab--all',
  running: 'ws-rail-tab--running',
  awaiting: 'ws-rail-tab--awaiting',
  done: 'ws-rail-tab--done',
  failed: 'ws-rail-tab--failed',
};

/** 介入 question -> 展示文本(string / {question|message|summary} / JSON 兜底) */
function questionToText(q: any): string {
  if (!q) return '';
  if (typeof q === 'string') return q;
  if (q.question || q.message || q.summary) return q.question || q.message || q.summary;
  try {
    return JSON.stringify(q);
  } catch {
    return '';
  }
}

function ElapsedTimer({ task }: { task: any }) {
  const [, force] = useState(0);
  useEffect(() => {
    if (!task?.started_at || task.status !== 'running') return;
    const t = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [task?.started_at, task?.status]);
  if (!task?.started_at || task.status !== 'running') return <></>;
  const secs = Math.max(0, Math.floor((Date.now() - dayjs(task.started_at).valueOf()) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return <span className="ws-rail-elapsed">{`已耗时 ${m}m${String(s).padStart(2, '0')}s`}</span>;
}

export interface SceneTaskRailProps {
  tasks: any[];
  interventions: any[];
  workspaceId?: number;
  activeTaskId?: number | null;
  disabled?: boolean;
  playbooks?: { playbook_id: number; playbook_name: string }[];
  onPreview: (item: any, kind: 'task' | 'intervention' | 'ecp_proposal') => void;
  onEnterConversation: (taskId: number) => void;
  onReference?: (task: any) => void;
  onRefreshLists?: () => void;
  /** 收件箱刷新信号:变更时重新拉待办(中间区域确认/否决提案后由 shell bump)。 */
  inboxTick?: number;
  /** 会话维度列表(workspace conversations),按会话展示每次对话记录。 */
  conversations?: any[];
  /** 当前会话 conv_uid(大厅=workspaceConvUid,任务=taskConvUid),用于列表高亮。 */
  currentConvUid?: string;
  /** 点击会话卡片进入对应对话:taskId 非空进任务对话,空进大厅会话(回 dashboard)。 */
  onOpenConversation?: (convUid: string, taskId: number | null) => void;
}

export function SceneTaskRail({
  tasks,
  interventions,
  workspaceId,
  activeTaskId,
  disabled,
  playbooks,
  onPreview,
  onEnterConversation,
  onReference,
  onRefreshLists,
  inboxTick,
  conversations,
  currentConvUid,
  onOpenConversation,
}: SceneTaskRailProps) {
  const { message, modal } = App.useApp();
  const [view, setView] = useState<'inbox' | 'tasks'>('inbox');
  const [inboxItems, setInboxItems] = useState<InboxItem[]>([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const [inboxSource, setInboxSource] = useState<string>('all');

  const refreshInbox = async () => {
    if (!workspaceId) return;
    setInboxLoading(true);
    const [err, res] = await apiInterceptors(listInbox(workspaceId));
    setInboxLoading(false);
    if (err) return;
    const items = Array.isArray(res) ? res : ((res as any)?.data || []);
    setInboxItems(items);
  };

  useEffect(() => { refreshInbox(); }, [workspaceId]);

  // 中间区域确认/否决 ECP 提案后 shell bump inboxTick -> 重新拉待办。
  useEffect(() => {
    if (inboxTick && inboxTick > 0) refreshInbox();
  }, [inboxTick]);

  const handleInboxClick = (item: InboxItem) => {
    if (item.source_type === 'task') {
      onEnterConversation(Number(item.source_id));
    } else if (item.source_type === 'intervention') {
      onPreview(
        { id: Number(item.source_id), question: { message: item.title }, status: 'requested' },
        'intervention',
      );
    } else if (item.source_type === 'ecp_proposal') {
      // 在中间内容区域打开提案确认(source_id 已编码 ecp workspace + 提案 id + 版本,
      // 见 parseEcpProposalSource),与点任务一样走 onPreview -> detailContext。
      onPreview(item, 'ecp_proposal');
    }
  };

  const handleInboxDone = async (item: InboxItem, e: any) => {
    e?.stopPropagation?.();
    if (!workspaceId) return;
    const [err] = await apiInterceptors(updateInboxStatus(workspaceId, item.id, 'done'));
    if (err) { message.error(err.message); return; }
    message.success('已标记完成');
    refreshInbox();
  };

  // ---------------- 任务转交 ----------------
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferTaskId, setTransferTaskId] = useState<number | null>(null);
  const [members, setMembers] = useState<any[]>([]);
  const [transferring, setTransferring] = useState(false);

  const handleTransferOpen = async (taskId: number, wsId: number) => {
    setTransferTaskId(taskId);
    setTransferOpen(true);
    const [err, res] = await apiInterceptors(listMembers({ workspace_id: wsId }));
    if (err) { message.error(err.message); return; }
    const list = Array.isArray(res) ? res : ((res as any)?.data || []);
    setMembers(list);
  };

  const handleTransferSubmit = async (userId: number) => {
    if (!transferTaskId) return;
    setTransferring(true);
    const [err] = await apiInterceptors(reassignTask(transferTaskId, userId));
    setTransferring(false);
    if (err) { message.error(err.message); return; }
    message.success('已转交');
    setTransferOpen(false);
    refreshInbox();
    onRefreshLists?.();
  };

  const [filter, setFilter] = useState('');
  const [tab, setTab] = useState<TaskTabKey>('all');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [resolveOpen, setResolveOpen] = useState<any | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 切换 tab/搜索时回到第一页
  useEffect(() => setVisibleCount(PAGE_SIZE), [tab, filter]);

  const pbNameById = useMemo(() => {
    const m = new Map<number, string>();
    (playbooks || []).forEach((p) => m.set(p.playbook_id, p.playbook_name));
    return m;
  }, [playbooks]);

  // 介入按 task_id 挂到对应任务下(介入是任务 awaiting_human 状态的附属请求,不再与任务平级)
  const interventionsByTask = useMemo(() => {
    const m = new Map<number, any[]>();
    (interventions || []).forEach((i) => {
      if (i.task_id != null) {
        const arr = m.get(i.task_id) || [];
        arr.push(i);
        m.set(i.task_id, arr);
      }
    });
    return m;
  }, [interventions]);

  const taskItems = useMemo(
    () => (tasks || []).map((t) => ({
      kind: 'task' as const,
      raw: t,
      interventions: interventionsByTask.get(t.id) || [],
      updatedAt: t.gmt_modified || t.gmt_created || t.updated_at || new Date().toISOString(),
    })),
    [tasks, interventionsByTask],
  );

  // 孤立介入:task_id 为空,或关联的 task 不在当前列表(已归档/超出 limit)
  const orphanItems = useMemo(
    () => (interventions || [])
      .filter((i) => i.task_id == null || !tasks.some((t) => t.id === i.task_id))
      .map((i) => ({
        kind: 'orphan-intervention' as const,
        raw: i,
        updatedAt: i.updated_at || i.created_at || i.gmt_modified || new Date().toISOString(),
      })),
    [interventions, tasks],
  );

  // 大厅会话:conversations 中 task_id 为空的(workspace 级对话)。
  // 任务≈会话(task 创建即建 conv),不再单列会话栏;这里把大厅会话混排进任务视图,
  // 按 gmt_modified 倒序与任务统一展示,用类型 chip 区分剧本/大厅。
  const lobbyConvItems = useMemo(
    () => (conversations || [])
      .filter((c) => c.task_id == null)
      .map((c) => ({
        kind: 'lobby-conversation' as const,
        raw: c,
        updatedAt: c.gmt_modified || c.gmt_created || new Date().toISOString(),
      })),
    [conversations],
  );

  const merged = useMemo(
    () => [...taskItems, ...lobbyConvItems, ...orphanItems].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    ),
    [taskItems, lobbyConvItems, orphanItems],
  );

  const counts = useMemo(() => {
    const c: Record<TaskTabKey, number> = { all: 0, running: 0, awaiting: 0, done: 0, failed: 0 };
    taskItems.forEach((it) => {
      c.all += 1;
      const tb = statusToTab(it.raw.status);
      if (tb !== 'all') c[tb] += 1;
    });
    // 大厅会话计入 all(剧本/大厅统一计数,无状态归 all)
    lobbyConvItems.forEach(() => { c.all += 1; });
    // 孤立介入计入 all + awaiting(仍需人响应)
    orphanItems.forEach(() => { c.all += 1; c.awaiting += 1; });
    return c;
  }, [taskItems, lobbyConvItems, orphanItems]);

  const activeCount = counts.running + counts.awaiting;

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return merged.filter((it) => {
      if (it.kind === 'task') {
        if (tab !== 'all' && statusToTab(it.raw.status) !== tab) return false;
      } else if (it.kind === 'lobby-conversation') {
        // 大厅会话只在 all 显示(无运行状态,不归入各状态 tab)
        if (tab !== 'all') return false;
      } else {
        // 孤立介入只在 all / awaiting 显示
        if (tab !== 'all' && tab !== 'awaiting') return false;
      }
      if (!q) return true;
      if (it.kind === 'task') {
        const title = it.raw.title || `task_${it.raw.id}`;
        const intQ = it.interventions.map((i: any) => questionToText(i.question)).join(' ');
        return title.toLowerCase().includes(q) || String(it.raw.id).includes(q) || intQ.toLowerCase().includes(q);
      }
      if (it.kind === 'lobby-conversation') {
        const title = it.raw.title || '';
        return title.toLowerCase().includes(q)
          || String(it.raw.conv_uid || '').toLowerCase().includes(q);
      }
      const t = questionToText(it.raw.question) || `intervention_${it.raw.id}`;
      return t.toLowerCase().includes(q) || String(it.raw.id).includes(q);
    });
  }, [merged, tab, filter]);

  // 渐进渲染 + 时间分段:在 visible 窗口内插入段头(数据已按 updatedAt 倒序)
  const grouped = useMemo(() => {
    const shown = filtered.slice(0, visibleCount);
    const rows: Array<{ type: 'seg'; label: string } | { type: 'item'; item: (typeof shown)[number] }> = [];
    let last = '';
    shown.forEach((item) => {
      const seg = segLabel(item.updatedAt);
      if (seg !== last) {
        rows.push({ type: 'seg', label: seg });
        last = seg;
      }
      rows.push({ type: 'item', item });
    });
    return rows;
  }, [filtered, visibleCount]);

  const handleTerminate = (id: number) => {
    modal.confirm({
      title: '终止任务',
      content: '会停止对应 Agent 的运行,任务标记为已关闭。',
      okText: '终止',
      okButtonProps: { danger: true },
      onOk: async () => {
        const [err] = await apiInterceptors(terminateTask(id));
        if (err) { message.error(err.message); return; }
        message.success('已终止');
        onRefreshLists?.();
      },
    });
  };

  const handleDelete = (id: number) => {
    modal.confirm({
      title: '删除任务',
      content: '删除后任务记录不可恢复(运行中/待介入的任务需先终止)。',
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        const [err] = await apiInterceptors(deleteTask(id));
        if (err) { message.error(err.message); return; }
        message.success('已删除');
        onRefreshLists?.();
      },
    });
  };

  const handleAbort = async (id: number) => {
    const [err] = await apiInterceptors(abortIntervention(id));
    if (err) { message.error(err.message); return; }
    message.success('已中止');
    onRefreshLists?.();
  };

  const handleResolve = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const [errAsset, assetRes] = await apiInterceptors(createAsset({
        workspace_id: workspaceId,
        type: values.asset_type || 'historical_artifact',
        name: values.asset_name,
        description: values.summary,
        scope: 'workspace',
        content_text: values.summary,
        source_task_id: resolveOpen?.task_id,
        is_published: true,
        created_by: 'reviewer',
      }));
      if (errAsset) { setSaving(false); message.error(errAsset.message); return; }
      const userId = getUserId();
      const [err] = await apiInterceptors(resolveAndExecuteIntervention(resolveOpen!.id, {
        decision: { action: 'approved', comment: values.decision },
        distillation: {
          asset_name: values.asset_name,
          summary: values.summary,
          asset_id: assetRes?.id,
        },
        linked_asset_id: assetRes?.id,
        resolved_by_user_id: userId ? Number(userId) : undefined,
      }));
      setSaving(false);
      if (err) { message.error(err.message); return; }
      message.success('已响应 + 沉淀资产');
      setResolveOpen(null);
      form.resetFields();
      onRefreshLists?.();
    } catch {
      // 表单校验失败等,静默
    }
  };

  const renderInterventionSub = (iv: any) => (
    <div className="ws-rail-intervention" key={iv.id}>
      <span className="ws-rail-int-question">{questionToText(iv.question) || `介入 #${iv.id}`}</span>
      {iv.status === 'requested' ? (
        <div className="ws-rail-int-actions">
          <Button size="small" type="primary" onClick={(e) => { e.stopPropagation(); setResolveOpen(iv); form.resetFields(); }}>响应</Button>
          <Button size="small" danger onClick={(e) => { e.stopPropagation(); handleAbort(iv.id); }}>中止</Button>
        </div>
      ) : (
        <span className="ws-rail-int-status">{iv.status}{iv.resolved_at ? ` · ${dayjs(iv.resolved_at).format('MM-DD HH:mm')}` : ''}</span>
      )}
    </div>
  );

  return (
    <div className="ws-scene-task-rail">
      <div className="ws-rail-view-switch">
        <span
          className={`ws-rail-view-tab${view === 'inbox' ? ' ws-rail-view-tab--on' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => setView('inbox')}
          onKeyDown={(e) => { if (e.key === 'Enter') setView('inbox'); }}
        >
          待办{inboxItems.length > 0 ? ` ${inboxItems.length}` : ''}
        </span>
        <span
          className={`ws-rail-view-tab${view === 'tasks' ? ' ws-rail-view-tab--on' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => setView('tasks')}
          onKeyDown={(e) => { if (e.key === 'Enter') setView('tasks'); }}
        >
          任务
        </span>
      </div>
      {view === 'inbox' ? (
        <div className="ws-rail-inbox">
          <div className="ws-rail-inbox-filter">
            {['all', 'intervention', 'ecp_proposal', 'task', 'manual'].map((s) => {
              const count = s === 'all'
                ? inboxItems.length
                : inboxItems.filter((it) => it.source_type === s).length;
              if (s !== 'all' && count === 0 && inboxSource !== s) return null;
              return (
                <span
                  key={s}
                  className={`ws-rail-inbox-chip${inboxSource === s ? ' ws-rail-inbox-chip--on' : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setInboxSource(s)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setInboxSource(s); }}
                >
                  {s === 'all' ? '全部' : INBOX_SOURCE_LABEL[s] || s}{count > 0 ? ` ${count}` : ''}
                </span>
              );
            })}
          </div>
          {inboxLoading && (
            <div className="ws-rail-empty"><div className="ws-rail-empty-t">加载中...</div></div>
          )}
          {!inboxLoading && inboxItems.length === 0 && (
            <div className="ws-rail-empty">
              <div className="ws-rail-empty-t">暂无待办</div>
              <div className="ws-rail-empty-h">没有需要你介入的事项。可在右侧对话框发起新任务。</div>
            </div>
          )}
          {inboxItems
            .filter((item) => inboxSource === 'all' || item.source_type === inboxSource)
            .map((item) => (
            <div
              key={item.id}
              className={`ws-rail-card ws-rail-card--inbox${item.inbox_status === 'doing' ? ' ws-rail-card--inbox-doing' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => handleInboxClick(item)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleInboxClick(item); } }}
            >
              <div className="ws-rail-ttl">{item.title}</div>
              <div className="ws-rail-meta">
                <span className="ws-rail-src">{INBOX_SOURCE_LABEL[item.source_type] || item.source_type}</span>
                <span className="ws-rail-meta-sep">·</span>
                <span>{item.visibility === 'shared' ? '共享' : '个人'}</span>
                {item.inbox_status === 'doing' && (
                  <>
                    <span className="ws-rail-meta-sep">·</span>
                    <span>处理中</span>
                  </>
                )}
              </div>
              <div className="ws-rail-foot">
                <span className="ws-rail-tm">{dayjs(item.gmt_modified).format('MM-DD HH:mm')}</span>
                <div className="ws-rail-card-actions">
                  {item.inbox_status !== 'done' && (
                    <span
                      className="ws-rail-card-act"
                      title="标记完成"
                      role="button"
                      tabIndex={0}
                      onClick={(e) => handleInboxDone(item, e)}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleInboxDone(item, e); } }}
                    >
                      <CheckOutlined />
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <>
      <div className="ws-scene-task-rail__header">
        <div className="ws-rail-h-top">
          <span className="ws-rail-title">任务与介入</span>
          <span className="ws-rail-count">{`${counts.all}${activeCount ? ` · 运行中 ${activeCount}` : ''}`}</span>
        </div>
        <div className="ws-rail-tabs">
          {(Object.keys(TAB_LABEL) as TaskTabKey[]).map((k) => (
            <div
              key={k}
              className={`ws-rail-tab ${TAB_CLASS[k]}${tab === k ? ' ws-rail-tab--on' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => setTab(k)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTab(k); } }}
            >
              {TAB_LABEL[k]}
              <span className={`ws-rail-bd${counts[k] === 0 ? ' ws-rail-bd--zero' : ''}`}>{counts[k]}</span>
            </div>
          ))}
        </div>
      </div>
      <Input
        prefix={<SearchOutlined />}
        placeholder="搜索任务、介入"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="ws-scene-task-rail__search"
      />
      <div className="ws-scene-task-rail__list">
        {filtered.length === 0 && (
          <div className="ws-rail-empty">
            <div className="ws-rail-empty-t">
              {tab === 'failed' ? '没有失败的任务' : tab === 'done' ? '还没有已完成的任务' : tab === 'awaiting' ? '当前没有待介入' : '暂无任务'}
            </div>
            <div className="ws-rail-empty-h">在右侧输入发起任务,选剧本 + 写目标,Agent 会跑起来。</div>
          </div>
        )}
        {grouped.map((row) => {
          if (row.type === 'seg') {
            return <div key={`seg-${row.label}`} className="ws-rail-seg">{row.label}</div>;
          }
          const it = row.item;
          if (it.kind === 'orphan-intervention') {
            const iv = it.raw;
            return (
              <div key={`orphan-${iv.id}`} className="ws-rail-card ws-rail-card--int ws-rail-card--orphan">
                <div className="ws-rail-ttl">{questionToText(iv.question) || `intervention_${iv.id}`}</div>
                <div className="ws-rail-meta">
                  <span className="ws-rail-status ws-rail-status--requested"><span className="ws-rail-dot" />待响应</span>
                  <span className="ws-rail-meta-sep">·</span>
                  <span className="ws-rail-meta-pb">无关联任务</span>
                </div>
                <div className="ws-rail-foot">
                  <span className="ws-rail-tm">{dayjs(it.updatedAt).format('MM-DD HH:mm')}</span>
                  <span className="ws-rail-meta-sep">·</span>
                  <span className="ws-rail-src">人工介入</span>
                </div>
                {renderInterventionSub(iv)}
              </div>
            );
          }
          if (it.kind === 'lobby-conversation') {
            const c = it.raw;
            const isCurrent = c.conv_uid === currentConvUid;
            const title = c.title || `会话 ${c.conv_uid?.slice(0, 8)}`;
            return (
              <div
                key={`lobby-${c.conv_uid}`}
                className={`ws-rail-card${isCurrent ? ' ws-rail-card--active' : ''}`}
                role={disabled ? undefined : 'button'}
                tabIndex={disabled ? -1 : 0}
                aria-disabled={disabled}
                onClick={() => !disabled && onOpenConversation?.(c.conv_uid, null)}
                onKeyDown={(e) => { if (!disabled && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onOpenConversation?.(c.conv_uid, null); } }}
              >
                <div className="ws-rail-ttl">{title}</div>
                <div className="ws-rail-meta">
                  <span className="ws-rail-conv-kind ws-rail-conv-kind--lobby">大厅</span>
                  {isCurrent && <span className="ws-rail-conv-cur">当前</span>}
                </div>
                <div className="ws-rail-foot">
                  <span className="ws-rail-tm">{dayjs(it.updatedAt).format('MM-DD HH:mm')}</span>
                  <span className="ws-rail-meta-sep">·</span>
                  <span className="ws-rail-src">大厅会话</span>
                </div>
              </div>
            );
          }
          const t = it.raw;
          const pbName = t.playbook_id ? pbNameById.get(t.playbook_id) : null;
          const isActive = activeTaskId === t.id;
          const canTerminate = t.status === 'running' || t.status === 'awaiting_human';
          const moreItems = [
            { key: 'reassign', label: '转交任务' },
            ...(canTerminate
              ? [{ key: 'terminate', danger: true, label: '终止任务' }]
              : [{ key: 'delete', danger: true, label: '删除任务' }]),
          ];
          return (
            <div
              key={`task-${t.id}`}
              className={`ws-rail-card${isActive ? ' ws-rail-card--active' : ''}`}
              role={disabled ? undefined : 'button'}
              tabIndex={disabled ? -1 : 0}
              aria-disabled={disabled}
              onClick={() => !disabled && onPreview(t, 'task')}
              onKeyDown={(e) => { if (!disabled && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onPreview(t, 'task'); } }}
            >
              <div className="ws-rail-ttl">{t.title || `task_${t.id}`}</div>
              <div className="ws-rail-meta">
                <span className={`ws-rail-status ws-rail-status--${t.status || 'draft'}`}>
                  <span className="ws-rail-dot" />
                  {statusLabel(t.status)}
                </span>
                {pbName && (
                  <>
                    <span className="ws-rail-meta-sep">·</span>
                    <span className="ws-rail-meta-pb" title={pbName}>{pbName}</span>
                  </>
                )}
              </div>
              <div className="ws-rail-foot">
                <span className="ws-rail-tm">{dayjs(it.updatedAt).format('MM-DD HH:mm')}</span>
                <span className="ws-rail-meta-sep">·</span>
                <span className="ws-rail-src">{triggerLabel(t)}</span>
                <ElapsedTimer task={t} />
                <div className="ws-rail-card-actions">
                  <span
                    className="ws-rail-card-act"
                    title="引用到输入框"
                    role="button"
                    tabIndex={disabled ? -1 : 0}
                    onClick={(e) => { e.stopPropagation(); if (!disabled) onReference?.(t); }}
                    onKeyDown={(e) => { if (!disabled && e.key === 'Enter') { e.preventDefault(); onReference?.(t); } }}
                  >
                    <LinkOutlined />
                  </span>
                  <span
                    className="ws-rail-card-act"
                    title="进入对话"
                    role="button"
                    tabIndex={disabled ? -1 : 0}
                    onClick={(e) => { e.stopPropagation(); if (!disabled) onEnterConversation(t.id); }}
                    onKeyDown={(e) => { if (!disabled && e.key === 'Enter') { e.preventDefault(); onEnterConversation(t.id); } }}
                  >
                    <CommentOutlined />
                  </span>
                  <Dropdown
                    menu={{
                      items: moreItems,
                      onClick: ({ key, domEvent }) => {
                        domEvent.stopPropagation();
                        if (key === 'terminate') handleTerminate(t.id);
                        else if (key === 'reassign') handleTransferOpen(t.id, t.workspace_id);
                        else handleDelete(t.id);
                      },
                    }}
                    trigger={['click']}
                  >
                    <span className="ws-rail-card-act" title="更多" onClick={(e) => e.stopPropagation()}>
                      <MoreOutlined />
                    </span>
                  </Dropdown>
                </div>
              </div>
              {it.interventions.length > 0 && (
                <div className="ws-rail-interventions">
                  {it.interventions.map(renderInterventionSub)}
                </div>
              )}
            </div>
          );
        })}
        {filtered.length > visibleCount && (
          <div
            className="ws-rail-more"
            role="button"
            tabIndex={0}
            onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
            onKeyDown={(e) => { if (e.key === 'Enter') setVisibleCount((n) => n + PAGE_SIZE); }}
          >
            加载更多(还有 {filtered.length - visibleCount} 条)
          </div>
        )}
      </div>
      </>
      )}

      <Modal
        open={!!resolveOpen}
        onCancel={() => setResolveOpen(null)}
        onOk={handleResolve}
        confirmLoading={saving}
        title="响应 - 沉淀为资产"
        width={640}
        okText="响应 + 保存资产"
      >
        <p style={{ fontSize: 13, color: 'var(--ws-ink-2)', lineHeight: 1.6, margin: '12px 0 18px' }}>
          审阅介入问题,做出决策,并把结论沉淀为空间资产(Agent 下次会作为记忆使用)。
        </p>
        <Form form={form} layout="vertical">
          <Form.Item name="decision" label="决策备注">
            <Input placeholder="approved / rejected / deferred" />
          </Form.Item>
          <Form.Item name="asset_name" label="资产名称" rules={[{ required: true }]}>
            <Input placeholder="例如:容量基线异常 - 2026年6月" />
          </Form.Item>
          <Form.Item name="asset_type" label="资产类型" initialValue="historical_artifact">
            <Input />
          </Form.Item>
          <Form.Item name="summary" label="沉淀摘要" rules={[{ required: true }]}>
            <Input.TextArea rows={5} placeholder="关键事实、决策理由、下次可复用的内容..." />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={transferOpen}
        onCancel={() => setTransferOpen(false)}
        title="转交任务"
        footer={null}
      >
        <p style={{ fontSize: 13, color: 'var(--ws-ink-2)', margin: '12px 0' }}>
          选择要转交给的成员,转交后任务会出现在对方的待办里。
        </p>
        <div>
          {members.length === 0 && <div style={{ color: 'var(--ws-ink-2)' }}>暂无成员</div>}
          {members.map((m: any) => (
            <Button
              key={m.user_id}
              style={{ margin: 4 }}
              loading={transferring}
              disabled={String(m.user_id) === String(getUserId())}
              onClick={() => handleTransferSubmit(m.user_id)}
            >
              {m.user_name || `用户 ${m.user_id}`}（{m.role}）
            </Button>
          ))}
        </div>
      </Modal>
    </div>
  );
}
