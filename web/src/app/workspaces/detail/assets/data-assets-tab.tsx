'use client';

import {
  apiInterceptors,
  listResources,
  addResource,
  removeResource,
  updateResource,
  getDbList,
} from '@/client/api';
import { listDatasets, uploadDataset } from '@/client/api/workspace';
import { listEcpAssets } from '@/client/api/ecp';
import {
  listSpaces,
  createSpace,
  getRawTree,
  uploadFile as uploadKnowledgeFile,
} from '@/client/api/knowledge-vault';
import {
  App, Button, Empty, Input, Modal, Select, Spin, Switch, Tag, Upload,
} from 'antd';
import {
  DatabaseOutlined,
  FileExcelOutlined,
  FileTextOutlined,
  CloudUploadOutlined,
  BookOutlined,
  InboxOutlined,
  DeploymentUnitOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useMemo, useState } from 'react';
import dayjs from 'dayjs';
import './assets.css';

const DB_TYPE_COLOR: Record<string, string> = {
  mysql: 'blue',
  postgresql: 'geekblue',
  duckdb: 'cyan',
  sqlite: 'cyan',
  excel: 'green',
  csv: 'green',
  clickhouse: 'purple',
  oracle: 'red',
  mssql: 'volcano',
  mongodb: 'lime',
};

/** 排序:启用在前,最近更新在前 —— 有数据可用的资产浮上来,禁用的沉底置灰。 */
function sortAssets(rows: any[]) {
  return [...rows].sort((a, b) => {
    if (!!a.is_active !== !!b.is_active) return a.is_active ? -1 : 1;
    return dayjs(b.gmt_modified || 0).valueOf() - dayjs(a.gmt_modified || 0).valueOf();
  });
}

