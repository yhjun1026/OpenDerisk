'use client';

import { apiInterceptors, listPlaybooks, getWorkspaceInfo, createPlaybook, deletePlaybook, seedBuiltinPlaybooks } from '@/client/api';
import { Button, Card, Empty, Input, Modal, Select, Spin, Table, Tag, Tabs, App } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import VisualEditor from './detail/visual-editor';
import type { PlaybookDeclaration } from './detail/visual-editor/types';

const { TextArea } = Input;

function deepMerge<T extends Record<string, any>>(target: T, source: Partial<T>): T {
  const result: any = { ...target };
  for (const key of Object.keys(source) as Array<keyof T>) {
    const srcVal = source[key];
    const tgtVal = target[key];
    if (
      srcVal !== null &&
      typeof srcVal === 'object' &&
      !Array.isArray(srcVal) &&
      tgtVal !== null &&
      typeof tgtVal === 'object' &&
      !Array.isArray(tgtVal)
    ) {
      result[key] = deepMerge(tgtVal as any, srcVal as any);
    } else if (srcVal !== undefined) {
      result[key] = srcVal;
    }
  }
  return result;
}

const DEFAULT_DSL = JSON.stringify({
  skills: [],
  context: { assets_required: [], resources: [] },
  deliverables: [
    { type: 'report', delivery: [{ category: 'notify', channel: 'in_app', target: 'self' }] },
  ],
  distill: { forced: true, produce: [{ type: 'historical_artifact', from: 'deliverable.0' }] },
}, null, 2);

const SCENARIO_OPTIONS = [
  { value: 'data_ops', label: 'data_ops' },
  { value: 'sre', label: 'sre' },
  { value: 'devops', label: 'devops' },
  { value: 'sec_ops', label: 'sec_ops' },
  { value: 'biz_ops', label: 'biz_ops' },
];

const TASK_TYPE_OPTIONS = [
  { value: 'routine', label: 'routine' },
  { value: 'pipeline', label: 'pipeline' },
  { value: 'incident', label: 'incident' },
  { value: 'adhoc', label: 'adhoc' },
];

