'use client';

import {
  apiInterceptors, getWorkspaceInfo, listTasks, listInterventions,
  createConversation, getCurrentConversation, setCurrentConversation,
  linkConversation,
} from '@/client/api';
import { Button, Spin } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useCallback, useContext, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ScheduleOutlined,
  SettingOutlined,
  BookOutlined,
  AppstoreOutlined,
  HomeOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { SceneWorkspaceShell } from './scene-workspace-shell';
import { ChatContext } from '@/contexts';
import '../workspaces.css';

export default function WorkspaceDetailPage() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const workspaceCode = searchParams?.get('id') || '';
  // 当前子页面导航激活态(分段控件高亮)
  const navActive = (segment: string) =>
    pathname?.includes(`/workspaces/detail/${segment}`) ? ' ws-console-nav-link--active' : '';
  const { t } = useTranslation();
  const [convUid, setConvUid] = useState<string>('');
  const [convLoadError, setConvLoadError] = useState<string | null>(null);
  const [convLoadKey, setConvLoadKey] = useState(0);
  const [listsRefreshKey, setListsRefreshKey] = useState(0);
  // 从会话列表选中会话时携带的 task_id:number=进 task 对话,null=workspace 级会话,
  // undefined=非列表触发(初始/任务栏进入)。shell 据此恢复 activeTaskId。
  const [pendingTaskId, setPendingTaskId] = useState<number | null | undefined>(undefined);

  // 场景空间三列布局需要宽度,进入时自动折叠左侧菜单
  const { setIsMenuExpand } = useContext(ChatContext);
  useEffect(() => {
    setIsMenuExpand(false);
  }, [setIsMenuExpand]);

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const workspaceId = ws?.id;
  const appCode = ws?.default_agent_app_code || 'main';

  useRequest(
    async () => {
      setConvLoadError(null);
      const [, current] = await apiInterceptors(getCurrentConversation(workspaceId));
      if (current?.conv_uid) {
        setConvUid(current.conv_uid);
        return;
      }
      const [newErr, newConv] = await apiInterceptors(createConversation({}));
      if (newErr || !newConv?.conv_uid) {
        setConvLoadError(newErr?.message || '无法创建会话，请稍后重试');
        return;
      }
      const [linkErr] = await apiInterceptors(
        linkConversation({ workspace_id: workspaceId, conv_uid: newConv.conv_uid, user_id: undefined })
      );
      if (linkErr) {
        setConvLoadError(`会话关联空间失败：${linkErr.message || '未知错误'}`);
        return;
      }
      const [currErr] = await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
      if (currErr) {
        setConvLoadError(`设置当前会话失败：${currErr.message || '未知错误'}`);
        return;
      }
      setConvUid(newConv.conv_uid);
    },
    {
      ready: !!workspaceId,
      refreshDeps: [convLoadKey],
      onError: (e: any) => {
        setConvLoadError(e?.message || '会话加载失败');
      },
    }
  );

  const { data: tasks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listTasks({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId, listsRefreshKey] });

  const { data: interventions } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listInterventions({
      workspace_id: workspaceId, status: 'requested', limit: 20,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId, listsRefreshKey] });

  const retryLoadConv = useCallback(() => {
    setConvLoadKey((k) => k + 1);
  }, []);

  const handleRefreshLists = useCallback(() => {
    setListsRefreshKey((k) => k + 1);
  }, []);

  if (!searchParams || wsLoading) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content ws-page-content--fluid" style={{ display: 'flex', justifyContent: 'center', padding: '120px 24px' }}>
          <Spin size="large" />
        </div>
      </div>
    );
  }

  if (!ws) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content ws-page-content--fluid">
          <div className="ws-empty">
            <div className="ws-empty-icon"><AppstoreOutlined /></div>
            <p className="ws-empty-title">Workspace not found</p>
            <p className="ws-empty-desc">This workspace may have been archived or you lack access.</p>
            <Link href="/workspaces"><Button>Back to workspaces</Button></Link>
          </div>
        </div>
      </div>
    );
  }

  if (!workspaceId) {
    return null;
  }

  const scenario = ws.scenario_type || ws.type || 'scenario';

  return (
    <div className="ws-page" style={{ height: '100%', minHeight: 0, overflow: 'hidden' }}>
      <div className="ws-page-bg" />
      <div
        className="ws-page-content ws-page-content--fluid"
        style={{ padding: '12px', height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 10, boxSizing: 'border-box' }}
      >
        <div className="ws-console-header">
          <div className="ws-console-header-left">
            <div className="ws-console-avatar"><AppstoreOutlined /></div>
            <div style={{ minWidth: 0 }}>
              <h2 className="ws-console-title">{ws.name}</h2>
              <div className="ws-console-sub">
                {ws.workspace_code} · {scenario}
              </div>
            </div>
          </div>
          <nav className="ws-console-nav" aria-label="Workspace navigation">
            <Link href={`/workspaces/detail?id=${workspaceCode}`} className={`ws-console-nav-link${pathname === '/workspaces/detail' ? ' ws-console-nav-link--active' : ''}`}>
              <HomeOutlined />{t('workspaces.lobby') || '工作台'}
            </Link>
            <Link href={`/workspaces/detail/tasks?id=${workspaceCode}`} className={`ws-console-nav-link${navActive('tasks')}`}>
              <ScheduleOutlined />{t('workspaces.subscriptions') || '订阅'}
            </Link>
            <Link href={`/workspaces/detail/playbooks?id=${workspaceCode}`} className={`ws-console-nav-link${navActive('playbooks')}`}>
              <BookOutlined />{t('workspaces.playbooks') || '剧本'}
            </Link>
            <Link href={`/workspaces/detail/assets?id=${workspaceCode}&tab=data`} className={`ws-console-nav-link${navActive('assets')}`}>
              <DatabaseOutlined />{t('workspaces.assets') || '资产'}
            </Link>
            <Link href={`/workspaces/detail/settings?id=${workspaceCode}`} className={`ws-console-nav-link${navActive('settings')}`}>
              <SettingOutlined />{t('workspaces.settings') || '设置'}
            </Link>
          </nav>
        </div>

        <SceneWorkspaceShell
          workspace={ws}
          tasks={tasks || []}
          interventions={interventions || []}
          workspaceConvUid={convUid}
          appCode={appCode}
          onRefreshLists={handleRefreshLists}
          onConvChanged={(uid: string, tid?: number | null) => {
            setConvUid(uid);
            setPendingTaskId(tid ?? null);
          }}
          convLoadError={convLoadError}
          retryLoadConv={retryLoadConv}
          pendingTaskId={pendingTaskId}
        />
      </div>
    </div>
  );
}