function fmtSize(bytes?: number | null): string {
  if (!bytes && bytes !== 0) return '';
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

/** 数据资产:空间里能"碰"的东西 —— 数据库 / 自持数据集 / 知识库。 */
export function DataAssetsTab({
  workspaceId,
  workspaceCode,
}: {
  workspaceId: number;
  workspaceCode?: string;
}) {
  // 静态 Modal/message 在本应用(React 19 静态渲染路径)下会静默失效,必须用 App.useApp() 上下文实例
  const { modal, message } = App.useApp();
  const [connectOpen, setConnectOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedDbId, setSelectedDbId] = useState<string | null>(null);
  const [selectedSpace, setSelectedSpace] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [fileOpen, setFileOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);

  const { data: resources, loading, refresh } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listResources({ workspace_id: workspaceId }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: dbs } = useRequest(async () => {
    // 只列"本空间自持 + 全局"数据源(后端 owner_workspace_id 过滤)
    const [err, res] = await apiInterceptors(
      getDbList({ owner_workspace_id: workspaceId }),
    );
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  // 派生 ECP workspace 已入驻资产(语义层登记的数据源引用)
  const ecpWsId = workspaceCode ? `ecp_${workspaceCode}` : null;
  const { data: ecpAssets } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listEcpAssets({ workspace_id: ecpWsId! }),
      );
      return err ? [] : res ?? [];
    },
    { ready: !!ecpWsId, refreshDeps: [ecpWsId] },
  );

  const { data: spaces, refresh: refreshSpaces } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listSpaces());
    return err ? [] : (res as any) || [];
  });

  const { data: datasets, refresh: refreshDatasets } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listDatasets(workspaceId));
    return err ? [] : (res as any) || [];
  }, { refreshDeps: [workspaceId] });

  const dbById = useMemo(() => {
    const m = new Map<string, any>();
    (dbs || []).forEach((d: any) => m.set(String(d.id), d));
    return m;
  }, [dbs]);

  const datasetIds = useMemo(
    () => new Set((datasets || []).map((d: any) => String(d.datasource_id))),
    [datasets],
  );

  const sections = useMemo(() => {
    const rows = (resources || [])
      .filter((r: any) => r.type === 'data_source' || r.type === 'knowledge_space')
      .map((r: any) => {
        const db = r.type === 'data_source' ? dbById.get(String(r.physical_ref)) : null;
        return {
          ...r,
          db,
          owned: r.type === 'data_source' && datasetIds.has(String(r.physical_ref)),
        };
      });
    return [
      {
        key: 'owned',
        title: '自持数据集',
        icon: <FileExcelOutlined />,
        items: sortAssets(rows.filter((r: any) => r.owned)),
      },
      {
        key: 'db',
        title: '数据库',
        icon: <DatabaseOutlined />,
        items: sortAssets(rows.filter((r: any) => r.type === 'data_source' && !r.owned)),
      },
      {
        key: 'knowledge',
        title: '知识库',
        icon: <BookOutlined />,
        items: sortAssets(rows.filter((r: any) => r.type === 'knowledge_space')),
      },
    ].filter((s) => s.items.length > 0);
  }, [resources, dbById, datasetIds]);

  const totalCount = useMemo(() => sections.reduce((n, s) => n + s.items.length, 0), [sections]);

  const refreshAll = () => { refresh(); refreshDatasets(); };

  // ---------------- 连接数据库(引用全局数据源) ----------------
  const boundDbIds = useMemo(
    () => new Set(
      (resources || [])
        .filter((r: any) => r.type === 'data_source')
        .map((r: any) => String(r.physical_ref)),
    ),
    [resources],
  );
  const candidateDbs = useMemo(
    () => (dbs || []).filter((d: any) => !boundDbIds.has(String(d.id))),
    [dbs, boundDbIds],
  );

  // ECP 已入驻但尚未绑定到本空间的 db 资产:入驻只建 ECP 侧引用,
  // 场景空间资源绑定由空间侧完成(ECP 模块单向依赖,不反向写空间资源)。
  const ecpUnbound = useMemo(
    () => (ecpAssets || []).filter(
      (a: any) => a.kind === 'db' && !boundDbIds.has(String(a.ref_id)),
    ),
    [ecpAssets, boundDbIds],
  );

  const handleBindEcpAsset = async (asset: any) => {
    const db = dbById.get(String(asset.ref_id));
    setSaving(true);
    const [err] = await apiInterceptors(addResource({
      workspace_id: workspaceId,
      type: 'data_source',
      name: db?.db_name || `db_${asset.ref_id}`,
      physical_ref: String(asset.ref_id),
      category: 'scenario_bound',
      access_mode: 'read',
      is_active: true,
      config: {},
    }));
    setSaving(false);
    if (err) { message.error(err.message); return; }
    message.success('已接入空间');
    refreshAll();
  };

  const handleConnectDb = async () => {
    if (!selectedDbId) return;
    const db = dbById.get(selectedDbId);
    if (!db) return;
    setSaving(true);
    const [err] = await apiInterceptors(addResource({
      workspace_id: workspaceId,
      type: 'data_source',
      name: db.db_name,
      physical_ref: String(db.id),
      category: 'scenario_bound',
      access_mode: 'read',
      is_active: true,
      config: {},
    }));
    setSaving(false);
    if (err) { message.error(err.message); return; }
    message.success('数据库已接入空间');
    setConnectOpen(false);
    setSelectedDbId(null);
    refreshAll();
  };

  // ---------------- 上传数据集(空间自持) ----------------
  const handleUpload = async () => {
    if (!uploadFile) { message.warning('请选择 Excel / CSV 文件'); return; }
    setSaving(true);
    const [err] = await apiInterceptors(uploadDataset(workspaceId, uploadFile, uploadName || undefined));
    setSaving(false);
    if (err) { message.error(err.message); return; }
    message.success('数据集已上传,正在学习表结构');
    setUploadOpen(false);
    setUploadFile(null);
    setUploadName('');
    refreshAll();
  };

  // ---------------- 挂载知识库 ----------------
  const boundSpaces = useMemo(
    () => new Set(
      (resources || [])
        .filter((r: any) => r.type === 'knowledge_space')
        .map((r: any) => String(r.physical_ref)),
    ),
    [resources],
  );
  const candidateSpaces = useMemo(
    () => (spaces || []).filter((s: any) => !boundSpaces.has(String(s.slug))),
    [spaces, boundSpaces],
  );

  // ---------------- 上传文件(文档/图片/音频 → 空间自持知识空间) ----------------
  // 与 ECP 软空间 slug 约定(ecp-<ws>)同族:docs-<workspace_code>。
  // 视频暂不支持:extractor registry 只有 text/pdf/docx/pptx/image/audio,无 video。
  const docSpaceSlug = workspaceCode ? `docs-${workspaceCode}` : null;
  const docSpaceBound = !!docSpaceSlug && boundSpaces.has(docSpaceSlug);

  // 已上传文件(raw 目录,上传即可见,不等异步抽取完成)
  const { data: docFiles, refresh: refreshDocFiles } = useRequest(
    async () => {
      if (!docSpaceSlug || !docSpaceBound) return [];
      const [err, res] = await apiInterceptors(getRawTree(docSpaceSlug));
      if (err) return [];
      const files: { path: string; name: string; size?: number | null }[] = [];
      const walk = (nodes: any[]) => {
        (nodes || []).forEach((n: any) => {
          if (n.is_dir) walk(n.children || []);
          else files.push({ path: n.path, name: n.name, size: n.size });
        });
      };
      walk((res as any) || []);
      return files;
    },
    { refreshDeps: [docSpaceSlug, docSpaceBound] },
  );

  const handleUploadFiles = async () => {
    if (!uploadFiles.length || !docSpaceSlug) return;
    setSaving(true);
    // 1. 确保空间自持知识空间存在(首次上传惰性创建)
    if (!(spaces || []).some((s: any) => s.slug === docSpaceSlug)) {
      const [err] = await apiInterceptors(createSpace({ slug: docSpaceSlug }));
      if (err) {
        setSaving(false);
        message.error(`创建知识空间失败:${err.message}`);
        return;
      }
    }
    // 2. 确保绑定为空间资源(绑定后 Agent 才能检索)
    if (!boundSpaces.has(docSpaceSlug)) {
      const [err] = await apiInterceptors(addResource({
        workspace_id: workspaceId,
        type: 'knowledge_space',
        name: docSpaceSlug,
        physical_ref: docSpaceSlug,
        category: 'scenario_bound',
        access_mode: 'read',
        is_active: true,
        config: {},
      }));
      if (err) {
        setSaving(false);
        message.error(err.message);
        return;
      }
    }
    // 3. 逐个上传(后端单文件接口),异步抽取 verbats + 生成 wiki
    let failed = 0;
    for (const f of uploadFiles) {
      const [err] = await apiInterceptors(uploadKnowledgeFile({ slug: docSpaceSlug, file: f }));
      if (err) failed++;
    }
    setSaving(false);
    if (failed) {
      message.warning(`${uploadFiles.length - failed} 个上传成功,${failed} 个失败`);
    } else {
      message.success('已上传,正在抽取内容(稍后即可被 Agent 检索)');
    }
    setFileOpen(false);
    setUploadFiles([]);
    refreshAll();
    refreshSpaces();
    refreshDocFiles();
  };

  const handleMountKnowledge = async () => {
    if (!selectedSpace) return;
    setSaving(true);
    const [err] = await apiInterceptors(addResource({
      workspace_id: workspaceId,
      type: 'knowledge_space',
      name: selectedSpace,
      physical_ref: selectedSpace,
      category: 'scenario_bound',
      access_mode: 'read',
      is_active: true,
      config: {},
    }));
    setSaving(false);
    if (err) { message.error(err.message); return; }
    message.success('知识库已挂载');
    setKnowledgeOpen(false);
    setSelectedSpace(null);
    refreshAll();
  };

  // ---------------- 启停 / 移除 ----------------
  const handleToggle = async (r: any, checked: boolean) => {
    const [err] = await apiInterceptors(updateResource({
      resource_id: r.id,
      resource: {
        workspace_id: workspaceId,
        type: r.type,
        name: r.name,
        category: r.category,
        physical_ref: r.physical_ref,
        config: r.config || {},
        access_mode: r.access_mode,
        is_active: checked,
      },
    }));
    if (err) { message.error(err.message); return; }
    refresh();
  };

  const handleRemove = (r: any) => {
    modal.confirm({
      title: `移除「${r.name}」?`,
      content: '只会解除与空间的绑定,不会删除数据本身。',
      okText: '移除',
      okButtonProps: { danger: true },
      onOk: async () => {
        const [err] = await apiInterceptors(removeResource({ resource_id: r.id }));
        if (err) { message.error(err.message); return; }
        message.success('已移除');
        refreshAll();
      },
    });
  };

  const renderCard = (r: any) => {
    const isKnowledge = r.type === 'knowledge_space';
    const icon = isKnowledge
      ? <BookOutlined className="ws-asset-card__icon" style={{ color: '#9333ea' }} />
      : r.owned
        ? <FileExcelOutlined className="ws-asset-card__icon" style={{ color: '#16a34a' }} />
        : <DatabaseOutlined className="ws-asset-card__icon" style={{ color: 'var(--ws-brand, #4f46e5)' }} />;
    const source = isKnowledge
      ? r.physical_ref
      : r.db
        ? `${r.db.db_name}${r.db.db_host ? ` · ${r.db.db_host}` : ''}`
        : `#${r.physical_ref}`;
    return (
      <div key={r.id} className={`ws-asset-card${r.is_active ? '' : ' ws-asset-card--off'}`}>
        <div className="ws-asset-card__top">
          {icon}
          <span className="ws-asset-card__name" title={r.name}>{r.name}</span>
          <Switch size="small" checked={!!r.is_active} onChange={(c) => handleToggle(r, c)} />
        </div>
        <div className="ws-asset-card__tags">
          {isKnowledge
            ? <Tag color="purple">知识库</Tag>
            : <Tag color={DB_TYPE_COLOR[r.db?.db_type] || 'blue'}>{r.db?.db_type || '数据库'}</Tag>}
          {r.owned ? <Tag color="gold">自持</Tag> : <Tag>引用</Tag>}
        </div>
        <div className="ws-asset-card__source" title={source}>{source}</div>
        <div className="ws-asset-card__foot">
          <span className="ws-asset-card__time">
            {r.gmt_modified ? dayjs(r.gmt_modified).format('MM-DD HH:mm') : ''}
          </span>
          <span className="ws-asset-card__ops">
            <Button size="small" type="text" danger onClick={() => handleRemove(r)}>移除</Button>
          </span>
        </div>
      </div>
    );
  };

  return (
    <div>
      <div className="flex justify-end gap-2 mb-4">
        <Button icon={<DatabaseOutlined />} onClick={() => setConnectOpen(true)}>连接数据库</Button>
        <Button icon={<CloudUploadOutlined />} onClick={() => setUploadOpen(true)}>上传数据集</Button>
        <Button icon={<FileTextOutlined />} onClick={() => setFileOpen(true)}>上传文件</Button>
        <Button icon={<BookOutlined />} onClick={() => setKnowledgeOpen(true)}>挂载知识库</Button>
      </div>

      {loading ? <div className="flex justify-center py-8"><Spin /></div> : totalCount === 0 ? (
        <Empty description="还没有数据资产" style={{ padding: '32px 0' }}>
          <div className="flex gap-2 justify-center">
            <Button size="small" onClick={() => setConnectOpen(true)}>连接数据库</Button>
            <Button size="small" onClick={() => setUploadOpen(true)}>上传 Excel / CSV</Button>
          </div>
        </Empty>
      ) : (
        sections.map((s) => (
          <div key={s.key} className="ws-asset-section">
            <div className="ws-asset-section__head">
              <span className="ws-asset-section__icon">{s.icon}</span>
              <span className="ws-asset-section__title">{s.title}</span>
              <span className="ws-asset-section__count">{s.items.length}</span>
            </div>
            <div className="ws-asset-grid">
              {s.items.map(renderCard)}
            </div>
          </div>
        ))
      )}

      {docFiles && docFiles.length > 0 && (
        <div className="ws-asset-section">
          <div className="ws-asset-section__head">
            <span className="ws-asset-section__icon"><FileTextOutlined /></span>
            <span className="ws-asset-section__title">文档</span>
            <span className="ws-asset-section__count">{docFiles.length}</span>
          </div>
          <div className="ws-asset-grid">
            {docFiles.map((f) => (
              <div key={f.path} className="ws-asset-card">
                <div className="ws-asset-card__top">
                  <FileTextOutlined className="ws-asset-card__icon" style={{ color: '#9333ea' }} />
                  <span className="ws-asset-card__name" title={f.path}>{f.name}</span>
                </div>
                <div className="ws-asset-card__tags">
                  <Tag color="purple">文档</Tag>
                  <Tag>{docSpaceSlug}</Tag>
                </div>
                <div className="ws-asset-card__source" title={f.path}>{f.path}</div>
                <div className="ws-asset-card__foot">
                  <span className="ws-asset-card__time">{fmtSize(f.size)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {ecpUnbound.length > 0 && (
        <div className="ws-asset-section">
          <div className="ws-asset-section__head">
            <span className="ws-asset-section__icon"><DeploymentUnitOutlined /></span>
            <span className="ws-asset-section__title">ECP 已入驻(待接入)</span>
            <span className="ws-asset-section__count">{ecpUnbound.length}</span>
          </div>
          <div className="ws-asset-grid">
            {ecpUnbound.map((a: any) => {
              const db = dbById.get(String(a.ref_id));
              const name = db?.db_name || `db_${a.ref_id}`;
              const source = db ? `${db.db_name}${db.db_host ? ` · ${db.db_host}` : ''}` : `#${a.ref_id}`;
              return (
                <div key={a.ref_id} className="ws-asset-card">
                  <div className="ws-asset-card__top">
                    <DatabaseOutlined className="ws-asset-card__icon" style={{ color: 'var(--ws-brand, #4f46e5)' }} />
                    <span className="ws-asset-card__name" title={name}>{name}</span>
                  </div>
                  <div className="ws-asset-card__tags">
                    <Tag color={DB_TYPE_COLOR[db?.db_type] || 'blue'}>{db?.db_type || '数据库'}</Tag>
                    <Tag color="purple">ECP 入驻</Tag>
                  </div>
                  <div className="ws-asset-card__source" title={source}>{source}</div>
                  <div className="ws-asset-card__foot">
                    <span className="ws-asset-card__time" />
                    <span className="ws-asset-card__ops">
                      <Button size="small" type="link" loading={saving} onClick={() => handleBindEcpAsset(a)}>接入空间</Button>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <Modal
        open={connectOpen}
        onCancel={() => setConnectOpen(false)}
        onOk={handleConnectDb}
        confirmLoading={saving}
        okButtonProps={{ disabled: !selectedDbId }}
        title="连接数据库"
        okText="接入空间"
      >
        <p className="text-sm text-gray-500 mb-3">
          从全局数据源中选择一个接入本空间(引用,不复制数据)。新数据库请先在「数据库」模块创建。
        </p>
        <Select
          style={{ width: '100%' }}
          placeholder="选择数据源"
          value={selectedDbId}
          onChange={setSelectedDbId}
          showSearch
          optionFilterProp="label"
          options={candidateDbs.map((d: any) => ({
            value: String(d.id),
            label: `${d.db_name} (${d.db_type}${d.db_host ? ` · ${d.db_host}` : ''})`,
          }))}
        />
      </Modal>

      <Modal
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={handleUpload}
        confirmLoading={saving}
        title="上传数据集"
        okText="上传"
      >
        <p className="text-sm text-gray-500 mb-3">
          Excel / CSV 会成为空间自持数据资产:自动物化为可查询的数据集,并学习表结构供 Agent 使用。
        </p>
        <Input
          className="mb-3"
          placeholder="数据集名称(可选,默认取文件名)"
          value={uploadName}
          onChange={(e) => setUploadName(e.target.value)}
        />
        <Upload.Dragger
          accept=".xlsx,.xls,.csv"
          maxCount={1}
          beforeUpload={(file) => { setUploadFile(file); return false; }}
          onRemove={() => setUploadFile(null)}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽文件到此上传</p>
          <p className="ant-upload-hint">支持 .xlsx / .xls / .csv</p>
        </Upload.Dragger>
      </Modal>

      <Modal
        open={fileOpen}
        onCancel={() => setFileOpen(false)}
        onOk={handleUploadFiles}
        confirmLoading={saving}
        okButtonProps={{ disabled: uploadFiles.length === 0 }}
        title="上传文件"
        okText="上传"
      >
        <p className="text-sm text-gray-500 mb-3">
          文档 / 图片 / 音频 / 视频会进入空间专属知识库({docSpaceSlug || 'docs-<workspace_code>'}),
          自动抽取内容后 Agent 可检索引用(视频走抽帧+音轨理解,原生视频模型自动直连)。
          Excel / CSV 请用「上传数据集」。
        </p>
        <Upload.Dragger
          accept=".pdf,.doc,.docx,.ppt,.pptx,.md,.markdown,.txt,.png,.jpg,.jpeg,.gif,.webp,.mp3,.wav,.ogg,.flac,.mp4,.mov,.webm,.mkv,.avi"
          multiple
          fileList={uploadFiles.map((f, i) => ({ uid: String(i), name: f.name, size: f.size })) as any}
          beforeUpload={(file, fileList) => { setUploadFiles(fileList); return false; }}
          onRemove={(file) => { setUploadFiles((prev) => prev.filter((f) => f.name !== file.name)); }}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽文件到此上传,可多选</p>
          <p className="ant-upload-hint">支持 PDF / Word / PPT / Markdown / TXT / 图片 / 音频 / 视频</p>
        </Upload.Dragger>
      </Modal>

      <Modal
        open={knowledgeOpen}
        onCancel={() => setKnowledgeOpen(false)}
        onOk={handleMountKnowledge}
        confirmLoading={saving}
        okButtonProps={{ disabled: !selectedSpace }}
        title="挂载知识库"
        okText="挂载"
      >
        <p className="text-sm text-gray-500 mb-3">
          把知识空间挂载进来,Agent 即可检索其中的文档与经验。
        </p>
        <Select
          style={{ width: '100%' }}
          placeholder="选择知识空间"
          value={selectedSpace}
          onChange={setSelectedSpace}
          showSearch
          optionFilterProp="label"
          options={candidateSpaces.map((s: any) => ({ value: s.slug, label: s.slug }))}
        />
      </Modal>
    </div>
  );
}
