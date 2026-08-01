'use client';

import {
  apiInterceptors,
  listResources,
  addResource,
  removeResource,
  updateResource,
  getSkillList,
} from '@/client/api';
import {
  Button, Empty, Input, Modal, Select, Spin, Switch, Tag, message,
} from 'antd';
import {
  ToolOutlined,
  ApiOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useMemo, useState } from 'react';
import dayjs from 'dayjs';
import './assets.css';

const TYPE_META: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  skill: { label: '技能', color: 'geekblue', icon: <ToolOutlined /> },
  mcp: { label: 'MCP', color: 'purple', icon: <ApiOutlined /> },
  llm_model: { label: '模型', color: 'cyan', icon: <CloudServerOutlined /> },
  environment: { label: '环境', color: 'default', icon: <CloudServerOutlined /> },
  app: { label: '智能体', color: 'blue', icon: <AppstoreOutlined /> },
};

/** 排序:启用在前,最近更新在前。 */
function sortCaps(rows: any[]) {
  return [...rows].sort((a, b) => {
    if (!!a.is_active !== !!b.is_active) return a.is_active ? -1 : 1;
    return dayjs(b.gmt_modified || 0).valueOf() - dayjs(a.gmt_modified || 0).valueOf();
  });
}

/** 能力:空间里的 Agent 会"干"什么 —— skill / MCP / 模型 / 智能体。 */
export function CapabilityTab({ workspaceId }: { workspaceId: number }) {
  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [addType, setAddType] = useState<'skill' | 'mcp'>('skill');
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [mcpName, setMcpName] = useState('');
  const [mcpRef, setMcpRef] = useState('');

  const { data: resources, loading, refresh } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listResources({ workspace_id: workspaceId }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: skillData } = useRequest(
    async () => await apiInterceptors(getSkillList({ filter: '' }, { page: 1, page_size: 200 })),
  );
  const allSkills = useMemo(() => {
    const [, res] = skillData || [];
    return res?.items || [];
  }, [skillData]);

  const sections = useMemo(() => {
    const rows = (resources || []).filter((r: any) => TYPE_META[r.type]);
    return [
      { key: 'skill', title: '技能', items: sortCaps(rows.filter((r: any) => r.type === 'skill')) },
      { key: 'mcp', title: 'MCP 服务', items: sortCaps(rows.filter((r: any) => r.type === 'mcp')) },
      {
        key: 'other',
        title: '模型与智能体',
        items: sortCaps(rows.filter((r: any) => ['llm_model', 'app', 'environment'].includes(r.type))),
      },
    ].filter((s) => s.items.length > 0);
  }, [resources]);

  const totalCount = useMemo(() => sections.reduce((n, s) => n + s.items.length, 0), [sections]);

  const boundSkills = useMemo(
    () => new Set(
      (resources || [])
        .filter((r: any) => r.type === 'skill')
        .map((r: any) => String(r.physical_ref || r.name)),
    ),
    [resources],
  );
  const candidateSkills = useMemo(
    () => allSkills.filter((s: any) => !boundSkills.has(String(s.skill_code)) && !boundSkills.has(String(s.name))),
    [allSkills, boundSkills],
  );

  const handleAdd = async () => {
    setSaving(true);
    let err: any = null;
    if (addType === 'skill') {
      const skill = allSkills.find((s: any) => s.skill_code === selectedSkill);
      if (!skill) { setSaving(false); return; }
      [err] = await apiInterceptors(addResource({
        workspace_id: workspaceId,
        type: 'skill',
        name: skill.name,
        physical_ref: skill.skill_code,
        category: 'scenario_bound',
        access_mode: 'read',
        is_active: true,
        config: {},
      }));
    } else {
      if (!mcpName.trim()) { setSaving(false); message.warning('请填写 MCP 名称'); return; }
      [err] = await apiInterceptors(addResource({
        workspace_id: workspaceId,
        type: 'mcp',
        name: mcpName.trim(),
        physical_ref: mcpRef.trim() || undefined,
        category: 'scenario_bound',
        access_mode: 'read',
        is_active: true,
        config: {},
      }));
    }
    setSaving(false);
    if (err) { message.error(err.message); return; }
    message.success('能力已添加');
    setAddOpen(false);
    setSelectedSkill(null);
    setMcpName('');
    setMcpRef('');
    refresh();
  };

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
    Modal.confirm({
      title: `移除能力「${r.name}」?`,
      content: '移除后空间内的 Agent 将无法使用该能力。',
      okText: '移除',
      okButtonProps: { danger: true },
      onOk: async () => {
        const [err] = await apiInterceptors(removeResource({ resource_id: r.id }));
        if (err) { message.error(err.message); return; }
        message.success('已移除');
        refresh();
      },
    });
  };

  const renderCard = (r: any) => {
    const meta = TYPE_META[r.type] || TYPE_META.skill;
    return (
      <div key={r.id} className={`ws-asset-card${r.is_active ? '' : ' ws-asset-card--off'}`}>
        <div className="ws-asset-card__top">
          <span className="ws-asset-card__icon" style={{ color: 'var(--ws-brand, #4f46e5)' }}>{meta.icon}</span>
          <span className="ws-asset-card__name" title={r.name}>{r.name}</span>
          <Switch size="small" checked={!!r.is_active} onChange={(c) => handleToggle(r, c)} />
        </div>
        <div className="ws-asset-card__tags">
          <Tag color={meta.color}>{meta.label}</Tag>
        </div>
        <div className="ws-asset-card__source" title={r.physical_ref || ''}>
          {r.physical_ref || '—'}
        </div>
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
      <div className="flex justify-end mb-4">
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加能力</Button>
      </div>

      {loading ? <div className="flex justify-center py-8"><Spin /></div> : totalCount === 0 ? (
        <Empty description="还没有能力" style={{ padding: '32px 0' }}>
          <Button size="small" onClick={() => setAddOpen(true)}>添加第一个能力</Button>
        </Empty>
      ) : (
        sections.map((s) => (
          <div key={s.key} className="ws-asset-section">
            <div className="ws-asset-section__head">
              <span className="ws-asset-section__icon">
                {s.key === 'skill' ? <ToolOutlined /> : s.key === 'mcp' ? <ApiOutlined /> : <AppstoreOutlined />}
              </span>
              <span className="ws-asset-section__title">{s.title}</span>
              <span className="ws-asset-section__count">{s.items.length}</span>
            </div>
            <div className="ws-asset-grid">
              {s.items.map(renderCard)}
            </div>
          </div>
        ))
      )}

      <Modal
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={handleAdd}
        confirmLoading={saving}
        title="添加能力"
        okText="添加"
      >
        <div className="mb-3">
          <div className="text-sm text-gray-500 mb-2">能力类型</div>
          <Select
            style={{ width: '100%' }}
            value={addType}
            onChange={(v) => setAddType(v)}
            options={[
              { value: 'skill', label: '技能(skill)— 指导 Agent 做事的方法' },
              { value: 'mcp', label: 'MCP — 扩展 Agent 工具能力的服务' },
            ]}
          />
        </div>
        {addType === 'skill' ? (
          <div>
            <div className="text-sm text-gray-500 mb-2">选择技能</div>
            <Select
              style={{ width: '100%' }}
              placeholder="从技能库选择"
              value={selectedSkill}
              onChange={setSelectedSkill}
              showSearch
              optionFilterProp="label"
              options={candidateSkills.map((s: any) => ({
                value: s.skill_code,
                label: `${s.name}${s.description ? ` — ${s.description}` : ''}`,
              }))}
            />
          </div>
        ) : (
          <div>
            <div className="text-sm text-gray-500 mb-2">MCP 名称</div>
            <Input
              className="mb-3"
              placeholder="例如:gitlab-mcp"
              value={mcpName}
              onChange={(e) => setMcpName(e.target.value)}
            />
            <div className="text-sm text-gray-500 mb-2">服务标识(可选)</div>
            <Input
              placeholder="MCP server 编码 / 地址;若它包裹业务数据,注明数据来源"
              value={mcpRef}
              onChange={(e) => setMcpRef(e.target.value)}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
