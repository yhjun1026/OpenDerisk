'use client';

import { apiInterceptors } from '@/client/api';
import {
  EcpAssetRef,
  EcpReadiness,
  generateEcpProposals,
  getEcpReadiness,
  listEcpAssets,
  registerEcpAsset,
} from '@/client/api/ecp';
import { listSpaces } from '@/client/api/knowledge-vault';
import { getDbList } from '@/client/api/request';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Input, Modal, Select, Spin } from 'antd';
import { useState } from 'react';

import { Dot, EcpEmpty } from './common';

const KIND_META: Record<string, { icon: React.ReactNode; label: string }> = {
  db: { icon: <DatabaseOutlined />, label: 'DB 数据源' },
  space: { icon: <FileTextOutlined />, label: '知识空间' },
  document: { icon: <FileTextOutlined />, label: '文档' },
  api: { icon: <ApiOutlined />, label: 'API' },
};

function ReadinessList({ readiness }: { readiness: EcpReadiness }) {
  return (
    <div style={{ marginTop: 10 }}>
      {readiness.checks.map(c => (
        <div
          key={c.item}
          style={{ display: 'flex', gap: 8, fontSize: 12, padding: '3px 0' }}
        >
          {c.ready ? (
            <CheckCircleOutlined style={{ color: 'var(--success)' }} />
          ) : (
            <CloseCircleOutlined style={{ color: 'var(--danger)' }} />
          )}
          <span style={{ color: 'var(--ink-500)' }}>
            {c.item}: {c.detail ?? ''}
          </span>
        </div>
      ))}
    </div>
  );
}

function AssetCard({
  asset,
  onGenerate,
  generating,
  index,
}: {
  asset: EcpAssetRef;
  onGenerate: (a: EcpAssetRef) => void;
  generating: boolean;
  index: number;
}) {
  const [readiness, setReadiness] = useState<EcpReadiness | null>(null);
  const { run: check, loading: checking } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getEcpReadiness(Number(asset.ref_id), asset.workspace_id),
      );
      if (err) throw err;
      setReadiness(res ?? null);
    },
    { manual: true },
  );

  const meta = KIND_META[asset.kind] ?? { icon: null, label: asset.kind };
  return (
    <div className={`ecp-card ecp-rise ecp-rise--${(index % 4) + 1}`} style={{ marginTop: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            background: 'var(--bg-fill)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--ink-500)',
            fontSize: 16,
          }}
        >
          {meta.icon}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-900)' }}>
            {meta.label}
          </div>
          <code style={{ fontSize: 12, color: 'var(--ink-400)' }}>{asset.ref_id}</code>
        </div>
        <span className="ecp-status">
          <Dot kind={asset.status === 'active' ? 'ecp-dot--success' : 'ecp-dot--neutral'} />
          {asset.status}
        </span>
      </div>

      <div
        style={{
          marginTop: 10,
          fontSize: 12,
          color: 'var(--ink-400)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>最近检查 {asset.last_checked_at ?? '从未'}</span>
      </div>

      {asset.kind === 'db' && readiness && <ReadinessList readiness={readiness} />}

      {asset.kind === 'db' && (
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <Button size="small" loading={checking} onClick={() => check()}>
            就绪检查
          </Button>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<ExperimentOutlined />}
            loading={generating}
            onClick={() => onGenerate(asset)}
          >
            生成提案
          </Button>
        </div>
      )}
    </div>
  );
}

