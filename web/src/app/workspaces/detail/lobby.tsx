'use client';

import { Tag } from 'antd';
import { useRequest } from 'ahooks';
import {
  CloudServerOutlined,
  SendOutlined,
  DeploymentUnitOutlined,
} from '@ant-design/icons';
import {
  apiInterceptors,
  listArtifacts,
  listDeliveries,
} from '@/client/api';
import { listEcpObjects } from '@/client/api/ecp';
import { GrowthCard } from './growth-card';
import { SpaceGuideCard } from './space-guide-card';
import './lobby.css';

export interface LobbyProps {
  workspaceId: number;
  workspaceCode: string;
  // 预留钩子:内容区域(大厅)开任务入口,待办卡片移除后待后续接 UI。
  onSelectTask?: (taskId: number) => void;
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
  onSelectArtifact,
}: LobbyProps) {
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

  // ECP 语义资产:派生 ECP workspace(ecp_<workspace_code>),拉取已确认语义对象
  const ecpWsId = workspaceCode ? `ecp_${workspaceCode}` : null;
  const { data: semanticRes } = useRequest(
    async () => {
      if (!ecpWsId) return null;
      const [err, res] = await apiInterceptors(
        listEcpObjects({ workspace_id: ecpWsId, status: 'confirmed', page_size: 50 }),
      );
      if (err) return null;
      return res;
    },
    { ready: !!ecpWsId, refreshDeps: [ecpWsId] },
  );
  const semantics = semanticRes?.items ?? [];

  const recentDeliveries = (deliveries || []).slice(0, 3);
  const recentArtifacts = (artifacts || []).slice(0, 4);
  const recentSemantics = semantics.slice(0, 5);

  return (
    <div className="ws-lobby">
      <div className="ws-lobby__scroll">
        {/* 空间导览(新人第一小时:有什么/会什么/怎么干) */}
        <SpaceGuideCard workspaceId={workspaceId} workspaceCode={workspaceCode} />

        {/* 空间成长概览(横向紧凑条) */}
        <GrowthCard workspaceId={workspaceId} workspaceCode={workspaceCode} />

        <div className="ws-lobby__grid">
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

          {/* 语义资产 */}
          <section className="ws-lobby__section">
            <SectionHead
              icon={<DeploymentUnitOutlined />}
              title="语义资产"
              count={recentSemantics.length}
              sub={semantics.length > recentSemantics.length ? `共 ${semantics.length}` : undefined}
            />
            <div className="ws-lobby__section-body">
              {recentSemantics.length === 0 && (
                <EmptyState
                  title="暂无已确认语义资产"
                  hint="在「资产层」生成提案并在「收件箱」确认后,这里会展示语义对象"
                />
              )}
              {recentSemantics.map((s: any) => (
                <div key={s.id} className="ws-lobby__hosted-card">
                  <span className="ws-lobby__hosted-title">{s.name || s.id}</span>
                  <Tag color="blue">{s.obj_type}</Tag>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
