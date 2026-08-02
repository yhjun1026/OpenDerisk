'use client';

import { useState } from 'react';
import { apiInterceptors } from '@/client/api';
import { getEcpInbox } from '@/client/api/ecp';
import { useRequest } from 'ahooks';

import AssetsTab from './AssetsTab';
import GraphTab from './GraphTab';
import InboxTab from './InboxTab';
import LintTab from './LintTab';
import MissTab from './MissTab';
import OverviewTab from './OverviewTab';
import SemanticsTab from './SemanticsTab';
import SettingsTab from './SettingsTab';
import WikiTab from './WikiTab';
import '../ecp.css';

export const VALID_TABS = [
  'overview',
  'inbox',
  'assets',
  'semantics',
  'wiki',
  'graph',
  'miss',
  'lint',
  'settings',
] as const;
export type TabKey = (typeof VALID_TABS)[number];

export const TAB_LABELS: Record<TabKey, string> = {
  overview: '总览',
  inbox: '收件箱',
  assets: '资产层',
  semantics: '硬语义',
  wiki: '软知识',
  graph: '血缘图',
  miss: 'miss',
  lint: '巡检',
  settings: '设置',
};

export interface EcpConsoleProps {
  workspaceId: string;
  /** 受控 tab(/ecp 整页用 URL 驱动);不传则内部 state(嵌入场景) */
  tab?: TabKey;
  onTabChange?: (key: TabKey) => void;
}

/** ECP 控制台内容区(nav + tab 内容),不含 hero / 空间选择器 / 全局外壳。
 *  /ecp 整页与场景空间资产 tab(语义资产)共用。 */
export function EcpConsole({ workspaceId, tab: controlledTab, onTabChange }: EcpConsoleProps) {
  const [innerTab, setInnerTab] = useState<TabKey>('overview');
  const tab = controlledTab ?? innerTab;
  const setTab = (key: TabKey) => (onTabChange ? onTabChange(key) : setInnerTab(key));

  // nav 收件箱角标(整页 hero 另有完整统计,这里是轻量 page_size=1)
  const { data: inbox } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getEcpInbox({ page_size: 1, workspace_id: workspaceId }),
      );
      return err ? null : res;
    },
    { refreshDeps: [workspaceId] },
  );
  const pendingCount = inbox?.total_count ?? 0;

  return (
    <>
      <nav className="ecp-nav">
        {VALID_TABS.map(key => (
          <span
            key={key}
            className={`ecp-nav__pill ${tab === key ? 'ecp-nav__pill--active' : ''}`}
            onClick={() => setTab(key)}
          >
            {TAB_LABELS[key]}
            {key === 'inbox' && pendingCount > 0 && (
              <span className="ecp-nav__count">{pendingCount}</span>
            )}
          </span>
        ))}
      </nav>

      <div className="ecp-tab-content">
        {tab === 'overview' && (
          <OverviewTab onGoInbox={() => setTab('inbox')} workspaceId={workspaceId} />
        )}
        {tab === 'inbox' && <InboxTab workspaceId={workspaceId} />}
        {tab === 'assets' && <AssetsTab workspaceId={workspaceId} />}
        {tab === 'semantics' && <SemanticsTab workspaceId={workspaceId} />}
        {tab === 'wiki' && <WikiTab workspaceId={workspaceId} />}
        {tab === 'graph' && <GraphTab workspaceId={workspaceId} />}
        {tab === 'miss' && <MissTab workspaceId={workspaceId} />}
        {tab === 'lint' && <LintTab workspaceId={workspaceId} />}
        {tab === 'settings' && <SettingsTab workspaceId={workspaceId} />}
      </div>
    </>
  );
}
