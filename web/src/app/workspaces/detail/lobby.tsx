'use client';

import { Tag } from 'antd';
import { useRequest } from 'ahooks';
import {
  ThunderboltOutlined,
  CloudServerOutlined,
  SendOutlined,
} from '@ant-design/icons';
import {
  apiInterceptors,
  listArtifacts,
  listDeliveries,
} from '@/client/api';
import { listInbox, type InboxItem } from '@/client/api/workspace';
import { GrowthCard } from './growth-card';
import { SpaceGuideCard } from './space-guide-card';
import './lobby.css';

export interface LobbyProps {
  workspaceId: number;
  workspaceCode: string;
  onSelectTask: (taskId: number) => void;
  onSelectArtifact?: (artifact: any) => void;
}

function SectionHead({
  icon,
  title,
  count,
  sub,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  sub?: string;
}) {
  return (
    <div className="ws-lobby__section-head">
      <span className="ws-lobby__section-icon">{icon}</span>
      <span className="ws-lobby__section-title">{title}</span>
      {typeof count === 'number' && <span className="ws-lobby__section-count">{count}</span>}
      {sub && <span className="ws-lobby__section-sub">{sub}</span>}
    </div>
  );
}

function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="ws-lobby__empty">
      <div className="ws-lobby__empty-title">{title}</div>
      {hint && <div className="ws-lobby__empty-hint">{hint}</div>}
    </div>
  );
}

export function Lobby({
  workspaceId,
  workspaceCode,
  onSelectTask,
  onSelectArtifact,
}: LobbyProps) {
  const { data: inboxRes } = useRequest(
    async () => apiInterceptors(listInbox(workspaceId)),
    { refreshDeps: [workspaceId] },
  );
  const inboxItems: InboxItem[] = (Array.isArray(inboxRes?.[1]) ? inboxRes[1] : (inboxRes?.[1]?.data || [])) as InboxItem[];

  const { data: deliveriesRes } = useRequest(
    async () => apiInterceptors(listDeliveries({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const deliveries = deliveriesRes?.[1];

  const { data: artifactsRes } = useRequest(
    async () => apiInterceptors(listArtifacts({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const artifacts = artifactsRes?.[1];

  const recentDeliveries = (deliveries || []).slice(0, 3);
  const recentArtifacts = (artifacts || []).slice(0, 4);

  return (
    <div className="ws-lobby">
      <div className="ws-lobby__scroll">
        {/* 空间导览(新人第一小时:有什么/会什么/怎么干) */}
        <SpaceGuideCard workspaceId={workspaceId} workspaceCode={workspaceCode} />

        {/* 空间成长概览(横向紧凑条) */}
        <GrowthCard workspaceId={workspaceId} />

        <div className="ws-lobby__grid">
          {/* 我的待办(个人工作台) */}
          <section className="ws-lobby__section">
            <SectionHead icon={<ThunderboltOutlined />} title="我的待办" count={inboxItems.length} />
            <div className="ws-lobby__section-body">
              {inboxItems.length === 0 && (
                <EmptyState title="暂无待办" hint="需要你介入的事项会出现在这里" />
              )}
              {inboxItems.slice(0, 5).map((item) => (
                <div
                  key={item.id}
                  className="ws-lobby__task-card"
                  role="button"
                  tabIndex={0}
                  onClick={() => item.source_type === 'task' && onSelectTask(Number(item.source_id))}
                  onKeyDown={(e) => { if (e.key === 'Enter' && item.source_type === 'task') onSelectTask(Number(item.source_id)); }}
                >
                  <div className="ws-lobby__task-title">{item.title}</div>
                  <div className="ws-lobby__task-meta">
                    <Tag color="blue">{item.source_type}</Tag>
                    <span>{item.visibility === 'shared' ? '共享' : '个人'}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* 最近产出 */}
          <section className="ws-lobby__section">
            <SectionHead icon={<CloudServerOutlined />} title="最近产出" count={recentArtifacts.length} />
            <div className="ws-lobby__section-body">
              {recentArtifacts.length === 0 && (
                <EmptyState title="暂无产出物" hint="任务产出的报告、数据集会沉淀在这里" />
              )}
              {recentArtifacts.map((a: any) => (
                <div
                  key={a.id}
                  className="ws-lobby__hosted-card"
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelectArtifact?.(a)}
                  onKeyDown={(e) => { if (e.key === 'Enter') onSelectArtifact?.(a); }}
                >
                  <span className="ws-lobby__hosted-title">{a.title || `artifact_${a.id}`}</span>
                  <Tag color="blue">{a.type}</Tag>
                </div>
              ))}
            </div>
          </section>

          {/* 最近交付 */}
          <section className="ws-lobby__section">
            <SectionHead icon={<SendOutlined />} title="最近交付" count={recentDeliveries.length} />
            <div className="ws-lobby__section-body">
              {recentDeliveries.length === 0 && (
                <EmptyState title="暂无交付记录" hint="交付物发送后会记录在这里" />
              )}
              {recentDeliveries.map((d: any) => (
                <div key={d.id} className="ws-lobby__delivery-item">
                  <Tag>{d.category}</Tag>
                  <span className="ws-lobby__delivery-channel">{d.channel}</span>
                  <span className="ws-lobby__delivery-status">{d.status}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
