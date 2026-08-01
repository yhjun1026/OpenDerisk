'use client';

import { apiInterceptors } from '@/client/api';
import {
  EcpSemanticObject,
  getEcpInbox,
  listEcpAssets,
  listEcpObjects,
} from '@/client/api/ecp';
import { useRequest } from 'ahooks';

import { Dot, EcpEmpty, StatusTag, TYPE_DOT } from './common';

/** Overview: semantic-asset solidification dashboard. */
export default function OverviewTab({
  onGoInbox,
  workspaceId,
}: {
  onGoInbox: () => void;
  workspaceId: string;
}) {
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
        getEcpInbox({ page_size: 5, workspace_id: workspaceId }),
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

  const confirmedCount = confirmed?.total_count ?? 0;
  const pendingCount = inbox?.total_count ?? 0;
  const rate =
    confirmedCount + pendingCount
      ? Math.round((confirmedCount / (confirmedCount + pendingCount)) * 100)
      : 0;

  const metrics = [
    { label: '已确认语义对象', num: confirmedCount, dot: 'ecp-dot--success', foot: 'confirmed 口径即刻参与查询' },
    { label: '待确认提案', num: pendingCount, dot: 'ecp-dot--warning', foot: '确认前不影响任何查询' },
    { label: '登记资产', num: assets?.length ?? 0, dot: 'ecp-dot--entity', foot: 'DB / 知识空间 / 文档 / API 引用' },
    { label: '资产固化率', num: `${rate}%`, dot: 'ecp-dot--metric', foot: '北极星：⚠️→✅ 的转化程度' },
  ];

  return (
    <>
      <div className="ecp-grid ecp-grid--4" style={{ marginBottom: 16 }}>
        {metrics.map((m, i) => (
          <div key={m.label} className={`ecp-metric-card ecp-rise ecp-rise--${i + 1}`}>
            <div className="ecp-metric-card__head">
              <Dot kind={m.dot} />
              {m.label}
            </div>
            <div className="ecp-metric-card__num">{m.num}</div>
            <div className="ecp-metric-card__foot">{m.foot}</div>
          </div>
        ))}
      </div>

      <div className="ecp-grid ecp-grid--2">
        <div className="ecp-card">
          <div className="ecp-card__title">
            待确认 Top 5
            <span className="ecp-card__title-link" onClick={onGoInbox}>
              去收件箱 →
            </span>
          </div>
          {(inbox?.items ?? []).length === 0 ? (
            <EcpEmpty title="收件箱为空" desc="没有等待确认的提案" />
          ) : (
            (inbox?.items ?? []).map((obj: EcpSemanticObject) => (
              <div
                key={`${obj.id}@${obj.version}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 4px',
                  borderBottom: '1px solid var(--line-soft)',
                }}
              >
                <Dot kind={TYPE_DOT[obj.obj_type] ?? 'ecp-dot--neutral'} />
                <span style={{ fontWeight: 600, color: 'var(--ink-900)', fontSize: 13 }}>
                  {obj.id}
                </span>
                <span style={{ color: 'var(--ink-400)', fontSize: 12, flex: 1 }}>
                  {obj.name ?? ''}
                </span>
                <StatusTag status={obj.status} />
              </div>
            ))
          )}
        </div>

        <div className="ecp-card">
          <div className="ecp-card__title">资产状态</div>
          {(assets ?? []).length === 0 ? (
            <EcpEmpty
              title="尚未登记资产"
              desc="到「资产层」接入 DB 数据源或知识空间"
            />
          ) : (
            (assets ?? []).map(a => (
              <div
                key={a.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 4px',
                  borderBottom: '1px solid var(--line-soft)',
                }}
              >
                <Dot kind={`ecp-dot--${a.kind}`} />
                <span style={{ fontSize: 13, color: 'var(--ink-700)', flex: 1 }}>
                  {a.kind} · <code style={{ fontSize: 12 }}>{a.ref_id}</code>
                </span>
                <span className="ecp-status">
                  <Dot kind={a.status === 'active' ? 'ecp-dot--success' : 'ecp-dot--neutral'} />
                  {a.status}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
