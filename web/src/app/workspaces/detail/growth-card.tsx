'use client';

import { Card, Statistic } from 'antd';
import { useRequest } from 'ahooks';
import { GET, apiInterceptors } from '@/client/api';
import { listEcpObjects } from '@/client/api/ecp';

export interface GrowthCardProps {
  workspaceId: number;
  workspaceCode?: string;
}

interface GrowthData {
  assets_count: number;
  evolution_proposals_count: number;
  tasks_trend: Array<{ date: string; count: number }>;
  knowledge_graph_nodes: number;
}

export function GrowthCard({ workspaceId, workspaceCode }: GrowthCardProps) {
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

  // ECP 成长:派生空间 ecp_<code> 已确认的语义口径数
  const ecpWsId = workspaceCode ? `ecp_${workspaceCode}` : null;
  const { data: ecpConfirmedCount } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listEcpObjects({ status: 'confirmed', page_size: 1, workspace_id: ecpWsId! }),
      );
      return err ? 0 : res?.total_count ?? 0;
    },
    { ready: !!ecpWsId, refreshDeps: [ecpWsId] },
  );

  const totalTasks = (data?.tasks_trend || []).reduce((sum, t) => sum + t.count, 0);
  // 全部为 0 时不渲染占位大 0,避免空态噪声 —— 空间还没有沉淀时引导交给快捷发起区
  const allZero =
    !loading &&
    (data?.assets_count ?? 0) === 0 &&
    (data?.evolution_proposals_count ?? 0) === 0 &&
    (data?.knowledge_graph_nodes ?? 0) === 0 &&
    (ecpConfirmedCount ?? 0) === 0 &&
    totalTasks === 0;

  if (allZero) return null;

  return (
    <Card size="small" title="本月空间成长" className="ws-growth-card" loading={loading}>
      <Statistic title="沉淀 Asset" value={data?.assets_count ?? 0} />
      <Statistic title="Playbook 演化提议" value={data?.evolution_proposals_count ?? 0} />
      <Statistic title="知识图谱节点" value={data?.knowledge_graph_nodes ?? 0} />
      {ecpWsId && <Statistic title="语义口径" value={ecpConfirmedCount ?? 0} />}
      <div className="ws-growth-card__trend">
        <span className="ws-growth-card__trend-label">任务趋势</span>
        <span className="ws-growth-card__trend-value">
          {totalTasks} 次 (30 天)
        </span>
      </div>
    </Card>
  );
}
