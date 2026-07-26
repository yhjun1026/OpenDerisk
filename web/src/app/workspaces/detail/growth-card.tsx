'use client';

import { Card, Statistic } from 'antd';
import { useRequest } from 'ahooks';
import { GET } from '@/client/api';

export interface GrowthCardProps {
  workspaceId: number;
}

interface GrowthData {
  assets_count: number;
  evolution_proposals_count: number;
  tasks_trend: Array<{ date: string; count: number }>;
  knowledge_graph_nodes: number;
}

export function GrowthCard({ workspaceId }: GrowthCardProps) {
  const { data, loading } = useRequest(
    async () => {
      const res = await GET<null, GrowthData>(
        `/api/v1/serve_workspace_service/workspaces/${workspaceId}/growth`,
      );
      if (res.data?.success && res.data.data) {
        return res.data.data;
      }
      return {
        assets_count: 0,
        evolution_proposals_count: 0,
        tasks_trend: [],
        knowledge_graph_nodes: 0,
      };
    },
    { refreshDeps: [workspaceId] },
  );

  const totalTasks = (data?.tasks_trend || []).reduce((sum, t) => sum + t.count, 0);
  // 全部为 0 时不渲染占位大 0,避免空态噪声 —— 空间还没有沉淀时引导交给快捷发起区
  const allZero =
    !loading &&
    (data?.assets_count ?? 0) === 0 &&
    (data?.evolution_proposals_count ?? 0) === 0 &&
    (data?.knowledge_graph_nodes ?? 0) === 0 &&
    totalTasks === 0;

  if (allZero) return null;

  return (
    <Card size="small" title="本月空间成长" className="ws-growth-card" loading={loading}>
      <Statistic title="沉淀 Asset" value={data?.assets_count ?? 0} />
      <Statistic title="Playbook 演化提议" value={data?.evolution_proposals_count ?? 0} />
      <Statistic title="知识图谱节点" value={data?.knowledge_graph_nodes ?? 0} />
      <div className="ws-growth-card__trend">
        <span className="ws-growth-card__trend-label">任务趋势</span>
        <span className="ws-growth-card__trend-value">
          {totalTasks} 次 (30 天)
        </span>
      </div>
    </Card>
  );
}