/** Asset layer: references to original assets (ECP owns refs, not assets). */
export default function AssetsTab({ workspaceId }: { workspaceId: string }) {
  const { message } = App.useApp();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [kind, setKind] = useState<string>('db');
  const [refId, setRefId] = useState<string>();
  const [genAsset, setGenAsset] = useState<EcpAssetRef | null>(null);
  const [domainHint, setDomainHint] = useState<string>();
  const [genReadiness, setGenReadiness] = useState<EcpReadiness | null>(null);

  const { data: assets, loading, refresh } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listEcpAssets({ workspace_id: workspaceId }),
      );
      if (err) throw err;
      return res ?? [];
    },
    { refreshDeps: [workspaceId] },
  );

  const { data: dbList } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbList());
    return err ? [] : res ?? [];
  });

  const { data: spaceList } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listSpaces());
    return err ? [] : (res as any[]) ?? [];
  });

  const { run: doRegister, loading: registering } = useRequest(
    async () => {
      if (!refId) return;
      const [err] = await apiInterceptors(
        registerEcpAsset({ kind, ref_id: refId, workspace_id: workspaceId }),
      );
      if (err) throw err;
      message.success('资产已登记（只建立引用，不复制数据）');
      setRegisterOpen(false);
      setRefId(undefined);
      refresh();
    },
    { manual: true },
  );

  const { run: openGenerate, loading: checking } = useRequest(
    async (asset: EcpAssetRef) => {
      const [err, res] = await apiInterceptors(
        getEcpReadiness(Number(asset.ref_id), asset.workspace_id),
      );
      if (err) throw err;
      setGenReadiness(res ?? null);
      setGenAsset(asset);
    },
    { manual: true },
  );

  const { run: doGenerate, loading: generating } = useRequest(
    async () => {
      if (!genAsset) return;
      const [err, res] = await apiInterceptors(
        generateEcpProposals({
          datasource_id: Number(genAsset.ref_id),
          workspace_id: workspaceId,
          domain_hint: domainHint || undefined,
        }),
      );
      if (err) throw err;
      message.success(
        `提案完成：处理 ${res?.tables_processed ?? 0} 张表，生成 ${res?.proposals_created ?? 0} 条提案，请到收件箱确认`,
      );
      setGenAsset(null);
      setDomainHint(undefined);
    },
    { manual: true },
  );

  // Workspace-level proposal generation: runs the configured proposal Agent over
  // ALL registered assets (assets passed as dynamic resources). Requires a
  // proposal_agent_id configured in ECP settings; otherwise the backend falls
  // back to per-datasource batch (which needs datasource_id, so this errors).
  const { run: doGenerateAll, loading: generatingAll } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        generateEcpProposals({
          workspace_id: workspaceId,
          domain_hint: domainHint || undefined,
        }),
      );
      if (err) throw err;
      if ((res?.errors ?? []).length > 0 && !res?.proposals_created) {
        message.warning(`提案未生成：${res?.errors?.[0] ?? '未知原因'}`);
        return;
      }
      message.success(
        `工作空间级提案完成：生成 ${res?.proposals_created ?? 0} 条提案，请到收件箱确认`,
      );
      setDomainHint(undefined);
    },
    { manual: true },
  );

  const refOptions =
    kind === 'db'
      ? (dbList ?? []).map((d: any) => ({
          value: String(d.id),
          label: `${d.db_name}（${d.db_type}）`,
        }))
      : kind === 'space'
        ? (spaceList ?? []).map((s: any) => ({
            value: s.slug,
            label: `${s.name ?? s.slug}（${s.slug}）`,
          }))
        : [];

  return (
    <>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <span style={{ fontSize: 13, color: 'var(--ink-500)' }}>
          ECP 不拥有原始资产，只登记引用——就绪后再生成提案。
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Input
            size="small"
            allowClear
            placeholder="领域背景(可选,注入提案提示)"
            value={domainHint}
            onChange={e => setDomainHint(e.target.value)}
            style={{ width: 220 }}
          />
          <Button
            size="small"
            type="primary"
            icon={<ExperimentOutlined />}
            loading={generatingAll}
            onClick={() => doGenerateAll()}
          >
            为所有资产生成提案
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refresh} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterOpen(true)}>
            登记资产
          </Button>
        </div>
      </div>

      {loading ? (
        <Spin style={{ display: 'block', margin: '64px auto' }} />
      ) : (assets ?? []).length === 0 ? (
        <EcpEmpty
          title="尚未登记资产"
          desc="接入 DB 数据源、知识空间或文档，ECP 才能开始提炼业务语义"
          action={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterOpen(true)}>
              登记第一个资产
            </Button>
          }
        />
      ) : (
        <div className="ecp-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
          {(assets ?? []).map((a, i) => (
            <AssetCard
              key={a.id}
              asset={a}
              index={i}
              generating={checking}
              onGenerate={asset => openGenerate(asset)}
            />
          ))}
        </div>
      )}

      <Modal
        title="登记资产引用"
        open={registerOpen}
        onOk={() => doRegister()}
        confirmLoading={registering}
        onCancel={() => setRegisterOpen(false)}
        okText="登记"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span style={{ fontSize: 13 }}>资产类型：</span>
          <Select
            style={{ width: '100%' }}
            value={kind}
            onChange={v => {
              setKind(v);
              setRefId(undefined);
            }}
            options={Object.entries(KIND_META).map(([v, m]) => ({
              value: v,
              label: m.label,
            }))}
          />
          <span style={{ fontSize: 13 }}>引用目标：</span>
          {kind === 'db' || kind === 'space' ? (
            <Select
              showSearch
              style={{ width: '100%' }}
              placeholder={kind === 'db' ? '选择数据源' : '选择知识空间'}
              value={refId}
              onChange={setRefId}
              options={refOptions}
            />
          ) : (
            <Input
              placeholder={
                kind === 'document' ? 'space_slug:verbat_id' : 'api_resource_id（P3 开放）'
              }
              value={refId}
              onChange={e => setRefId(e.target.value)}
            />
          )}
          <span style={{ fontSize: 12, color: 'var(--ink-400)' }}>
            登记只建立引用，不复制任何数据。
          </span>
        </div>
      </Modal>

      <Modal
        title={`生成语义提案（${genAsset?.ref_id ?? ''}）`}
        open={!!genAsset}
        onOk={() => doGenerate()}
        confirmLoading={generating}
        onCancel={() => setGenAsset(null)}
        okText="开始生成"
        okButtonProps={{ disabled: genReadiness ? !genReadiness.ready : false }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {genReadiness && (
            <div className="ecp-card" style={{ padding: 14, marginTop: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                {genReadiness.ready ? '✅ 材料就绪' : '❌ 材料不完整'}
              </div>
              <ReadinessList readiness={genReadiness} />
            </div>
          )}
          <span style={{ fontSize: 13 }}>领域背景（可选，注入提案提示词）：</span>
          <Input.TextArea
            rows={3}
            placeholder="例：零售行业，口径以《财务核算办法》为准"
            value={domainHint}
            onChange={e => setDomainHint(e.target.value)}
          />
          <span style={{ fontSize: 12, color: 'var(--ink-400)' }}>
            提案全部进入「收件箱」，确认前不影响任何查询。
          </span>
        </div>
      </Modal>
    </>
  );
}
