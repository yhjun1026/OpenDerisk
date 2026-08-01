'use client';

import { apiInterceptors } from '@/client/api';
import { getEcpInbox, listEcpAssets, listEcpObjects } from '@/client/api/ecp';
import { listWorkspaces } from '@/client/api/workspace';
import { getUserId } from '@/utils/storage';
import { useRequest } from 'ahooks';
import { Select } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';

import AssetsTab from './components/AssetsTab';
import GraphTab from './components/GraphTab';
import InboxTab from './components/InboxTab';
import LintTab from './components/LintTab';
import MissTab from './components/MissTab';
import OverviewTab from './components/OverviewTab';
import SemanticsTab from './components/SemanticsTab';
import SettingsTab from './components/SettingsTab';
import WikiTab from './components/WikiTab';
import './ecp.css';

const VALID_TABS = [
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
type TabKey = (typeof VALID_TABS)[number];

const TAB_LABELS: Record<TabKey, string> = {
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

/** 全局共享语义库的 ECP workspace id(后端缺省值)。 */
const DEFAULT_WORKSPACE = 'default';

export default function EcpPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get('tab') as TabKey | null;
  const tab: TabKey = tabParam && VALID_TABS.includes(tabParam) ? tabParam : 'overview';
  const workspaceId = searchParams.get('workspace') || DEFAULT_WORKSPACE;

  // 空间选择器选项:全局共享库 + 各场景空间派生的 ECP workspace(ecp_<code>)
  const { data: wsOptions } = useRequest(async () => {
    const [err, res] = await apiInterceptors(
      listWorkspaces({ user_id: Number(getUserId()) || 0 }),
    );
    if (err) return [];
    const list: Array<{ workspace_code: string; name: string }> =
      (res as any) ?? [];
    return [
      { value: DEFAULT_WORKSPACE, label: '全局共享库 (default)' },
      ...list.map(ws => ({
        value: `ecp_${ws.workspace_code}`,
        label: `场景空间：${ws.name}`,
      })),
    ];
  });

  const { data: confirmed } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listEcpObjects({ status: 'confirmed', page_size: 1, workspace_id: workspaceId }),
      );
      return err ? null : res;
    },
    { refreshDeps: [workspaceId] },
  );
  const { data: inbox } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getEcpInbox({ page_size: 1, workspace_id: workspaceId }),
      );
      return err ? null : res;
    },
    { refreshDeps: [workspaceId] },
  );
  const { data: assets } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listEcpAssets({ workspace_id: workspaceId }),
      );
      return err ? [] : res ?? [];
    },
    { refreshDeps: [workspaceId] },
  );

  const setTab = (key: TabKey) =>
    router.push(`/ecp?tab=${key}&workspace=${encodeURIComponent(workspaceId)}`);
  const setWorkspace = (ws: string) =>
    router.push(`/ecp?tab=${tab}&workspace=${encodeURIComponent(ws)}`);

  const confirmedCount = confirmed?.total_count ?? 0;
  const pendingCount = inbox?.total_count ?? 0;
  const rate =
    confirmedCount + pendingCount
      ? Math.round((confirmedCount / (confirmedCount + pendingCount)) * 100)
      : 0;

  return (
    <div className="ecp-root">
      {/* 固定区域：hero + nav */}
      <div className="ecp-hero">
        <div className="ecp-hero__aurora">
          <div className="aurora-stage">
            <div
              className="aurora-blob aurora-blob--brand"
              style={{ width: 420, height: 420, top: '-60%', right: '22%' }}
            />
            <div
              className="aurora-blob aurora-blob--cyan"
              style={{ width: 340, height: 340, top: '-30%', right: '-4%' }}
            />
          </div>
        </div>
        <div className="ecp-rise" style={{ position: 'relative', zIndex: 1 }}>
          <div className="ecp-hero__eyebrow">Enterprise Context Protocol</div>
          <h1 className="ecp-hero__title">{t('ecp_page_title')}工作台</h1>
          <div className="ecp-hero__sub">
            业务层的高阶知识库：口径、指标、维度、join
            路径全部资产化——AI 提案、人确认、版本冻结，数字只来自已确认的语义。
          </div>
          <div style={{ marginTop: 12 }}>
            <Select
              value={workspaceId}
              onChange={setWorkspace}
              options={wsOptions}
              style={{ minWidth: 260 }}
              placeholder="选择语义空间"
            />
          </div>
        </div>
        <div className="ecp-hero__stats">
          <div className="ecp-stat-chip ecp-rise ecp-rise--1">
            <div className="ecp-stat-chip__num">{confirmedCount}</div>
            <div className="ecp-stat-chip__label">
              <span className="ecp-dot ecp-dot--success" />
              已确认口径
            </div>
          </div>
          <div className="ecp-stat-chip ecp-rise ecp-rise--2">
            <div className="ecp-stat-chip__num">{pendingCount}</div>
            <div className="ecp-stat-chip__label">
              <span className="ecp-dot ecp-dot--warning" />
              待确认提案
            </div>
          </div>
          <div className="ecp-stat-chip ecp-rise ecp-rise--3">
            <div className="ecp-stat-chip__num">{assets?.length ?? 0}</div>
            <div className="ecp-stat-chip__label">
              <span className="ecp-dot ecp-dot--entity" />
              登记资产
            </div>
          </div>
          <div className="ecp-stat-chip ecp-rise ecp-rise--4">
            <div className="ecp-stat-chip__num">{rate}%</div>
            <div className="ecp-stat-chip__label">
              <span className="ecp-dot ecp-dot--metric" />
              资产固化率
            </div>
          </div>
        </div>
      </div>

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

      {/* 滚动区域：tab 内容 */}
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
    </div>
  );
}
