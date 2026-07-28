'use client';

import {
  apiInterceptors, createTask, getWorkspaceInfo, listPlaybooks,
  getTriggerInfo, createTrigger, updateTrigger, startTask,
} from '@/client/api';
import {
  Button, Card, Form, Input, Select, Spin, Switch, Typography, Tag, message,
} from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useState, useMemo, useEffect } from 'react';
import { getUserId } from '@/utils/storage';
import {
  ArrowLeftOutlined, ThunderboltOutlined, FileTextOutlined,
  ClockCircleOutlined, GlobalOutlined, AlertOutlined, CheckOutlined,
} from '@ant-design/icons';
import Link from 'next/link';
import CronEditor from './cron-editor';
import '../../../workspaces.css';

const { TextArea } = Input;
const { Text } = Typography;

type TriggerType = 'adhoc' | 'timer' | 'webhook' | 'alert';

interface PlaybookOption {
  id: number;
  name: string;
  scenario_type?: string;
  task_type?: string;
  declaration?: { skills?: string[] };
}

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const TYPE_CONFIG: Record<TriggerType, {
  label: string;
  desc: string;
  detail: string;
  icon: React.ReactNode;
  iconBg: string;
  iconText: string;
  cardBg: string;
  cardBorder: string;
  ring: string;
  accentBar: string;
}> = {
  adhoc: {
    label: '手动执行',
    desc: '一次性临时任务',
    detail: '立即创建并执行一次任务，在任务详情查看对话、产出和交付。',
    icon: <ThunderboltOutlined />,
    iconBg: 'bg-blue-100',
    iconText: 'text-blue-600',
    cardBg: 'bg-blue-50/40',
    cardBorder: 'border-blue-500',
    ring: 'ring-blue-200',
    accentBar: 'bg-blue-500',
  },
  timer: {
    label: '定时触发',
    desc: '按 Cron 周期执行',
    detail: '创建定时触发规则：到点自动按剧本创建任务，每次执行你设定的指令。',
    icon: <ClockCircleOutlined />,
    iconBg: 'bg-emerald-100',
    iconText: 'text-emerald-600',
    cardBg: 'bg-emerald-50/40',
    cardBorder: 'border-emerald-500',
    ring: 'ring-emerald-200',
    accentBar: 'bg-emerald-500',
  },
  webhook: {
    label: 'Webhook',
    desc: '外部请求触发',
    detail: '创建 Webhook 触发规则：外部系统向 Webhook URL 发 POST 即自动按剧本创建任务。',
    icon: <GlobalOutlined />,
    iconBg: 'bg-violet-100',
    iconText: 'text-violet-600',
    cardBg: 'bg-violet-50/40',
    cardBorder: 'border-violet-500',
    ring: 'ring-violet-200',
    accentBar: 'bg-violet-500',
  },
  alert: {
    label: '告警触发',
    desc: '告警事件触发',
    detail: '创建告警触发规则：监控系统向告警 URL 推送事件即自动按剧本创建任务。',
    icon: <AlertOutlined />,
    iconBg: 'bg-amber-100',
    iconText: 'text-amber-600',
    cardBg: 'bg-amber-50/40',
    cardBorder: 'border-amber-500',
    ring: 'ring-amber-200',
    accentBar: 'bg-amber-500',
  },
};

