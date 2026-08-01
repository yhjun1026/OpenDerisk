'use client';

import { apiInterceptors } from '@/client/api';
import { EcpSemanticObject, listEcpObjects } from '@/client/api/ecp';
import { useRequest } from 'ahooks';
import { Input, Select, Spin } from 'antd';
import { useState } from 'react';

import {
  Dot,
  EcpEmpty,
  ObjectDetailDrawer,
  StatusTag,
  summarizePayload,
  TYPE_DOT,
} from './common';

const TYPES = ['entity', 'metric', 'relation', 'dimension', 'claim', 'terminology', 'policy'] as const;

function useTypeCount(obj_type: string, workspaceId: string) {
  return useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listEcpObjects({ obj_type, page_size: 1, workspace_id: workspaceId }),
      );
      return err ? 0 : res?.total_count ?? 0;
    },
    { refreshDeps: [workspaceId] },
  );
}

function SideGroup({
  type,
  active,
  onSelect,
  workspaceId,
}: {
  type: string | undefined;
  active: boolean;
  onSelect: () => void;
  workspaceId: string;
}) {
  const { data: count } = useTypeCount(type ?? '', workspaceId);
  return (
    <div
      className={`ecp-semantics__group ${active ? 'ecp-semantics__group--active' : ''}`}
      onClick={onSelect}
    >
      <span className="ecp-semantics__group-name">
        <Dot kind={type ? (TYPE_DOT[type] ?? 'ecp-dot--neutral') : 'ecp-dot--neutral'} />
        {type ?? '全部'}
      </span>
      {type && <span className="ecp-semantics__count">{count ?? 0}</span>}
    </div>
  );
}

/** Hard semantic layer: the enterprise Wikidata browser. */
export default function SemanticsTab({ workspaceId }: { workspaceId: string }) {
  const [typeFilter, setTypeFilter] = useState<string>();
  const [statusFilter, setStatusFilter] = useState<string>();
  const [keyword, setKeyword] = useState<string>();
  const [detail, setDetail] = useState<EcpSemanticObject | null>(null);

  const { data, loading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listEcpObjects({
          obj_type: typeFilter,
          status: statusFilter,
          keyword,
          page_size: 100,
          workspace_id: workspaceId,
        }),
      );
      if (err) throw err;
      return res;
    },
    { refreshDeps: [typeFilter, statusFilter, keyword, workspaceId] },
  );

  const items = data?.items ?? [];

  return (
    <div className="ecp-semantics">
      <div className="ecp-semantics__side">
        <SideGroup
          type={undefined}
          active={!typeFilter}
          onSelect={() => setTypeFilter(undefined)}
          workspaceId={workspaceId}
        />
        {TYPES.map(tp => (
          <SideGroup
            key={tp}
            type={tp}
            active={typeFilter === tp}
            onSelect={() => setTypeFilter(tp)}
            workspaceId={workspaceId}
          />
        ))}
        <div style={{ padding: '12px 8px 4px' }}>
          <Select
            allowClear
            placeholder="状态"
            size="small"
            style={{ width: '100%' }}
            value={statusFilter}
            onChange={setStatusFilter}
            options={['confirmed', 'proposed', 'rejected', 'deprecated', 'superseded'].map(
              v => ({ value: v, label: v }),
            )}
          />
        </div>
        <div style={{ padding: '8px 8px 4px' }}>
          <Input.Search
            allowClear
            size="small"
            placeholder="搜索"
            onSearch={setKeyword}
          />
        </div>
      </div>

      <div className="ecp-semantics__main">
        {loading ? (
          <Spin style={{ display: 'block', margin: '64px auto' }} />
        ) : items.length === 0 ? (
          <EcpEmpty
            title="语义目录为空"
            desc="到「资产层」生成提案并在「收件箱」确认后，这里会出现已确认的语义资产"
          />
        ) : (
          <div className="ecp-card" style={{ padding: '8px 20px' }}>
            {items.map(obj => (
              <div
                key={`${obj.id}@${obj.version}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '13px 0',
                  borderBottom: '1px solid var(--line-soft)',
                  cursor: 'pointer',
                }}
                onClick={() => setDetail(obj)}
              >
                <Dot kind={TYPE_DOT[obj.obj_type] ?? 'ecp-dot--neutral'} />
                <div style={{ width: 220, flexShrink: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-900)' }}>
                    {obj.id}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--ink-400)' }}>
                    {obj.name ?? ''}
                    {obj.payload?.aliases?.length
                      ? `（${obj.payload.aliases.join('/')}）`
                      : ''}
                  </div>
                </div>
                <div
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 12,
                    color: 'var(--ink-500)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {summarizePayload(obj)}
                </div>
                <StatusTag status={obj.status} />
              </div>
            ))}
          </div>
        )}
      </div>

      <ObjectDetailDrawer obj={detail} open={!!detail} onClose={() => setDetail(null)} />
    </div>
  );
}
