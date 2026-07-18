'use client';

import {
  apiInterceptors,
  getWorkspaceInfo,
  listArtifacts,
  listDeliveries,
  listAssets,
  listTasks,
  sendDelivery,
} from '@/client/api';
import {
  Button, Card, Empty, Spin, Table, Tabs, Tag, Tooltip, Modal, Descriptions, message,
} from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GPTVis } from '@antv/gpt-vis';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import {
  FileTextOutlined,
  SendOutlined,
  InboxOutlined,
  DatabaseOutlined,
  EyeOutlined,
  HistoryOutlined,
} from '@ant-design/icons';

const TAB_KEYS = ['artifacts', 'management', 'deliveries', 'archive'] as const;
type TabKey = typeof TAB_KEYS[number];

function isHtmlContent(text: string): boolean {
  const head = text.trimStart().slice(0, 200).toLowerCase();
  return head.startsWith('<!doctype') || head.startsWith('<html');
}

/** 交付物内容渲染:html → 沙箱 iframe;markdown → GPTVis;空 → 占位提示。 */
function ArtifactContent({ text }: { text: string }) {
  if (!text.trim()) {
    return <Empty description="(no content stored; see content_ref for reference)" />;
  }
  if (isHtmlContent(text)) {
    return (
      <iframe
        sandbox="allow-same-origin"
        srcDoc={text}
        title="artifact preview"
        style={{ width: '100%', minHeight: 480, border: '1px solid #f0f0f0', borderRadius: 8 }}
      />
    );
  }
  return (
    <div style={{ maxHeight: 480, overflowY: 'auto' }}>
      {/* @ts-ignore rehypePlugins type mismatch is pre-existing repo-wide */}
      <GPTVis components={markdownComponents} {...markdownPlugins}>
        {preprocessLaTeX(text)}
      </GPTVis>
    </div>
  );
}

interface ArtifactItem {
  id: number;
  title: string;
  type: string;
  task_id: number;
  current_version: number;
  is_shared: boolean;
  gmt_created: string;
  content_text?: string;
  content_ref?: string;
  provenance?: any;
}

interface DeliveryItem {
  id: number;
  channel: string;
  target: string;
  status: string;
  sent_at?: string;
  artifact_id?: number;
  task_id?: number;
}

interface AssetItem {
  id: number;
  name: string;
  type: string;
  gmt_created: string;
}

interface TaskItem {
  id: number;
  title: string;
  status: string;
  gmt_closed?: string;
}

