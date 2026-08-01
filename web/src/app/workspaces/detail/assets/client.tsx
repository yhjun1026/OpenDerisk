'use client';

import { apiInterceptors, getWorkspaceInfo } from '@/client/api';
import { Button, Card, Empty, Spin, Tabs } from 'antd';
import {
  DatabaseOutlined,
  SendOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { DataAssetsTab } from './data-assets-tab';
import { DeliveryPanel } from './delivery-panel';
import { CapabilityTab } from './capability-tab';

const TAB_KEYS = ['data', 'delivery', 'capability'] as const;
type TabKey = typeof TAB_KEYS[number];

/** 资产页:数据资产(能碰什么) / 交付沉淀(干出了什么) / 能力(会干什么)。 */
export default function AssetsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const workspaceCode = searchParams?.get('id') || '';
  const tabParam = searchParams?.get('tab');
  const activeTab: TabKey = (TAB_KEYS as readonly string[]).includes(tabParam || '')
    ? (tabParam as TabKey)
    : 'data';
  const { t } = useTranslation();

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const handleTabChange = (key: string) => {
    router.replace(`${pathname}?id=${workspaceCode}&tab=${key}`);
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

  const tabs = [
    {
      key: 'data',
      label: (
        <span>
          <DatabaseOutlined style={{ marginRight: 6 }} />
          {t('assets.tab_data') || '数据资产'}
        </span>
      ),
      children: <DataAssetsTab workspaceId={ws.id} workspaceCode={ws.workspace_code} />,
    },
    {
      key: 'delivery',
      label: (
        <span>
          <SendOutlined style={{ marginRight: 6 }} />
          {t('assets.tab_delivery') || '交付沉淀'}
        </span>
      ),
      children: <DeliveryPanel workspaceId={ws.id} />,
    },
    {
      key: 'capability',
      label: (
        <span>
          <ToolOutlined style={{ marginRight: 6 }} />
          {t('assets.tab_capability') || '能力'}
        </span>
      ),
      children: <CapabilityTab workspaceId={ws.id} />,
    },
  ];

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content" style={{ paddingTop: 16, paddingBottom: 48 }}>
        <div className="ws-page-header mb-6">
          <div className="ws-page-header-left">
            <div className="ws-page-icon">
              <DatabaseOutlined />
            </div>
            <div>
              <p className="ws-page-eyebrow">
                {ws.name}
                <span className="ws-page-eyebrow-code">{ws.workspace_code}</span>
              </p>
              <h1 className="ws-page-title">{t('assets.title_page') || '资产'}</h1>
              <p className="ws-page-subtitle">
                {t('assets.subtitle') || '空间的数据资产、能力,与任务交付沉淀 —— 大家共同维护的公共环境。'}
              </p>
            </div>
          </div>
          <div className="ws-page-actions">
            <Link href={`/workspaces/detail?id=${workspaceCode}`}>
              <Button>{t('back') || '返回'}</Button>
            </Link>
          </div>
        </div>

        <Card className="ws-surface">
          <Tabs activeKey={activeTab} onChange={handleTabChange} items={tabs} />
        </Card>
      </div>
    </div>
  );
}