export default function TaskCreatePage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const router = useRouter();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [selectedPlaybookId, setSelectedPlaybookId] = useState<number | null>(null);

  const rawType = searchParams?.get('type') as TriggerType | null;
  const initialType: TriggerType = rawType && TYPE_CONFIG[rawType] ? rawType : 'adhoc';
  const [selectedType, setSelectedType] = useState<TriggerType>(initialType);
  const [cronExpr, setCronExpr] = useState('0 9 * * *');
  const editTriggerId = searchParams?.get('trigger_id')
    ? Number(searchParams.get('trigger_id'))
    : null;

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: playbooks, loading: pbLoading } = useRequest(async () => {
    if (!ws?.id) return [];
    const [err, res] = await apiInterceptors(listPlaybooks({ workspace_id: ws.id, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [ws?.id] });

  const selectedPlaybook = useMemo(() => {
    return (playbooks || []).find((p: PlaybookOption) => p.id === selectedPlaybookId);
  }, [playbooks, selectedPlaybookId]);

  const { data: existingTrigger, loading: editLoading } = useRequest(async () => {
    if (!editTriggerId) return null;
    const [err, res] = await apiInterceptors(getTriggerInfo(editTriggerId));
    return err ? null : res;
  }, { refreshDeps: [editTriggerId] });

  useEffect(() => {
    if (!existingTrigger) return;
    const type = (existingTrigger.type as TriggerType) || 'timer';
    setSelectedType(TYPE_CONFIG[type] ? type : 'timer');
    setSelectedPlaybookId(existingTrigger.target_playbook_id);
    setCronExpr(existingTrigger.config?.cron || '0 9 * * *');
    form.setFieldsValue({
      name: existingTrigger.name,
      instruction: existingTrigger.instruction || '',
      target_playbook_id: existingTrigger.target_playbook_id,
      priority: 'medium',
      secret: existingTrigger.config?.secret || '',
      alert_name: existingTrigger.config?.alert_name || '',
      is_active: existingTrigger.is_active ?? true,
    });
  }, [existingTrigger, form]);

  useEffect(() => {
    form.setFieldValue('cron', cronExpr);
  }, [cronExpr, form]);

  const publicWebhookUrl = useMemo(() => {
    if (!ws?.id || selectedType !== 'webhook') return '';
    const base = typeof window !== 'undefined' ? window.location.origin : '';
    const tid = editTriggerId || '{trigger_id}';
    return `${base}/api/v1/serve_trigger_service/triggers/${tid}/webhook`;
  }, [ws?.id, selectedType, editTriggerId]);

  const publicAlertUrl = useMemo(() => {
    if (!ws?.id || selectedType !== 'alert') return '';
    const base = typeof window !== 'undefined' ? window.location.origin : '';
    const tid = editTriggerId || '{trigger_id}';
    return `${base}/api/v1/serve_trigger_service/triggers/${tid}/alert`;
  }, [ws?.id, selectedType, editTriggerId]);

  const isEditing = !!editTriggerId;

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (!ws?.id) return;
      setSubmitting(true);

      if (selectedType === 'adhoc') {
        const [cerr, res] = await apiInterceptors(createTask({
          workspace_id: ws.id,
          title: values.instruction,
          description: '',
          type: 'adhoc',
          triggered_by: 'manual',
          playbook_id: values.target_playbook_id || null,
          priority: values.priority || 'medium',
          created_by_user_id: Number(getUserId()) || 0,
          status: 'pending_trigger',
        }));
        if (cerr) { setSubmitting(false); message.error(cerr.message); return; }
        await apiInterceptors(startTask(res?.id));
        setSubmitting(false);
        message.success(t('tasks.create_success') || '任务已创建并开始执行');
        router.push(`/workspaces/detail/tasks/detail?id=${workspaceCode}&task_id=${res?.id}`);
        return;
      }

      const config: Record<string, string> = {};
      if (selectedType === 'timer') {
        config.cron = cronExpr;
      } else if (selectedType === 'webhook') {
        config.secret = values.secret || '';
      } else if (selectedType === 'alert') {
        config.alert_name = values.alert_name || '';
      }

      const payload = {
        workspace_id: ws.id,
        type: selectedType,
        name: values.name || values.instruction?.slice(0, 30) || '未命名触发器',
        target_playbook_id: values.target_playbook_id,
        instruction: values.instruction,
        is_active: values.is_active ?? true,
        config,
      };

      const [err] = await apiInterceptors(
        editTriggerId
          ? updateTrigger({ id: editTriggerId, ...payload })
          : createTrigger(payload)
      );
      setSubmitting(false);
      if (err) { message.error(err.message); return; }
      message.success(editTriggerId ? '触发规则已更新' : '触发规则已创建，到点/事件发生时将自动按剧本创建任务');
      router.push(`/workspaces/detail/tasks?id=${workspaceCode}&tab=triggers`);
    } catch {
      setSubmitting(false);
    }
  };

  if (wsLoading || editLoading) {
    return (
      <div className="ws-page scrollbar-default flex justify-center items-center">
        <div className="ws-page-bg" />
        <Spin size="large" />
      </div>
    );
  }

  if (!ws) {
    return (
      <div className="ws-page scrollbar-default flex justify-center items-center">
        <div className="ws-page-bg" />
        <Card>Workspace not found</Card>
      </div>
    );
  }

  return (
    <div className="ws-page scrollbar-default">
      <div className="ws-page-bg" />

      {/* Sticky header */}
      <div
        className="sticky top-0 z-30 backdrop-blur border-b border-[var(--ws-border)]"
        style={{ backgroundColor: 'color-mix(in srgb, var(--ws-surface) 88%, transparent)' }}
      >
        <div className="ws-page-content">
          <header className="ws-page-header !mb-0 py-3">
            <div className="ws-page-header-left">
              <div className="ws-page-icon"><ThunderboltOutlined /></div>
              <div>
                <div className="ws-page-eyebrow">
                  {isEditing ? '触发器' : (t('workspaces.tasks') || '任务')}
                  <span className="ws-page-eyebrow-code">{ws.workspace_code}</span>
                </div>
                <h1 className="ws-page-title">{isEditing ? '编辑任务触发' : '新建任务'}</h1>
                <p className="ws-page-subtitle">
                  选一个剧本（怎么做）+ 写一条指令（做什么）+ 设定触发方式（何时做）
                </p>
              </div>
            </div>
            <div className="ws-page-actions">
              <Link href={isEditing ? `/workspaces/detail/tasks?id=${workspaceCode}&tab=triggers` : `/workspaces/detail/tasks?id=${workspaceCode}`}>
                <Button icon={<ArrowLeftOutlined />} size="large">
                  {t('back') || '返回'}
                </Button>
              </Link>
            </div>
          </header>
        </div>
      </div>

      <div className="ws-page-content">
        <main className="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-6 pb-24">
          {/* Left column */}
          <div className="lg:col-span-8 space-y-6">
            {/* Trigger type selector */}
            <section className="bg-[var(--ws-surface)] rounded-xl border border-[var(--ws-border)] shadow-sm p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-1 h-5 bg-[var(--ws-accent)] rounded-full" />
                <h3 className="text-sm font-semibold text-[var(--ws-ink)]">触发方式</h3>
                <span className="text-xs text-[var(--ws-ink-3)]">选择任务如何被启动</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {(Object.keys(TYPE_CONFIG) as TriggerType[]).map(type => {
                  const cfg = TYPE_CONFIG[type];
                  const active = selectedType === type;
                  return (
                    <button
                      type="button"
                      key={type}
                      disabled={isEditing}
                      onClick={() => setSelectedType(type)}
                      className={`group relative flex flex-col gap-3 rounded-xl border p-4 text-left transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed ${active ? `${cfg.cardBg} ${cfg.cardBorder} border-2 shadow-sm ring-2 ${cfg.ring}` : 'bg-[var(--ws-surface)] border-[var(--ws-border)] hover:border-[var(--ws-accent)]/30 hover:shadow-md hover:-translate-y-0.5'}`}
                    >
                      {active && (
                        <div className={`absolute top-2 right-2 w-5 h-5 rounded-full ${cfg.iconBg} ${cfg.iconText} flex items-center justify-center text-xs shadow-sm`}>
                          <CheckOutlined />
                        </div>
                      )}
                      <div className={`w-10 h-10 rounded-lg ${cfg.iconBg} ${cfg.iconText} flex items-center justify-center text-lg transition-transform duration-200 group-hover:scale-105`}>
                        {cfg.icon}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-[var(--ws-ink)]">{cfg.label}</div>
                        <div className="text-xs text-[var(--ws-ink-2)] mt-0.5 leading-relaxed">{cfg.desc}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>

            {/* Core config form */}
            <section className="bg-[var(--ws-surface)] rounded-xl border border-[var(--ws-border)] shadow-sm p-5">
              <div className="flex items-center gap-2 mb-5">
                <div className="w-1 h-5 bg-[var(--ws-accent)] rounded-full" />
                <h3 className="text-sm font-semibold text-[var(--ws-ink)]">核心配置</h3>
                <span className="text-xs text-[var(--ws-ink-3)]">剧本 + 指令</span>
              </div>
              <Form
                form={form}
                layout="vertical"
                initialValues={{ priority: 'medium', is_active: true }}
                onValuesChange={(_, all) => setSelectedPlaybookId(all.target_playbook_id || null)}
              >
                <Form.Item
                  name="target_playbook_id"
                  label={<span className="font-medium text-[var(--ws-ink)]">使用剧本 <span className="text-[var(--ws-ink-3)] text-xs font-normal">任务模板</span></span>}
                  rules={[{ required: true, message: '请选择一个剧本' }]}
                >
                  <Select
                    size="large"
                    loading={pbLoading}
                    placeholder="选择要使用的剧本"
                    showSearch
                    optionFilterProp="children"
                  >
                    {(playbooks || []).map((p: PlaybookOption) => (
                      <Select.Option key={p.id} value={p.id}>
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-[var(--ws-ink)]">{p.name}</span>
                          <Tag color="blue">{p.scenario_type || p.task_type}</Tag>
                        </div>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>

                <Form.Item
                  name="instruction"
                  label={<span className="font-medium text-[var(--ws-ink)]">任务指令 <span className="text-[var(--ws-ink-3)] text-xs font-normal">本次要完成的目标</span></span>}
                  rules={[{ required: true, message: '请输入任务指令' }]}
                >
                  <TextArea
                    rows={3}
                    placeholder="例如：排查 prod-db-01 的 CPU 飙高并产出根因报告"
                    className="!rounded-lg"
                  />
                </Form.Item>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Form.Item
                    name="name"
                    label={<span className="font-medium text-[var(--ws-ink)]">任务名称 <span className="text-[var(--ws-ink-3)] text-xs font-normal">可选</span></span>}
                  >
                    <Input size="large" placeholder="如：每周数据库巡检报告" className="!rounded-lg" />
                  </Form.Item>
                  {selectedType === 'adhoc' && (
                    <Form.Item name="priority" label={<span className="font-medium text-[var(--ws-ink)]">优先级</span>}>
                      <Select size="large">
                        {PRIORITY_OPTIONS.map(opt => (
                          <Select.Option key={opt.value} value={opt.value}>{opt.label}</Select.Option>
                        ))}
                      </Select>
                    </Form.Item>
                  )}
                  {selectedType !== 'adhoc' && (
                    <Form.Item name="is_active" label={<span className="font-medium text-[var(--ws-ink)]">启用</span>} valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  )}
                </div>

                {selectedType === 'timer' && (
                  <>
                    <div className="flex items-center gap-2 mb-4 mt-2">
                      <div className={`w-1 h-5 rounded-full ${TYPE_CONFIG.timer.accentBar}`} />
                      <h3 className="text-sm font-semibold text-[var(--ws-ink)]">定时配置</h3>
                    </div>
                    <Form.Item name="cron" rules={[{ required: true, message: '请配置 Cron 表达式' }]}>
                      <Input type="hidden" />
                    </Form.Item>
                    <CronEditor value={cronExpr} onChange={setCronExpr} />
                  </>
                )}

                {selectedType === 'webhook' && (
                  <>
                    <div className="flex items-center gap-2 mb-4 mt-2">
                      <div className={`w-1 h-5 rounded-full ${TYPE_CONFIG.webhook.accentBar}`} />
                      <h3 className="text-sm font-semibold text-[var(--ws-ink)]">Webhook 配置</h3>
                    </div>
                    <Form.Item
                      name="secret"
                      label={<span className="font-medium text-[var(--ws-ink)]">密钥 <span className="text-[var(--ws-ink-3)] text-xs font-normal">可选，用于校验请求</span></span>}
                    >
                      <Input size="large" placeholder="Bearer token 或签名密钥" className="!rounded-lg" />
                    </Form.Item>
                    {publicWebhookUrl && (
                      <Form.Item label={<span className="font-medium text-[var(--ws-ink)]">Webhook URL</span>}>
                        <div className="bg-[var(--ws-border-subtle)] border border-[var(--ws-border)] rounded-lg p-3">
                          <code className="block text-xs text-[var(--ws-ink)] break-all font-mono">{publicWebhookUrl}</code>
                        </div>
                        {!isEditing && <Text type="secondary" className="text-xs block mt-1">创建后将替换为实际触发器 ID</Text>}
                      </Form.Item>
                    )}
                  </>
                )}

                {selectedType === 'alert' && (
                  <>
                    <div className="flex items-center gap-2 mb-4 mt-2">
                      <div className={`w-1 h-5 rounded-full ${TYPE_CONFIG.alert.accentBar}`} />
                      <h3 className="text-sm font-semibold text-[var(--ws-ink)]">告警配置</h3>
                    </div>
                    <Form.Item
                      name="alert_name"
                      label={<span className="font-medium text-[var(--ws-ink)]">告警名称过滤 <span className="text-[var(--ws-ink-3)] text-xs font-normal">可选</span></span>}
                    >
                      <Input size="large" placeholder="如：cpu_usage_high" className="!rounded-lg" />
                    </Form.Item>
                    {publicAlertUrl && (
                      <Form.Item label={<span className="font-medium text-[var(--ws-ink)]">告警接收 URL</span>}>
                        <div className="bg-[var(--ws-border-subtle)] border border-[var(--ws-border)] rounded-lg p-3">
                          <code className="block text-xs text-[var(--ws-ink)] break-all font-mono">{publicAlertUrl}</code>
                        </div>
                        {!isEditing && <Text type="secondary" className="text-xs block mt-1">创建后将替换为实际触发器 ID</Text>}
                      </Form.Item>
                    )}
                  </>
                )}

                <div className="flex justify-end gap-3 mt-8 pt-4 border-t border-[var(--ws-border-subtle)]">
                  <Link href={isEditing ? `/workspaces/detail/tasks?id=${workspaceCode}&tab=triggers` : `/workspaces/detail/tasks?id=${workspaceCode}`}>
                    <Button size="large">{t('tasks.cancel') || '取消'}</Button>
                  </Link>
                  <Button type="primary" size="large" loading={submitting} onClick={handleSubmit} className="!rounded-lg">
                    {selectedType === 'adhoc' ? '创建并执行' : (isEditing ? '保存' : '创建触发器')}
                  </Button>
                </div>
              </Form>
            </section>
          </div>

          {/* Sidebar */}
          <aside className="lg:col-span-4">
            <div className="lg:sticky lg:top-24 space-y-5">
              <Card
                className="shadow-sm border-[var(--ws-border)] rounded-xl"
                bodyStyle={{ padding: 20, background: 'var(--ws-surface)' }}
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className={`w-10 h-10 rounded-lg ${TYPE_CONFIG[selectedType].iconBg} ${TYPE_CONFIG[selectedType].iconText} flex items-center justify-center text-lg`}>
                    {TYPE_CONFIG[selectedType].icon}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-[var(--ws-ink)]">{TYPE_CONFIG[selectedType].label}</div>
                    <div className="text-xs text-[var(--ws-ink-2)]">{TYPE_CONFIG[selectedType].desc}</div>
                  </div>
                </div>
                <div className="space-y-3 text-sm">
                  <div className="flex items-start gap-2">
                    <span className="text-[var(--ws-ink-3)] shrink-0">剧本</span>
                    <span className="text-[var(--ws-ink)] font-medium">{selectedPlaybook?.name || <span className="text-[var(--ws-ink-3)]">未选择</span>}</span>
                  </div>
                  <div className="text-xs text-[var(--ws-ink-2)] leading-relaxed bg-[var(--ws-border-subtle)] rounded-lg p-3">
                    {TYPE_CONFIG[selectedType].detail}
                  </div>
                </div>
              </Card>

              <Card
                className="shadow-sm border-[var(--ws-border)] rounded-xl"
                bodyStyle={{ padding: 20, background: 'var(--ws-surface)' }}
                title={
                  <span className="flex items-center gap-2 text-sm font-medium text-[var(--ws-ink)]">
                    <FileTextOutlined className="text-purple-500" />
                    已选剧本
                  </span>
                }
              >
                {selectedPlaybook ? (
                  <>
                    <div className="text-base font-semibold text-[var(--ws-ink)] mb-2">{selectedPlaybook.name}</div>
                    <div className="flex flex-wrap gap-2 mb-3">
                      <Tag color="blue">{selectedPlaybook.scenario_type}</Tag>
                      <Tag>{selectedPlaybook.task_type}</Tag>
                    </div>
                    {selectedPlaybook.declaration?.skills && (
                      <div>
                        <div className="text-xs text-[var(--ws-ink-3)] mb-1">技能</div>
                        <div className="flex flex-wrap gap-1">
                          {selectedPlaybook.declaration.skills.map((s: string, i: number) => (
                            <Tag key={i} className="text-xs">{s}</Tag>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-sm text-[var(--ws-ink-2)] leading-relaxed">
                    选择一个剧本作为任务模板，它将定义可用的资源、技能、产出物和蒸馏规则。
                  </div>
                )}
              </Card>
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}
