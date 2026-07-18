'use client';

import React, { useMemo, useState } from 'react';
import { Tooltip } from 'antd';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  PauseCircleOutlined,
  SyncOutlined,
  DownOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import classNames from 'classnames';
import { ee, EVENTS } from '@/utils/event-emitter';
import { getToolNameIcon, formatArgsSummary } from '../VisAgentPlanCard';

/**
 * VisAgentPlanGroupCard — 连续同工具步骤的聚合卡片。
 *
 * 由 groupConsecutivePlanCards 在渲染前把相邻的同 title d-agent-plan 围栏
 * 合并为一个 d-agent-plan-group 围栏。收起时只显示一行摘要(工具名 + 数量),
 * 展开时以时间线轨道列出每个步骤。组内有 running 步骤时自动展开。
 */

interface GroupItem {
  uid: string;
  title?: string;
  description?: string;
  status?: string;
  tool_name?: string;
}

interface GroupData {
  uid: string;
  title: string;
  items: GroupItem[];
}

const statusIcon = (status?: string) => {
  switch (status) {
    case 'running':
      return <LoadingOutlined style={{ color: '#1677ff', fontSize: 12 }} spin />;
    case 'failed':
      return <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 12 }} />;
    case 'waiting':
      return <PauseCircleOutlined style={{ color: '#f5a623', fontSize: 12 }} />;
    case 'retrying':
      return <SyncOutlined style={{ color: '#1677ff', fontSize: 12 }} />;
    case 'complete':
    default:
      return <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12 }} />;
  }
};

const VisAgentPlanGroupCard: React.FC<{ data: GroupData }> = ({ data }) => {
  const items = useMemo(() => (Array.isArray(data.items) ? data.items : []), [data.items]);
  const anyRunning = items.some((i) => i.status === 'running' || i.status === 'retrying');
  const failedCount = items.filter((i) => i.status === 'failed').length;
  // null = 未手动操作,跟随自动规则(running 时展开);用户点击后尊重手动状态
  const [manualExpanded, setManualExpanded] = useState<boolean | null>(null);
  const expanded = manualExpanded ?? anyRunning;

  const toolMeta = getToolNameIcon(data.items?.[0]?.tool_name, data.title);
  const chipColor = toolMeta?.color ?? '#64748b';

  const handleItemClick = (uid: string) => {
    if (!uid) return;
    const convId =
      typeof window !== 'undefined'
        ? new URLSearchParams(window.location.search).get('conv_uid') || ''
        : '';
    ee.emit(EVENTS.CLICK_FOLDER, { uid, conv_id: convId });
    ee.emit(EVENTS.OPEN_PANEL);
  };

  return (
    <div className="w-fit max-w-[85%] rounded-[10px] border border-slate-200/80 bg-white/70 shadow-[0_1px_2px_rgba(15,23,42,0.03)] transition-all hover:bg-white">
      {/* Summary row — always visible, toggles the group */}
      <button
        className="flex items-center gap-1.5 w-full pl-1 pr-2.5 py-[3px]"
        onClick={() => setManualExpanded(!expanded)}
      >
        <span
          className="w-[19px] h-[19px] rounded-md inline-flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: `${chipColor}14`, color: chipColor }}
        >
          {toolMeta ? (
            React.cloneElement(toolMeta.icon as React.ReactElement, { style: { fontSize: 11 } })
          ) : (
            <ToolOutlined style={{ fontSize: 11 }} />
          )}
        </span>
        <span className="text-xs font-medium text-slate-700">{data.title}</span>
        <span className="text-[11px] text-slate-400 tabular-nums">× {items.length}</span>
        {failedCount > 0 && (
          <span className="text-[10px] px-1 rounded bg-red-50 text-red-500 tabular-nums">
            {failedCount} 失败
          </span>
        )}
        <DownOutlined
          className={classNames(
            'text-[9px] text-slate-300 ml-1 transition-transform duration-200',
            expanded && 'rotate-180',
          )}
        />
      </button>

      {/* Expanded: timeline of individual steps */}
      {expanded && (
        <div className="flex flex-col px-1 pb-1">
          {items.map((item, index) => (
            <div key={item.uid ?? index} className="relative flex items-stretch">
              {/* Timeline rail: chip column with connector to the next row */}
              <div className="relative w-[19px] flex-shrink-0">
                {index < items.length - 1 && (
                  <span className="absolute left-1/2 -translate-x-1/2 top-[22px] bottom-[-3px] w-[2px] rounded-full bg-slate-300/70" />
                )}
                <span
                  className="relative z-10 w-[19px] h-[19px] mt-[3px] rounded-md inline-flex items-center justify-center flex-shrink-0"
                  style={{ backgroundColor: `${chipColor}14`, color: chipColor }}
                >
                  {toolMeta ? (
                    React.cloneElement(toolMeta.icon as React.ReactElement, { style: { fontSize: 10 } })
                  ) : (
                    <ToolOutlined style={{ fontSize: 10 }} />
                  )}
                </span>
              </div>
              <Tooltip title={item.description ? `${item.title} ${item.description}` : item.title}>
                <button
                  className={classNames(
                    'flex items-center gap-1.5 flex-1 min-w-0 ml-1.5 px-1.5 py-[5px] rounded-md text-left transition-colors',
                    'hover:bg-slate-50',
                    item.status === 'running' && 'bg-blue-50/60',
                  )}
                  onClick={() => handleItemClick(item.uid)}
                >
                  <span className="text-[11px] text-slate-500 truncate flex-1 min-w-0">
                    {formatArgsSummary(String(item.description ?? '')) || item.title}
                  </span>
                  <span className="flex-shrink-0">{statusIcon(item.status)}</span>
                </button>
              </Tooltip>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default React.memo(VisAgentPlanGroupCard);
