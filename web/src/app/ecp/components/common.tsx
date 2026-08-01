'use client';

import { apiInterceptors } from '@/client/api';
import { EcpSemanticObject, getEcpObjectVersions } from '@/client/api/ecp';
import { useRequest } from 'ahooks';
import { Drawer, Table } from 'antd';
import React from 'react';

import '../ecp.css';

export const TYPE_DOT: Record<string, string> = {
  entity: 'ecp-dot--entity',
  metric: 'ecp-dot--metric',
  relation: 'ecp-dot--relation',
  dimension: 'ecp-dot--dimension',
  claim: 'ecp-dot--metric',
  terminology: 'ecp-dot--entity',
  policy: 'ecp-dot--relation',
};

const STATUS_DOT: Record<string, { dot: string; label: string }> = {
  confirmed: { dot: 'ecp-dot--success', label: 'confirmed' },
  proposed: { dot: 'ecp-dot--warning', label: 'proposed' },
  rejected: { dot: 'ecp-dot--danger', label: 'rejected' },
  deprecated: { dot: 'ecp-dot--neutral', label: 'deprecated' },
  superseded: { dot: 'ecp-dot--neutral', label: 'superseded' },
};

export function Dot({ kind }: { kind: string }) {
  return <span className={`ecp-dot ${kind}`} />;
}

export function StatusTag({ status }: { status: string }) {
  const meta = STATUS_DOT[status] ?? { dot: 'ecp-dot--neutral', label: status };
  return (
    <span className="ecp-status">
      <Dot kind={meta.dot} />
      {status === 'confirmed' ? `✅ ${meta.label}` : meta.label}
    </span>
  );
}

export function TypeChip({ type }: { type: string }) {
  return (
    <span className="ecp-type-chip">
      <Dot kind={TYPE_DOT[type] ?? 'ecp-dot--neutral'} />
      {type}
    </span>
  );
}

/** Natural-language-ish summary of a payload for list/cards. */
export function summarizePayload(obj: EcpSemanticObject): string {
  const p = obj.payload || {};
  if (obj.obj_type === 'entity') {
    const binding = p.binding || {};
    return `绑定表 ${binding.table ?? '?'}（PK: ${binding.pk ?? '?'}）· 默认过滤 ${(p.default_filters || []).join('; ') || '无'}`;
  }
  if (obj.obj_type === 'metric') {
    return `口径 ${p.expression ?? '?'} · 附加过滤 ${(p.extra_filters || []).join('; ') || '无'} · 粒度 ${(p.grain || []).join('/') || '未定义'} · 单位 ${p.unit ?? '-'}`;
  }
  if (obj.obj_type === 'relation') {
    return `join 路径 ${p.path ?? '?'}（${p.cardinality ?? '?'}）`;
  }
  if (obj.obj_type === 'dimension') {
    const values = (p.values || []).map((v: any) => v.label).join('、');
    return `维度列 ${p.column ?? '?'} · 值 ${values || '（待确认）'}`;
  }
  if (obj.obj_type === 'claim') {
    const binding = p.binding || {};
    return `${p.text ?? '?'} · 出处 ${binding.doc_id ?? '?'}${binding.anchor ? `@${binding.anchor}` : ''}`;
  }
  if (obj.obj_type === 'terminology') {
    return `定义 ${(p.definition ?? '?').slice(0, 80)} · 别名 ${(p.aliases || []).join('/') || '无'}`;
  }
  if (obj.obj_type === 'policy') {
    return `${p.rule ?? '?'} · 条件 ${p.condition ?? '通用'}`;
  }
  return '';
}

export function EcpEmpty({
  title,
  desc,
  action,
}: {
  title: string;
  desc?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="ecp-empty">
      <div className="ecp-empty__title">{title}</div>
      {desc && <div className="ecp-empty__desc">{desc}</div>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="ecp-drawer__kv">
      <div className="ecp-drawer__kv-key">{k}</div>
      <div className="ecp-drawer__kv-val">{v}</div>
    </div>
  );
}

export function ObjectDetailDrawer({
  obj,
  open,
  onClose,
}: {
  obj: EcpSemanticObject | null;
  open: boolean;
  onClose: () => void;
}) {
  const { data: versions } = useRequest(
    async () => {
      if (!obj) return [];
      const [err, res] = await apiInterceptors(
        getEcpObjectVersions(obj.id, obj.workspace_id),
      );
      return err ? [] : res ?? [];
    },
    { refreshDeps: [obj?.id, open], ready: open && !!obj },
  );

  if (!obj) return null;
  return (
    <Drawer
      className="ecp-drawer"
      title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <TypeChip type={obj.obj_type} />
          <span style={{ fontWeight: 650 }}>{obj.id}</span>
          <span style={{ color: 'var(--ink-400)', fontSize: 12 }}>v{obj.version}</span>
        </span>
      }
      width={640}
      open={open}
      onClose={onClose}
    >
      <div className="ecp-drawer__section">
        <div className="ecp-drawer__section-title">基本信息</div>
        <KV k="状态" v={<StatusTag status={obj.status} />} />
        <KV k="名称" v={obj.name ?? '-'} />
        <KV k="别名" v={(obj.payload?.aliases || []).join(' / ') || '-'} />
        <KV k="说明" v={summarizePayload(obj)} />
        <KV k="来源" v={obj.source ?? '-'} />
        <KV
          k="确认"
          v={obj.confirmed_by ? `${obj.confirmed_by} @ ${obj.confirmed_at ?? ''}` : '未确认'}
        />
      </div>

      {!!obj.evidence?.length && (
        <div className="ecp-drawer__section">
          <div className="ecp-drawer__section-title">证据引文</div>
          {obj.evidence.map((ev, i) => (
            <div key={i} className="ecp-proposal__evidence" style={{ marginTop: i ? 8 : 0 }}>
              {ev.source ?? '来源未知'}：{ev.quote ?? ''}
            </div>
          ))}
        </div>
      )}

      <div className="ecp-drawer__section">
        <div className="ecp-drawer__section-title">Payload</div>
        <pre
          style={{
            maxHeight: 300,
            overflow: 'auto',
            fontSize: 12,
            margin: 0,
            color: 'var(--ink-700)',
          }}
        >
          {JSON.stringify(obj.payload, null, 2)}
        </pre>
      </div>

      <div className="ecp-drawer__section">
        <div className="ecp-drawer__section-title">版本历史</div>
        <Table
          size="small"
          rowKey="version"
          pagination={false}
          dataSource={versions ?? []}
          columns={[
            { title: 'v', dataIndex: 'version', width: 48 },
            {
              title: '状态',
              dataIndex: 'status',
              width: 150,
              render: (s: string) => <StatusTag status={s} />,
            },
            { title: '创建', dataIndex: 'created_by', width: 90 },
            { title: '时间', dataIndex: 'created_at', ellipsis: true },
            {
              title: 'supersedes',
              dataIndex: 'supersedes',
              width: 100,
              render: (v: number | null) => v ?? '-',
            },
          ]}
        />
      </div>
    </Drawer>
  );
}