export default function DeliveriesPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<TabKey>('artifacts');
  const [activeArtifact, setActiveArtifact] = useState<ArtifactItem | null>(null);

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const workspaceId = ws?.id;

  const { data: artifacts, loading: artifactsLoading } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listArtifacts({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: deliveries, loading: deliveriesLoading, refresh: refreshDeliveries } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listDeliveries({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const handleResend = async (deliveryId: number) => {
    const [err] = await apiInterceptors(sendDelivery(deliveryId));
    if (err) {
      message.error('投递失败,请稍后重试');
      return;
    }
    message.success('已重新投递');
    refreshDeliveries();
  };

  const { data: assets, loading: assetsLoading } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listAssets({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: tasks, loading: tasksLoading } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listTasks({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const closedTasks = (tasks || []).filter((task: TaskItem) =>
    ['closed', 'archived', 'failed'].includes(task.status)
  );
  const closedTaskIds = new Set(closedTasks.map((t: TaskItem) => t.id));
  const archivedArtifacts = (artifacts || []).filter((a: ArtifactItem) =>
    closedTaskIds.has(a.task_id)
  );
  const recentArtifacts = (artifacts || []).filter((a: ArtifactItem) =>
    !closedTaskIds.has(a.task_id)
  );

  const deliveryStatusColor = (s: string) => {
    if (s === 'sent' || s === 'delivered') return 'success';
    if (s === 'failed') return 'error';
    if (s === 'pending') return 'warning';
    return 'default';
  };

  if (wsLoading || !searchParams) {
    return (
      <div className="flex justify-center py-20">
        <Spin size="large" />
      </div>
    );
  }

  if (!ws) {
    return (
      <div className="p-6">
        <Empty description="Workspace not found" />
      </div>
    );
  }

  const artifactColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: t('deliveries.artifact_title') || 'Title', dataIndex: 'title' },
    {
      title: t('deliveries.artifact_type') || 'Type',
      dataIndex: 'type',
      width: 110,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    { title: 'Task', dataIndex: 'task_id', width: 80 },
    { title: t('deliveries.version') || 'Version', dataIndex: 'current_version', width: 90 },
    {
      title: t('deliveries.shared') || 'Shared',
      dataIndex: 'is_shared',
      width: 90,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? 'yes' : 'no'}</Tag>,
    },
    { title: t('deliveries.created') || 'Created', dataIndex: 'gmt_created', width: 180 },
    {
      title: '',
      key: 'view',
      width: 90,
      render: (_: any, r: ArtifactItem) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => setActiveArtifact(r)}>
          {t('view') || 'View'}
        </Button>
      ),
    },
  ];

  const deliveryColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    {
      title: t('deliveries.channel') || 'Channel',
      dataIndex: 'channel',
      width: 110,
      render: (v: string) => <Tag color="purple">{v}</Tag>,
    },
    { title: t('deliveries.target') || 'Target', dataIndex: 'target' },
    {
      title: t('deliveries.status') || 'Status',
      dataIndex: 'status',
      width: 110,
      render: (s: string) => <Tag color={deliveryStatusColor(s)}>{s}</Tag>,
    },
    { title: 'Artifact', dataIndex: 'artifact_id', width: 90 },
    { title: 'Task', dataIndex: 'task_id', width: 80 },
    { title: t('deliveries.sent_at') || 'Sent At', dataIndex: 'sent_at', width: 180 },
    {
      title: '',
      key: 'actions',
      width: 100,
      render: (_: any, r: DeliveryItem) => (
        <Button size="small" icon={<SendOutlined />} onClick={() => handleResend(r.id)}>
          {t('deliveries.resend') || '重发'}
        </Button>
      ),
    },
  ];

  const archiveColumns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: t('deliveries.artifact_title') || 'Title', dataIndex: 'title' },
    {
      title: t('deliveries.artifact_type') || 'Type',
      dataIndex: 'type',
      width: 110,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    { title: 'Task', dataIndex: 'task_id', width: 80 },
    { title: t('deliveries.version') || 'Version', dataIndex: 'current_version', width: 90 },
    { title: t('deliveries.created') || 'Created', dataIndex: 'gmt_created', width: 180 },
    {
      title: '',
      key: 'view',
      width: 90,
      render: (_: any, r: ArtifactItem) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => setActiveArtifact(r)}>
          {t('view') || 'View'}
        </Button>
      ),
    },
  ];

  const tabs = [
    {
      key: 'artifacts',
      label: (
        <span>
          <FileTextOutlined style={{ marginRight: 6 }} />
          {t('deliveries.tab_artifacts') || '产出物'}
        </span>
      ),
      children: (
        <>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-base font-semibold m-0">
              {t('deliveries.recent_outputs') || 'Recent Outputs'}
            </h3>
            <span className="text-sm text-gray-500">
              {recentArtifacts.length} {t('deliveries.items') || 'items'}
            </span>
          </div>
          <Table
            rowKey="id"
            size="small"
            pagination={{ pageSize: 10 }}
            loading={artifactsLoading}
            dataSource={recentArtifacts}
            columns={artifactColumns}
            locale={{ emptyText: <Empty description={t('deliveries.no_artifacts') || 'No artifacts yet'} /> }}
          />
        </>
      ),
    },
    {
      key: 'management',
      label: (
        <span>
          <DatabaseOutlined style={{ marginRight: 6 }} />
          {t('deliveries.tab_management') || '产出管理'}
        </span>
      ),
      children: (
        <>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-base font-semibold m-0">
              {t('deliveries.artifact_library') || 'Artifact Library'}
            </h3>
            <span className="text-sm text-gray-500">
              {(artifacts || []).length} {t('deliveries.total') || 'total'}
            </span>
          </div>
          <Table
            rowKey="id"
            size="small"
            pagination={{ pageSize: 15 }}
            loading={artifactsLoading}
            dataSource={artifacts || []}
            columns={artifactColumns}
            locale={{ emptyText: <Empty description={t('deliveries.no_artifacts') || 'No artifacts yet'} /> }}
          />
        </>
      ),
    },
    {
      key: 'deliveries',
      label: (
        <span>
          <SendOutlined style={{ marginRight: 6 }} />
          {t('deliveries.tab_deliveries') || '产出交付'}
        </span>
      ),
      children: (
        <>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-base font-semibold m-0">
              {t('deliveries.delivery_log') || 'Delivery Log'}
            </h3>
            <span className="text-sm text-gray-500">
              {(deliveries || []).length} {t('deliveries.records') || 'records'}
            </span>
          </div>
          <Table
            rowKey="id"
            size="small"
            pagination={{ pageSize: 15 }}
            loading={deliveriesLoading}
            dataSource={deliveries || []}
            columns={deliveryColumns}
            locale={{ emptyText: <Empty description={t('deliveries.no_deliveries') || 'No deliveries yet'} /> }}
          />
        </>
      ),
    },
    {
      key: 'archive',
      label: (
        <span>
          <InboxOutlined style={{ marginRight: 6 }} />
          {t('deliveries.tab_archive') || '产出归档'}
        </span>
      ),
      children: (
        <>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-base font-semibold m-0">
              {t('deliveries.archived_outputs') || 'Archived Outputs'}
            </h3>
            <span className="text-sm text-gray-500">
              {archivedArtifacts.length} {t('deliveries.archived') || 'archived'} · {(assets || []).length} {t('deliveries.distilled') || 'distilled'}
            </span>
          </div>
          <Table
            rowKey="id"
            size="small"
            pagination={{ pageSize: 15 }}
            loading={artifactsLoading || tasksLoading}
            dataSource={archivedArtifacts}
            columns={archiveColumns}
            locale={{ emptyText: <Empty description={t('deliveries.no_archived') || 'No archived outputs yet'} /> }}
          />
          <div className="mt-6">
            <h3 className="text-base font-semibold mb-3">
              <HistoryOutlined style={{ marginRight: 6 }} />
              {t('deliveries.distilled_assets') || 'Distilled Assets'}
            </h3>
            <Table
              rowKey="id"
              size="small"
              pagination={{ pageSize: 10 }}
              loading={assetsLoading}
              dataSource={assets || []}
              columns={[
                { title: 'ID', dataIndex: 'id', width: 70 },
                { title: t('deliveries.asset_name') || 'Name', dataIndex: 'name' },
                { title: t('deliveries.asset_type') || 'Type', dataIndex: 'type', width: 140, render: (v: string) => <Tag color="green">{v}</Tag> },
                { title: t('deliveries.created') || 'Created', dataIndex: 'gmt_created', width: 180 },
              ]}
              locale={{ emptyText: <Empty description={t('deliveries.no_assets') || 'No distilled assets yet'} /> }}
            />
          </div>
        </>
      ),
    },
  ];

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content" style={{ paddingTop: 16, paddingBottom: 48 }}>
        <div className="ws-page-header mb-6">
          <div className="ws-page-header-left">
            <div className="ws-page-icon">
              <SendOutlined />
            </div>
            <div>
              <p className="ws-page-eyebrow">
                {ws.name}
                <span className="ws-page-eyebrow-code">{ws.workspace_code}</span>
              </p>
              <h1 className="ws-page-title">{t('deliveries.title') || 'Delivery Space'}</h1>
              <p className="ws-page-subtitle">
                {t('deliveries.subtitle') || 'Artifacts, deliveries, and archived outputs for this workspace.'}
              </p>
            </div>
          </div>
          <div className="ws-page-actions">
            <Link href={`/workspaces/detail?id=${workspaceCode}`}>
              <Button>{t('back') || 'Back'}</Button>
            </Link>
          </div>
        </div>

        <Card className="ws-surface">
          <Tabs
            activeKey={activeTab}
            onChange={(k) => setActiveTab(k as TabKey)}
            items={tabs}
          />
        </Card>
      </div>

      <Modal
        open={!!activeArtifact}
        onCancel={() => setActiveArtifact(null)}
        footer={null}
        width={900}
        title={activeArtifact?.title}
      >
        {activeArtifact && (
          <div>
            <p className="text-sm text-gray-600 mb-2">
              <Tag color="blue">{activeArtifact.type}</Tag>
              {' '}v{activeArtifact.current_version} · Task #{activeArtifact.task_id}
            </p>
            <Descriptions column={1} size="small" bordered className="mb-4">
              <Descriptions.Item label="ID">{activeArtifact.id}</Descriptions.Item>
              <Descriptions.Item label="Shared">{activeArtifact.is_shared ? 'Yes' : 'No'}</Descriptions.Item>
              <Descriptions.Item label="Created">{activeArtifact.gmt_created}</Descriptions.Item>
            </Descriptions>
            <h3 className="text-sm font-medium mt-4">Content</h3>
            <ArtifactContent text={activeArtifact.content_text || activeArtifact.content_ref || ''} />
            <h3 className="text-sm font-medium mt-4">Provenance</h3>
            <pre className="text-xs bg-gray-50 p-3 max-h-40 overflow-auto rounded">
              {JSON.stringify(activeArtifact.provenance || {}, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
}
