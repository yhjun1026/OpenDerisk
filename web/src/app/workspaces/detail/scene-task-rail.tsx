'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button, Dropdown, Form, Input, Modal, message } from 'antd';
import { CommentOutlined, LinkOutlined, MoreOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { apiInterceptors, createAsset, resolveAndExecuteIntervention, abortIntervention, terminateTask, deleteTask } from '@/client/api';
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
  onPreview: (item: any, kind: 'task' | 'intervention') => void;
  onEnterConversation: (taskId: number) => void;
  onReference?: (task: any) => void;
  onRefreshLists?: () => void;
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
}: SceneTaskRailProps) {
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

  const merged = useMemo(
    () => [...taskItems, ...orphanItems].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    ),
    [taskItems, orphanItems],
  );

  const counts = useMemo(() => {
    const c: Record<TaskTabKey, number> = { all: 0, running: 0, awaiting: 0, done: 0, failed: 0 };
    taskItems.forEach((it) => {
      c.all += 1;
      const tb = statusToTab(it.raw.status);
      if (tb !== 'all') c[tb] += 1;
    });
    // 孤立介入计入 all + awaiting(仍需人响应)
    orphanItems.forEach(() => { c.all += 1; c.awaiting += 1; });
    return c;
  }, [taskItems, orphanItems]);

  const activeCount = counts.running + counts.awaiting;

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return merged.filter((it) => {
      if (it.kind === 'task') {
        if (tab !== 'all' && statusToTab(it.raw.status) !== tab) return false;
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
    Modal.confirm({
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
    Modal.confirm({
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
          const t = it.raw;
          const pbName = t.playbook_id ? pbNameById.get(t.playbook_id) : null;
          const isActive = activeTaskId === t.id;
          const canTerminate = t.status === 'running' || t.status === 'awaiting_human';
          const moreItems = canTerminate
            ? [{ key: 'terminate', danger: true, label: '终止任务' }]
            : [{ key: 'delete', danger: true, label: '删除任务' }];
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
    </div>
  );
}
