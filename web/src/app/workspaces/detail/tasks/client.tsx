'use client';

import { apiInterceptors, listTasks, getWorkspaceInfo } from '@/client/api';
import { getUserId } from '@/utils';
import { useState } from 'react';
import { Button, Empty, Spin, Tabs } from 'antd';
import { ScheduleOutlined, PlusOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import Table from 'antd/es/table';
import TriggersTable from './triggers-table';
import '../../workspaces.css';

interface TaskRow {
  id: number;
  title: string;
  status: string;
  type?: string;
  triggered_by?: string;
  gmt_created?: string;
}

const STATUS_VARIANT: Record<string, string> = {
  draft: 'neutral',
  pending_trigger: 'attention',
  running: 'running',
  awaiting_human: 'attention',
  blocked: 'danger',
  delivered: 'success',
  closed: 'neutral',
  archived: 'neutral',
  failed: 'danger',
};

function statusVariant(s: string) { return STATUS_VARIANT[s] || 'neutral'; }
function statusLabel(s: string) { return (s || '').replace(/_/g, ' '); }

export default function TaskListPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const activeTab = searchParams?.get('tab') === 'runs' ? 'runs' : 'triggers';
  const { t } = useTranslation();

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const [showAll, setShowAll] = useState(false);
  const { data: tasks, loading } = useRequest(async () => {
    if (!ws?.id) return [];
    const uid = Number(getUserId()) || 0;
    const [err, res] = await apiInterceptors(listTasks({
      workspace_id: ws.id, limit: 200,
      mine: !showAll, user_id: uid || undefined,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id, showAll] });

  const columns: ColumnsType<TaskRow> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 70,
      render: (v: number) => <span className="ws-table-id">#{v}</span>,
    },
    {
      title: t('tasks.title') || 'Title',
      dataIndex: 'title',
      render: (v: string, r: TaskRow) => (
        <Link href={`/workspaces/detail/tasks/detail?id=${workspaceCode}&task_id=${r.id}`} className="ws-table-link">
          {v}
        </Link>
      ),
    },
    {
      title: t('tasks.status') || 'Status',
      dataIndex: 'status',
      width: 140,
      render: (s: string) => (
        <span className={`ws-status ws-status--${statusVariant(s)}`}>
          <span className="ws-status-dot" />
          {statusLabel(s)}
        </span>
      ),
    },
    {
      title: t('tasks.type') || 'Type',
      dataIndex: 'type',
      width: 120,
      render: (v?: string) => v ? <span className="ws-chip ws-chip--outline">{v}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
    {
      title: t('tasks.triggered_by') || 'Trigger',
      dataIndex: 'triggered_by',
      width: 120,
      render: (v?: string) => v ? <span className="ws-chip ws-chip--mono">{v}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
    {
      title: t('tasks.created') || 'Created',
      dataIndex: 'gmt_created',
      width: 170,
      render: (v?: string) => v ? <span className="ws-table-time">{new Date(v).toLocaleString()}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
  ];

  if (loading) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content" style={{ display: 'flex', justifyContent: 'center', padding: '120px 24px' }}>
          <Spin size="large" />
        </div>
      </div>
    );
  }

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content">
        <div className="ws-page-header">
          <div className="ws-page-header-left">
            <div className="ws-page-icon"><ScheduleOutlined /></div>
            <div>
              <div className="ws-page-eyebrow">
                {t('workspaces.subscriptions') || '订阅'}
              </div>
              <h1 className="ws-page-title">{t('workspaces.subscriptions') || '订阅'}</h1>
              <p className="ws-page-subtitle">
                {t('tasks.subtitle') || '给场景订阅触发源:定时 / Webhook / 告警,到点或事件发生时自动按剧本创建任务;「执行记录」查看每次运行。'}
              </p>
            </div>
          </div>
          <div className="ws-page-actions">
            <Link href={`/workspaces/detail?id=${workspaceCode}`}>
              <Button icon={<ArrowLeftOutlined />}>{t('back') || 'Back'}</Button>
            </Link>
            {activeTab === 'runs' && (
              <Button onClick={() => setShowAll(v => !v)}>
                {showAll ? '只看我的' : '看全部'}
              </Button>
            )}
            <Link href={`/workspaces/detail/tasks/create?id=${workspaceCode}&type=timer`}>
              <Button type="primary" icon={<PlusOutlined />}>新建订阅</Button>
            </Link>
          </div>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            const qs = key === 'triggers' ? `id=${workspaceCode}&tab=triggers` : `id=${workspaceCode}`;
            window.history.replaceState(null, '', `/workspaces/detail/tasks?${qs}`);
          }}
          items={[
            {
              key: 'runs',
              label: '执行记录',
              children: (
                <div className="ws-table-wrap">
                  <Table<TaskRow>
                    rowKey="id"
                    columns={columns}
                    dataSource={tasks || []}
                    pagination={{ pageSize: 20, showSizeChanger: true }}
                    locale={{
                      emptyText: <Empty description={t('tasks.empty') || 'No tasks'} style={{ padding: '48px 0' }} />,
                    }}
                  />
                </div>
              ),
            },
            {
              key: 'triggers',
              label: '触发规则',
              children: ws?.id ? (
                <div className="ws-table-wrap">
                  <TriggersTable workspaceId={ws.id} workspaceCode={workspaceCode} />
                </div>
              ) : null,
            },
          ]}
        />
      </div>
    </div>
  );
}
