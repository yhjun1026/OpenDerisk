'use client';

import { apiInterceptors, listResources, listPlaybooks, listTriggers, getWorkspaceInfo } from '@/client/api';
import { listEcpObjects } from '@/client/api/ecp';
import {
  DatabaseOutlined,
  ToolOutlined,
  BookOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  ScheduleOutlined,
  DeploymentUnitOutlined,
  DownOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import Link from 'next/link';
import { useMemo, useState } from 'react';

interface SpaceGuideCardProps {
  workspaceId: number;
  workspaceCode: string;
}

const DATA_TYPES = ['data_source', 'knowledge_space'];
const CAPABILITY_TYPES = ['skill', 'mcp', 'llm_model', 'environment', 'app', 'ecp'];

/** 空间导览卡:回答新人三个问题 —— 这空间是干嘛的、有什么数据、Agent 会干什么、有哪些现成剧本。 */
export function SpaceGuideCard({ workspaceId, workspaceCode }: SpaceGuideCardProps) {
  const storageKey = `ws-guide-collapsed-${workspaceId}`;
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(storageKey) === '1';
  });

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });
  const description = ws?.description;

  const { data: resources } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listResources({ workspace_id: workspaceId }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: playbooks } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listPlaybooks({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: triggers } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listTriggers({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  // ECP 语义资产计数(派生 ECP workspace 下已确认语义对象)
  const ecpWsId = workspaceCode ? `ecp_${workspaceCode}` : null;
  const { data: semanticRes } = useRequest(
    async () => {
      if (!ecpWsId) return null;
      const [err, res] = await apiInterceptors(
        listEcpObjects({ workspace_id: ecpWsId, status: 'confirmed', page_size: 1 }),
      );
      if (err) return null;
      return res;
    },
    { ready: !!ecpWsId, refreshDeps: [ecpWsId] },
  );
  const semanticCount = semanticRes?.total_count ?? 0;

  const stats = useMemo(() => {
    const dataCount = (resources || []).filter((r: any) => DATA_TYPES.includes(r.type)).length;
    const capCount = (resources || []).filter((r: any) => CAPABILITY_TYPES.includes(r.type)).length;
    const pbCount = (playbooks || []).length;
    const triggeredPb = new Set(
      (triggers || []).filter((t: any) => t.is_active !== false).map((t: any) => t.playbook_id),
    ).size;
    return { dataCount, capCount, pbCount, triggeredPb, semanticCount };
  }, [resources, playbooks, triggers, semanticCount]);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(storageKey, next ? '1' : '0');
    }
  };

  // 聚焦右侧 Agent 输入框(textarea 无稳定 id,用 placeholder 定位,与 agent-workspace-input 耦合)
  const focusChatInput = () => {
    const el = document.querySelector<HTMLTextAreaElement>('textarea[placeholder*="输入指令"]');
    el?.focus();
  };

  return (
    <div className="ws-guide">
      <div
        className="ws-guide__head"
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={(e) => { if (e.key === 'Enter') toggle(); }}
      >
        <span className="ws-guide__title">空间导览</span>
        {description && <span className="ws-guide__desc">{description}</span>}
        <span className="ws-guide__toggle">{collapsed ? <RightOutlined /> : <DownOutlined />}</span>
      </div>
      {!collapsed && (
        <div className="ws-guide__body">
          <div className="ws-guide__stats">
            <span className="ws-guide__stat">
              <DatabaseOutlined />
              数据资产 <b>{stats.dataCount}</b>
            </span>
            <span className="ws-guide__stat">
              <ToolOutlined />
              能力 <b>{stats.capCount}</b>
            </span>
            <span className="ws-guide__stat">
              <DeploymentUnitOutlined />
              语义资产 <b>{stats.semanticCount}</b>
            </span>
            <span className="ws-guide__stat">
              <BookOutlined />
              剧本 <b>{stats.pbCount}</b>
              {stats.triggeredPb > 0 && <em>({stats.triggeredPb} 个有自动触发)</em>}
            </span>
          </div>
          <div className="ws-guide__actions">
            <span
              className="ws-guide__action"
              role="button"
              tabIndex={0}
              onClick={focusChatInput}
              onKeyDown={(e) => { if (e.key === 'Enter') focusChatInput(); }}
            >
              <MessageOutlined /> 随便问问
            </span>
            <Link className="ws-guide__action" href={`/workspaces/detail/playbooks?id=${workspaceCode}`}>
              <PlayCircleOutlined /> 跑一个剧本
            </Link>
            <Link className="ws-guide__action" href={`/workspaces/detail/tasks?id=${workspaceCode}&tab=triggers`}>
              <ScheduleOutlined /> 订阅提醒
            </Link>
            <Link className="ws-guide__action" href={`/workspaces/detail/assets?id=${workspaceCode}&tab=data`}>
              <DatabaseOutlined /> 看看数据资产
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
