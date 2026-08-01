'use client';

import { apiInterceptors } from '@/client/api';
import {
  addEcpConfirmer,
  getEcpOpLog,
  getEcpWorkspaceConfig,
  listEcpConfirmers,
  removeEcpConfirmer,
  saveEcpWorkspaceConfig,
} from '@/client/api/ecp';
import { getAppList } from '@/client/api/app';
import { getUserId } from '@/utils';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Input, Popconfirm, Select, Spin, Table } from 'antd';
import { useState } from 'react';

import { Dot, EcpEmpty } from './common';

/** Proposal agent: pick a STANDARD agent from the agent store. */
function ProposalAgentCard({ workspaceId }: { workspaceId: string }) {
  const { message } = App.useApp();
  const [agentId, setAgentId] = useState<string>();

  const { loading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getEcpWorkspaceConfig(workspaceId));
      if (!err && res) setAgentId(res.proposal_agent_id ?? undefined);
    },
    { refreshDeps: [workspaceId] },
  );

  const { data: apps } = useRequest(async () => {
    const [err, res] = await apiInterceptors(
      getAppList({ page: 1, page_size: 100 }),
    );
    if (err) return [];
    // AppListResponse field is `app_list` (not `items`)
    return (res as any)?.app_list ?? [];
  });

  const { run: save, loading: saving } = useRequest(
    async () => {
      const [err] = await apiInterceptors(
        saveEcpWorkspaceConfig({
          proposal_agent_id: agentId ?? '',
          workspace_id: workspaceId,
        }),
      );
      if (err) throw err;
      message.success('提案 Agent 已保存');
    },
    { manual: true },
  );

  return (
    <div className="ecp-card" style={{ marginTop: 0 }}>
      <div className="ecp-card__title">提案 Agent</div>
      {loading ? (
        <Spin />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ fontSize: 12, color: 'var(--ink-400)', lineHeight: 1.7 }}>
            从 Agent 空间选择一个标准 Agent 作为提案
            Agent——给它发任务指令（如「为数据源 X 生成语义提案」），它会用 ECP
            工具完成提案，输出结构由 propose_semantic 工具校验，只进收件箱。
            模型、提示词等在 Agent 自身配置里维护，ECP 不重复。
          </div>
          <Select
            allowClear
            showSearch
            style={{ width: '100%' }}
            placeholder="选择 Agent（留空 = 内置批处理提案管线）"
            value={agentId}
            onChange={setAgentId}
            optionFilterProp="label"
            options={(apps ?? []).map((a: any) => ({
              value: a.app_code ?? a.app_id ?? a.id,
              label: a.app_name ?? a.name ?? a.app_code,
            }))}
          />
          <div>
            <Button type="primary" loading={saving} onClick={() => save()}>
              保存
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SettingsTab({ workspaceId }: { workspaceId: string }) {
  const { message } = App.useApp();
  const [newConfirmer, setNewConfirmer] = useState('');

  const { data: confirmers, refresh: refreshConfirmers } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(listEcpConfirmers(workspaceId));
      return err ? [] : res ?? [];
    },
    { refreshDeps: [workspaceId] },
  );

  const { data: opLog, loading: logLoading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getEcpOpLog({ page_size: 100, workspace_id: workspaceId }),
      );
      return err ? [] : res ?? [];
    },
    { refreshDeps: [workspaceId] },
  );

  const { run: add, loading: adding } = useRequest(
    async () => {
      if (!newConfirmer.trim()) return;
      const [err] = await apiInterceptors(
        addEcpConfirmer({ user_id: newConfirmer.trim(), workspace_id: workspaceId }),
      );
      if (err) throw err;
      message.success(`已添加确认人 ${newConfirmer.trim()}`);
      setNewConfirmer('');
      refreshConfirmers();
    },
    { manual: true },
  );

  const { run: remove } = useRequest(
    async (id: number) => {
      const [err] = await apiInterceptors(removeEcpConfirmer(id));
      if (err) throw err;
      message.success('已移除');
      refreshConfirmers();
    },
    { manual: true },
  );

  return (
    <div className="ecp-grid" style={{ gridTemplateColumns: '1fr 1.6fr' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <ProposalAgentCard workspaceId={workspaceId} />
        <div className="ecp-card" style={{ marginTop: 0 }}>
          <div className="ecp-card__title">
            确认人名单
            <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--ink-400)' }}>
              当前用户 {getUserId() ?? 'unknown'}
            </span>
          </div>
        <div style={{ fontSize: 12, color: 'var(--ink-400)', marginBottom: 12, lineHeight: 1.7 }}>
          名单为空时任何人可确认（开放 bootstrap）；非空时仅名单内用户可将提案确认为口径。
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Input
            placeholder="user_id"
            value={newConfirmer}
            onChange={e => setNewConfirmer(e.target.value)}
            onPressEnter={() => add()}
          />
          <Button type="primary" icon={<PlusOutlined />} loading={adding} onClick={() => add()} />
        </div>
        {(confirmers ?? []).length === 0 ? (
          <EcpEmpty title="名单为空" desc="开放 bootstrap：任何人可确认" />
        ) : (
          (confirmers ?? []).map(c => (
            <div
              key={c.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '10px 0',
                borderBottom: '1px solid var(--line-soft)',
              }}
            >
              <Dot kind="ecp-dot--success" />
              <span style={{ flex: 1, fontSize: 13, color: 'var(--ink-700)' }}>{c.user_id}</span>
              <span style={{ fontSize: 12, color: 'var(--ink-400)' }}>{c.scope ?? '全部范围'}</span>
              <Popconfirm title="移除该确认人？" onConfirm={() => remove(c.id)}>
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </div>
          ))
        )}
        </div>
      </div>

      <div className="ecp-card" style={{ marginTop: 0 }}>
        <div className="ecp-card__title">操作日志（append-only）</div>
        {logLoading ? (
          <Spin style={{ display: 'block', margin: '32px auto' }} />
        ) : (opLog ?? []).length === 0 ? (
          <EcpEmpty title="暂无操作记录" />
        ) : (
          <Table
            rowKey="id"
            size="small"
            dataSource={opLog ?? []}
            pagination={{ pageSize: 15 }}
            columns={[
              { title: '时间', dataIndex: 'ts', width: 170 },
              {
                title: '操作',
                dataIndex: 'op',
                width: 130,
                render: (op: string) => (
                  <span className="ecp-type-chip">{op}</span>
                ),
              },
              {
                title: '详情',
                dataIndex: 'detail',
                render: (d: any) => (
                  <code style={{ fontSize: 11, color: 'var(--ink-500)' }}>
                    {d ? JSON.stringify(d) : '-'}
                  </code>
                ),
              },
            ]}
          />
        )}
      </div>
    </div>
  );
}
