'use client';

import {
  apiInterceptors, listTriggers, deleteTrigger, fireTrigger,
} from '@/client/api';
import { App, Button, Spin } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import Table from 'antd/es/table';
import '../../workspaces.css';

interface TriggerRow {
  id: number;
  workspace_id: number;
  name: string;
  type: string;
  instruction?: string;
  target_playbook_id: number;
  is_active: boolean;
  last_fired_at?: string;
  gmt_modified?: string;
}

const TYPE_VARIANT: Record<string, string> = {
  timer: 'info',
  webhook: 'purple',
  alert: 'attention',
  manual: 'neutral',
};

/**
 * 触发规则表格(定时/webhook/告警/手动规则,到点或事件发生时自动按剧本创建任务)。
 * 嵌在任务页「触发规则」Tab 中;workspaceId 由父页面传入。
 */
export default function TriggersTable({ workspaceId, workspaceCode }: { workspaceId: number; workspaceCode: string }) {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();

  const { data: triggers, loading, refresh } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listTriggers({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const handleFire = async (item: TriggerRow) => {
    const [err, res] = await apiInterceptors(fireTrigger({
      workspace_id: item.workspace_id,
      trigger_id: item.id,
      payload: {},
    }));
    if (err) { message.error(err.message); return; }
    message.success(`${t('triggers.fired') || 'Fired'} — Task #${res?.task_id}`);
    refresh();
  };

  const handleDelete = (id: number) => {
    modal.confirm({
      title: t('triggers.delete_confirm') || 'Delete trigger source?',
      okText: t('delete') || 'Delete',
      okButtonProps: { danger: true },
      cancelText: t('cancel') || 'Cancel',
      onOk: async () => {
        const [err] = await apiInterceptors(deleteTrigger(id));
        if (err) { message.error(err.message); return; }
        message.success(t('triggers.deleted') || 'Deleted');
        refresh();
      },
    });
  };

  const columns: ColumnsType<TriggerRow> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 70,
      render: (v: number) => <span className="ws-table-id">#{v}</span>,
    },
    {
      title: t('triggers.name') || 'Name',
      dataIndex: 'name',
      render: (v: string, r: TriggerRow) => (
        <Link href={`/workspaces/detail/tasks/create?id=${workspaceCode}&trigger_id=${r.id}&type=${r.type}`} className="ws-table-link">
          {v}
        </Link>
      ),
    },
    {
      title: '指令',
      dataIndex: 'instruction',
      render: (v?: string) => v ? (
        <span title={v} style={{ color: 'var(--ws-ink-2)' }}>{v.length > 26 ? v.slice(0, 26) + '…' : v}</span>
      ) : <span style={{ color: 'var(--ws-ink-3)' }}>—</span>,
    },
    {
      title: t('triggers.type') || 'Type',
      dataIndex: 'type',
      width: 120,
      render: (v: string) => (
        <span className={`ws-chip ws-chip--${TYPE_VARIANT[v] || 'outline'} ws-chip--mono`}>{v}</span>
      ),
    },
    {
      title: t('triggers.target_playbook') || 'Playbook',
      dataIndex: 'target_playbook_id',
      width: 120,
      render: (v: number) => <span className="ws-chip ws-chip--mono">#{v}</span>,
    },
    {
      title: t('triggers.active') || 'Active',
      dataIndex: 'is_active',
      width: 100,
      render: (v: boolean) => (
        <span className={`ws-status ws-status--${v ? 'success' : 'neutral'}`}>
          <span className="ws-status-dot" />
          {v ? 'active' : 'paused'}
        </span>
      ),
    },
    {
      title: t('triggers.last_fired') || 'Last Fired',
      dataIndex: 'last_fired_at',
      width: 180,
      render: (v?: string) => v ? <span className="ws-table-time">{new Date(v).toLocaleString()}</span> : <span style={{ color: 'var(--ws-ink-3)' }}>never</span>,
    },
    {
      title: '',
      key: 'actions',
      width: 200,
      render: (_: unknown, r: TriggerRow) => (
        <div style={{ display: 'flex', gap: 6 }}>
          <Button size="small" type="primary" ghost icon={<ThunderboltOutlined />} onClick={() => handleFire(r)}>
            {t('triggers.fire') || 'Fire'}
          </Button>
          <Link href={`/workspaces/detail/tasks/create?id=${workspaceCode}&trigger_id=${r.id}&type=${r.type}`}>
            <Button size="small">{t('edit') || 'Edit'}</Button>
          </Link>
          <Button size="small" danger onClick={() => handleDelete(r.id)}>{t('delete') || 'Delete'}</Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}><Spin /></div>
      ) : (
        <Table<TriggerRow>
          rowKey="id"
          columns={columns}
          dataSource={triggers || []}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          locale={{ emptyText: <span style={{ color: 'var(--ws-ink-3)', padding: '48px 0', display: 'inline-block' }}>{t('triggers.empty') || 'No trigger sources'}</span> }}
        />
      )}
    </div>
  );
}
