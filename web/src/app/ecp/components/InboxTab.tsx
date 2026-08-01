'use client';

import { apiInterceptors } from '@/client/api';
import {
  confirmEcpObject,
  EcpSemanticObject,
  getEcpInbox,
  rejectEcpObject,
} from '@/client/api/ecp';
import { getUserId } from '@/utils';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Input, Popconfirm, Select, Spin } from 'antd';
import { useState } from 'react';

import {
  Dot,
  EcpEmpty,
  ObjectDetailDrawer,
  StatusTag,
  summarizePayload,
  TYPE_DOT,
} from './common';

function Confidence({ value }: { value?: number | null }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  return (
    <span className="ecp-confidence">
      <span className="ecp-confidence__bar">
        <span className="ecp-confidence__fill" style={{ width: `${pct}%` }} />
      </span>
      {pct}%
    </span>
  );
}

/** Confirmation inbox: proposal cards, the confirmer's home view. */
export default function InboxTab({ workspaceId }: { workspaceId: string }) {
  const { message } = App.useApp();
  const [typeFilter, setTypeFilter] = useState<string>();
  const [keyword, setKeyword] = useState<string>();
  const [detail, setDetail] = useState<EcpSemanticObject | null>(null);

  const { data, loading, refresh } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getEcpInbox({
          obj_type: typeFilter,
          keyword,
          page_size: 50,
          workspace_id: workspaceId,
        }),
      );
      if (err) throw err;
      return res;
    },
    { refreshDeps: [typeFilter, keyword, workspaceId] },
  );

  const { run: confirm, loading: confirming } = useRequest(
    async (obj: EcpSemanticObject) => {
      const user_id = getUserId() ?? 'unknown';
      const [err] = await apiInterceptors(
        confirmEcpObject(obj.id, obj.version, {
          user_id,
          workspace_id: obj.workspace_id,
        }),
      );
      if (err) throw err;
      message.success(`已确认 ${obj.id}，该口径即刻生效`);
      refresh();
    },
    { manual: true },
  );

  const { run: reject } = useRequest(
    async (obj: EcpSemanticObject) => {
      const user_id = getUserId() ?? 'unknown';
      const [err] = await apiInterceptors(
        rejectEcpObject(obj.id, obj.version, {
          user_id,
          workspace_id: obj.workspace_id,
        }),
      );
      if (err) throw err;
      message.success(`已否决 ${obj.id}`);
      refresh();
    },
    { manual: true },
  );

  const items = data?.items ?? [];

  return (
    <>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="类型"
          style={{ width: 140 }}
          value={typeFilter}
          onChange={setTypeFilter}
          options={['entity', 'metric', 'relation', 'dimension'].map(v => ({
            value: v,
            label: v,
          }))}
        />
        <Input.Search
          allowClear
          placeholder="搜索名称 / id"
          style={{ width: 260 }}
          onSearch={setKeyword}
        />
      </div>

      {loading ? (
        <Spin style={{ display: 'block', margin: '64px auto' }} />
      ) : items.length === 0 ? (
        <EcpEmpty
          title="收件箱为空"
          desc={
            <>
              到「资产层」对数据源执行「生成提案」，
              <br />
              AI 提炼的语义资产会在这里等待你确认。
            </>
          }
        />
      ) : (
        items.map((obj, i) => (
          <div key={`${obj.id}@${obj.version}`} className={`ecp-proposal ecp-rise ecp-rise--${(i % 4) + 1}`}>
            <div className="ecp-proposal__head">
              <Dot kind={TYPE_DOT[obj.obj_type] ?? 'ecp-dot--neutral'} />
              <span className="ecp-proposal__id" onClick={() => setDetail(obj)}>
                {obj.id}
              </span>
              <span className="ecp-proposal__name">
                {obj.name ?? ''}
                {obj.payload?.aliases?.length ? `（${obj.payload.aliases.join('/')}）` : ''}
              </span>
              <span style={{ flex: 1 }} />
              <StatusTag status={obj.status} />
            </div>

            <div className="ecp-proposal__summary">{summarizePayload(obj)}</div>

            {!!obj.evidence?.length && (
              <div className="ecp-proposal__evidence">
                「{obj.evidence[0].quote ?? ''}」
                <span style={{ fontStyle: 'normal', color: 'var(--ink-400)' }}>
                  {' '}
                  —— {obj.evidence[0].source ?? '来源未知'}
                </span>
              </div>
            )}

            <div className="ecp-proposal__foot">
              <div className="ecp-proposal__meta">
                <Confidence value={obj.confidence} />
                <span>来源 {obj.source ?? '-'}</span>
                <span>{obj.created_at?.slice(0, 16) ?? ''}</span>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button size="small" onClick={() => setDetail(obj)}>
                  详情
                </Button>
                <Popconfirm title="否决该提案？" onConfirm={() => reject(obj)}>
                  <Button size="small" danger icon={<CloseOutlined />} />
                </Popconfirm>
                <Button
                  size="small"
                  type="primary"
                  icon={<CheckOutlined />}
                  loading={confirming}
                  onClick={() => confirm(obj)}
                >
                  确认生效
                </Button>
              </div>
            </div>
          </div>
        ))
      )}

      <ObjectDetailDrawer obj={detail} open={!!detail} onClose={() => setDetail(null)} />
    </>
  );
}