export default function PlaybookListPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const router = useRouter();
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [createOpen, setCreateOpen] = useState(false);
  const [dsl, setDsl] = useState(DEFAULT_DSL);
  const [createTab, setCreateTab] = useState('visual');
  const [createName, setCreateName] = useState('New Playbook');
  const [createScenario, setCreateScenario] = useState('data_ops');
  const [createTaskType, setCreateTaskType] = useState('routine');

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: playbooks, loading, refresh } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listPlaybooks({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const parseDeclaration = (): PlaybookDeclaration | null => {
    try {
      return JSON.parse(dsl) as PlaybookDeclaration;
    } catch {
      return null;
    }
  };

  const declaration = parseDeclaration();
  const invalidJson = dsl ? !declaration : false;

  const handleDeclarationChange = (partial: Partial<PlaybookDeclaration>) => {
    try {
      const current = JSON.parse(dsl) as PlaybookDeclaration;
      const updated = deepMerge(current, partial);
      setDsl(JSON.stringify(updated, null, 2));
    } catch {
      // ignore if JSON is invalid
    }
  };

  const handleCreate = async () => {
    try {
      let parsed;
      try {
        parsed = JSON.parse(dsl);
      } catch (e) {
        message.error('DSL must be valid JSON');
        return;
      }
      const [err] = await apiInterceptors(createPlaybook({
        workspace_id: ws?.id,
        name: createName || 'New Playbook',
        scenario_type: createScenario,
        task_type: createTaskType,
        declaration: parsed,
      }));
      if (err) {
        message.error(err.message);
        return;
      }
      message.success('Playbook created');
      setCreateOpen(false);
      refresh();
    } catch (e) {}
  };

  const handleDelete = async (id: number) => {
    Modal.confirm({
      title: 'Delete playbook?',
      onOk: async () => {
        const [err] = await apiInterceptors(deletePlaybook(id));
        if (err) { message.error(err.message); return; }
        message.success('Deleted');
        refresh();
      },
    });
  };

  const handleSeedBuiltin = async () => {
    if (!ws?.id) return;
    const [err, res] = await apiInterceptors(seedBuiltinPlaybooks(ws.id));
    if (err) { message.error(err.message); return; }
    message.success('Built-in playbooks seeded');
    refresh();
  };

  const resetCreateModal = () => {
    setCreateOpen(false);
    setDsl(DEFAULT_DSL);
    setCreateTab('visual');
    setCreateName('New Playbook');
    setCreateScenario('data_ops');
    setCreateTaskType('routine');
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: t('playbooks.name') || 'Name', dataIndex: 'name' },
    { title: t('playbooks.scenario') || 'Scenario', dataIndex: 'scenario_type', width: 120 },
    { title: t('playbooks.task_type') || 'Task Type', dataIndex: 'task_type', width: 110 },
    { title: 'Version', dataIndex: 'current_version', width: 90 },
    {
      title: t('playbooks.active') || 'Active', dataIndex: 'is_active', width: 90,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? 'yes' : 'no'}</Tag>,
    },
    {
      title: '', key: 'actions', width: 180,
      render: (_: any, r: any) => (
        <div className="flex gap-2">
          <Link href={`/workspaces/detail/playbooks/detail?id=${workspaceCode}&playbook_id=${r.id}`}>
            <Button size="small">{t('playbooks.edit') || 'Edit'}</Button>
          </Link>
          <Button size="small" danger onClick={() => handleDelete(r.id)}>{t('delete') || 'Delete'}</Button>
        </div>
      ),
    },
  ];

  return (
    <div className="p-6 h-full overflow-auto">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-xl font-semibold">{t('playbooks.title') || 'Playbooks'}</h1>
        <div className="flex gap-2">
          <Link href={`/workspaces/detail?id=${workspaceCode}`}>
            <Button>{t('back') || 'Back'}</Button>
          </Link>
          <Button onClick={handleSeedBuiltin}>{t('playbooks.seed_builtin') || 'Seed Built-in Examples'}</Button>
          <Button type="primary" onClick={() => setCreateOpen(true)}>{t('playbooks.create') || '+ New Playbook'}</Button>
        </div>
      </div>
      <Card>
        {loading ? <div className="flex justify-center py-12"><Spin /></div> : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={playbooks || []}
            pagination={{ pageSize: 20 }}
            locale={{ emptyText: <Empty description="No playbooks yet" /> }}
          />
        )}
      </Card>

      <Modal
        title={t('playbooks.create_title') || 'Create Playbook'}
        open={createOpen}
        onCancel={resetCreateModal}
        onOk={handleCreate}
        width={900}
        okText={t('create') || 'Create'}
        bodyStyle={{ maxHeight: '70vh', overflow: 'auto' }}
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 border border-gray-100 rounded-xl bg-gray-50/20">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('playbooks.name') || 'Name'}
              </label>
              <Input
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder={t('playbooks.name') || 'Name'}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('playbooks.scenario') || 'Scenario'}
              </label>
              <Select
                value={createScenario}
                options={SCENARIO_OPTIONS}
                onChange={(val) => setCreateScenario(val)}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('playbooks.task_type') || 'Task Type'}
              </label>
              <Select
                value={createTaskType}
                options={TASK_TYPE_OPTIONS}
                onChange={(val) => setCreateTaskType(val)}
                className="w-full"
              />
            </div>
          </div>

          <Tabs
            activeKey={createTab}
            onChange={setCreateTab}
            items={[
              {
                key: 'visual',
                label: t('playbooks.visual_editor') || 'Visual Editor',
                children: (
                  <div>
                    {invalidJson && (
                      <div className="mb-3 text-red-500 text-sm">
                        {t('playbooks.visual_editor.invalid_json_warning') || 'JSON is invalid, cannot render visual editor.'}
                      </div>
                    )}
                    {declaration && (
                      <VisualEditor
                        declaration={declaration}
                        onDeclarationChange={handleDeclarationChange}
                      />
                    )}
                  </div>
                ),
              },
              {
                key: 'editor',
                label: t('playbooks.editor') || 'Declaration DSL (JSON)',
                children: (
                  <TextArea
                    className="font-mono text-xs"
                    value={dsl}
                    onChange={(e) => setDsl(e.target.value)}
                    autoSize={{ minRows: 16, maxRows: 30 }}
                  />
                ),
              },
            ]}
          />
        </div>
      </Modal>
    </div>
  );
}
