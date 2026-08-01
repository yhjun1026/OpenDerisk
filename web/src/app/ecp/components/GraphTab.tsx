'use client';

import { apiInterceptors } from '@/client/api';
import { EcpGraph, getEcpGraph } from '@/client/api/ecp';
import { useLoadGraph, SigmaContainer } from '@react-sigma/core';
import '@react-sigma/core/lib/style.css';
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import { Spin } from 'antd';
import { useRequest } from 'ahooks';
import { useEffect } from 'react';

import { Dot, EcpEmpty } from './common';

// Canvas hex colors aligned with ecp-dot type colors.
const HEX: Record<string, string> = {
  entity: '#4f46e5',
  metric: '#22c55e',
  relation: '#f59e0b',
  dimension: '#722ed1',
  default: '#8a92a6',
};

function GraphLoader({ data }: { data: EcpGraph }) {
  const loadGraph = useLoadGraph();

  useEffect(() => {
    // graphology-types is not resolvable in this repo (same workaround as
    // knowledge-vault/GraphCanvas): keep the instance untyped.
    const graph: any = new Graph();
    const degrees = new Map<string, number>();
    for (const l of data.links) {
      degrees.set(l.source, (degrees.get(l.source) || 0) + 1);
      degrees.set(l.target, (degrees.get(l.target) || 0) + 1);
    }
    const maxDegree = Math.max(1, ...degrees.values());

    for (const n of data.nodes) {
      const degree = degrees.get(n.id) || 0;
      const proposed = n.status !== 'confirmed';
      graph.addNode(n.id, {
        label: `${n.name ?? n.id}${proposed ? ' 🟡' : ''}`,
        size: 4 + Math.sqrt(degree / maxDegree) * 14,
        color: HEX[n.obj_type] ?? HEX.default,
        forceLabel: true,
        x: Math.random() * 100,
        y: Math.random() * 100,
      });
    }
    for (const l of data.links) {
      if (!graph.hasNode(l.source) || !graph.hasNode(l.target)) continue;
      const key = `${l.source}-[${l.edge_type}]->${l.target}`;
      if (!graph.hasEdge(key)) {
        graph.addEdgeWithKey(key, l.source, l.target, {
          label: l.edge_type,
          size: 1,
          color: '#94a3b8',
        });
      }
    }

    if (graph.order > 1) {
      forceAtlas2.assign(graph, {
        iterations: 120,
        settings: {
          ...forceAtlas2.inferSettings(graph),
          gravity: 1,
          strongGravityMode: true,
          barnesHutOptimize: graph.order > 50,
        },
      });
    }
    loadGraph(graph);
  }, [data, loadGraph]);

  return null;
}

/**
 * Semantic lineage graph: hard-layer objects as nodes (colored by type,
 * 🟡 marks proposed), materialized edges as links.
 */
export default function GraphTab({ workspaceId }: { workspaceId: string }) {
  const { data, loading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getEcpGraph(workspaceId));
      if (err) throw err;
      return res;
    },
    { refreshDeps: [workspaceId] },
  );

  if (loading) return <Spin style={{ display: 'block', margin: '64px auto' }} />;
  if (!data?.nodes?.length) {
    return (
      <EcpEmpty
        title="语义图为空"
        desc="确认语义对象后，对象间引用（belongs_to / binding / joins）会在此成图"
      />
    );
  }

  return (
    <div className="ecp-graph">
      <div className="ecp-graph__legend">
        {(['entity', 'metric', 'relation', 'dimension'] as const).map(tp => (
          <span key={tp} className="ecp-graph__legend-item">
            <Dot kind={`ecp-dot--${tp}`} />
            {tp}
          </span>
        ))}
        <span className="ecp-graph__legend-item">🟡 = proposed（未确认）</span>
      </div>
      <SigmaContainer style={{ height: '100%', width: '100%' }}>
        <GraphLoader data={data} />
      </SigmaContainer>
    </div>
  );
}
