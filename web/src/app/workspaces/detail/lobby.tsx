'use client';

import { Button, Tag, message } from 'antd';
import { useRequest } from 'ahooks';
import {
  ThunderboltOutlined,
  CloudServerOutlined,
  SendOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import {
  apiInterceptors,
  createTask,
  listTasks,
  listArtifacts,
  listDeliveries,
  listPlaybooks,
} from '@/client/api';
import { GrowthCard } from './growth-card';
import './lobby.css';

export interface LobbyProps {
  workspaceId: number;
  workspaceCode: string;
  onSelectTask: (taskId: number) => void;
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
  onSelectTask,
}: LobbyProps) {
  const handleQuickStart = async (playbookId: number) => {
    const [err, task] = await apiInterceptors(
      createTask({ workspace_id: workspaceId, playbook_id: playbookId })
    );
    if (err || !task) {
      message.error('创建任务失败，请重试');
      return;
    }
    onSelectTask(task.id);
  };
  const { data: tasksRes } = useRequest(
    async () => apiInterceptors(listTasks({ workspace_id: workspaceId, status: 'running' })),
    { refreshDeps: [workspaceId] },
  );
  const tasks = tasksRes?.[1];

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

  const { data: playbooksRes } = useRequest(
    async () => apiInterceptors(listPlaybooks({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const playbooks = playbooksRes?.[1];

  const runningTasks = (tasks || []).slice(0, 5);
  const recentDeliveries = (deliveries || []).slice(0, 3);
  const recentArtifacts = (artifacts || []).slice(0, 4);

  return (
    <div className="ws-lobby">
      <div className="ws-lobby__scroll">
        {/* 空间成长概览(横向紧凑条) */}
        <GrowthCard workspaceId={workspaceId} />

        <div className="ws-lobby__grid">
          {/* 进行中任务 */}
          <section className="ws-lobby__section">
            <SectionHead icon={<ThunderboltOutlined />} title="进行中任务" count={runningTasks.length} />
            <div className="ws-lobby__section-body">
              {runningTasks.length === 0 && (
                <EmptyState title="暂无进行中任务" hint="在下方输入指令,或从快捷发起选择一个剧本" />
              )}
              {runningTasks.map((t: any) => (
                <div
                  key={t.id}
                  className="ws-lobby__task-card"
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelectTask(t.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter') onSelectTask(t.id); }}
                >
                  <div className="ws-lobby__task-title">{t.title}</div>
                  <div className="ws-lobby__task-meta">
                    <Tag color="blue">{t.status}</Tag>
                    <span>{t.triggered_by}</span>
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
                <div key={a.id} className="ws-lobby__hosted-card">
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

          {/* 快捷发起 */}
          <section className="ws-lobby__section">
            <SectionHead icon={<RocketOutlined />} title="快捷发起" sub="选择剧本,一键发起任务" />
            <div className="ws-lobby__section-body ws-lobby__quick">
              {(playbooks || []).slice(0, 4).map((p: any) => (
                <Button
                  key={p.id}
                  className="ws-lobby__quick-btn"
                  onClick={() => handleQuickStart(p.id)}
                >
                  <span className="ws-lobby__quick-name">发起: {p.name}</span>
                  {(p.scenario_type || p.task_type) && (
                    <span className="ws-lobby__quick-desc">{p.scenario_type || p.task_type}</span>
                  )}
                </Button>
              ))}
              {(playbooks || []).length === 0 && (
                <EmptyState
                  title="空间还没有剧本"
                  hint="去剧本管理创建一个,或直接在底部输入框下指令"
                />
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
