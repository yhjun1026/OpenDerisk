'use client';

import { apiInterceptors, batchAddMaskingConfig, previewMasking } from '@/client/api';
import {
  BatchMaskingConfigResponse,
  MASKING_MODE_OPTIONS,
  SENSITIVE_TYPE_OPTIONS,
} from '@/types/db';
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Divider,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd';
import React, { useCallback, useEffect, useState } from 'react';

// 默认示例值，便于"原值→脱敏值"试运行展示
const SAMPLE_BY_TYPE: Record<string, string> = {
  phone: '13812345678',
  email: 'user@example.com',
  id_card: '310101199001011234',
  bank_card: '6222021234561234567',
  address: '上海市浦东新区张江路100号',
  name: '张三丰',
  password: 'p@ssw0rd',
  token: 'sk-abc123def456',
  ip_address: '192.168.1.100',
  custom: 'sensitive-value',
};

interface MaskingRule {
  id: number;
  column_names: string;
  sensitive_type: string;
  masking_mode: string;
  ignore_case: boolean;
  status: 'idle' | 'applying' | 'done' | 'error';
  result?: BatchMaskingConfigResponse;
  error?: string;
  preview?: { original: string; masked: string };
}

interface BatchMaskingModalProps {
  open: boolean;
  datasourceId: number;
  onCancel: () => void;
  onSuccess: () => void;
}

let RULE_ID_SEQ = 1;

function newRule(): MaskingRule {
  return {
    id: RULE_ID_SEQ++,
    column_names: '',
    sensitive_type: 'phone',
    masking_mode: 'mask',
    ignore_case: true,
    status: 'idle',
  };
}

function RuleCard({
  rule,
  onChange,
  onRemove,
}: {
  rule: MaskingRule;
  onChange: (patch: Partial<MaskingRule>) => void;
  onRemove: () => void;
}) {
  // Per-rule preview (debounced), independent across rules.
  useEffect(() => {
    if (rule.status === 'done' || !rule.sensitive_type) return;
    const sample = SAMPLE_BY_TYPE[rule.sensitive_type] || SAMPLE_BY_TYPE.custom;
    const handle = setTimeout(async () => {
      const [err, res] = await apiInterceptors(
        previewMasking({
          sensitive_type: rule.sensitive_type,
          masking_mode: rule.masking_mode || 'mask',
          sample_value: sample,
        }),
      );
      if (!err && res) {
        onChange({ preview: { original: res.original, masked: res.masked } });
      }
    }, 250);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule.sensitive_type, rule.masking_mode]);

  const statusTag = () => {
    switch (rule.status) {
      case 'applying':
        return <Tag color="processing">applying</Tag>;
      case 'done':
        return (
          <Tag color="green">
            <CheckCircleOutlined /> +{rule.result?.total_configs_added ?? 0}
          </Tag>
        );
      case 'error':
        return (
          <Tag color="red">
            <CloseCircleOutlined /> failed
          </Tag>
        );
      default:
        return null;
    }
  };

  return (
    <div
      style={{
        border: '1px solid #f0f0f0',
        borderRadius: 6,
        padding: 12,
        marginBottom: 12,
      }}
    >
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
        <Space>{statusTag()}</Space>
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={onRemove}
        />
      </Space>

      <Input.TextArea
        rows={2}
        value={rule.column_names}
        placeholder="phone, mobile, telephone..."
        onChange={(e) => onChange({ column_names: e.target.value, status: 'idle' })}
        style={{ marginBottom: 8 }}
      />

      <Space wrap style={{ marginBottom: 8 }}>
        <Select
          size="small"
          style={{ width: 150 }}
          value={rule.sensitive_type}
          options={SENSITIVE_TYPE_OPTIONS.map((o) => ({
            value: o.value,
            label: `${o.label} (${o.labelEn})`,
          }))}
          onChange={(v) => onChange({ sensitive_type: v, status: 'idle' })}
        />
        <Select
          size="small"
          style={{ width: 140 }}
          value={rule.masking_mode}
          options={MASKING_MODE_OPTIONS.map((o) => ({
            value: o.value,
            label: `${o.label} (${o.labelEn})`,
          }))}
          onChange={(v) => onChange({ masking_mode: v, status: 'idle' })}
        />
        <Space size={4}>
          <Switch
            size="small"
            checked={rule.ignore_case}
            onChange={(v) => onChange({ ignore_case: v, status: 'idle' })}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            ignore case
          </Typography.Text>
        </Space>
      </Space>

      {rule.preview && (
        <div
          style={{
            background: 'rgba(0,0,0,0.02)',
            borderRadius: 4,
            padding: '6px 10px',
            marginBottom: 8,
          }}
        >
          <Space size={8}>
            <code style={{ fontSize: 12 }}>{rule.preview.original}</code>
            <ArrowRightOutlined style={{ color: '#999', fontSize: 12 }} />
            <Tag color="blue" style={{ fontSize: 12 }}>
              {rule.preview.masked}
            </Tag>
          </Space>
        </div>
      )}

      {rule.status === 'done' && rule.result && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          scanned {rule.result.total_tables_scanned} tables · matched{' '}
          {rule.result.total_columns_matched} columns · added{' '}
          {rule.result.total_configs_added}
        </Typography.Text>
      )}
      {rule.status === 'error' && rule.error && (
        <Typography.Text type="danger" style={{ fontSize: 12 }}>
          {rule.error}
        </Typography.Text>
      )}
      {rule.status === 'done' && rule.result && rule.result.matched_columns.length > 0 && (
        <List
          size="small"
          split={false}
          style={{ marginTop: 6, maxHeight: 120, overflow: 'auto' }}
          dataSource={rule.result.matched_columns}
          renderItem={(item) => (
            <List.Item style={{ padding: '2px 0' }}>
              <Typography.Text style={{ fontSize: 12 }}>
                <code>
                  {item.table}.{item.column}
                </code>
              </Typography.Text>
            </List.Item>
          )}
        />
      )}
    </div>
  );
}

export default function BatchMaskingModal({
  open,
  datasourceId,
  onCancel,
  onSuccess,
}: BatchMaskingModalProps) {
  const { message } = App.useApp();
  const [rules, setRules] = useState<MaskingRule[]>([]);
  const [applying, setApplying] = useState(false);
  const [anyApplied, setAnyApplied] = useState(false);

  // Reset when modal opens
  useEffect(() => {
    if (open) {
      setRules([newRule()]);
      setAnyApplied(false);
    }
  }, [open]);

  const updateRule = useCallback((id: number, patch: Partial<MaskingRule>) => {
    setRules((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }, []);

  const addRule = () => setRules((prev) => [...prev, newRule()]);

  const removeRule = (id: number) =>
    setRules((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));

  const applyOne = async (rule: MaskingRule): Promise<boolean> => {
    const columnNames = rule.column_names
      .split(/[,\s]+/)
      .map((n) => n.trim())
      .filter((n) => n.length > 0);
    if (columnNames.length === 0) {
      updateRule(rule.id, { status: 'error', error: 'No column names entered' });
      return false;
    }
    updateRule(rule.id, { status: 'applying', error: undefined });
    const [err, res] = await apiInterceptors(
      batchAddMaskingConfig(datasourceId, {
        column_names: columnNames,
        sensitive_type: rule.sensitive_type,
        masking_mode: rule.masking_mode || 'mask',
        ignore_case: rule.ignore_case ?? true,
      }),
    );
    if (err || !res) {
      updateRule(rule.id, {
        status: 'error',
        error: 'Batch apply failed',
      });
      return false;
    }
    setAnyApplied(true);
    updateRule(rule.id, { status: 'done', result: res });
    return true;
  };

  const handleApplyAll = async () => {
    setApplying(true);
    // Sequential apply: upsert has no cross-request transaction, no rollback.
    for (const rule of rules) {
      // eslint-disable-next-line no-await-in-loop
      await applyOne(rule);
    }
    setApplying(false);
    message.success('Batch masking applied');
  };

  const handleRetry = (rule: MaskingRule) => {
    setApplying(true);
    applyOne(rule).finally(() => setApplying(false));
  };

  const handleRetryAll = async () => {
    setApplying(true);
    for (const rule of rules.filter((r) => r.status === 'error')) {
      // eslint-disable-next-line no-await-in-loop
      await applyOne(rule);
    }
    setApplying(false);
  };

  const handleClose = () => {
    if (anyApplied) onSuccess();
    onCancel();
  };

  const hasError = rules.some((r) => r.status === 'error');

  return (
    <Modal
      title={
        <Space>
          <SafetyCertificateOutlined />
          Batch Masking Configuration
        </Space>
      }
      open={open}
      onCancel={handleClose}
      width={560}
      destroyOnClose
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Button onClick={addRule} icon={<PlusOutlined />} disabled={applying}>
            Add Rule
          </Button>
          <Space>
            {hasError && (
              <Button
                onClick={handleRetryAll}
                loading={applying}
                icon={<ReloadOutlined />}
              >
                Retry Failed
              </Button>
            )}
            <Button onClick={handleClose}>Close</Button>
            <Button type="primary" loading={applying} onClick={handleApplyAll}>
              Apply All
            </Button>
          </Space>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="按列名模式批量配置脱敏。后应用的规则会覆盖同名列的先前配置。"
      />

      {rules.map((rule) => (
        <RuleCard
          key={rule.id}
          rule={rule}
          onChange={(patch) => updateRule(rule.id, patch)}
          onRemove={() => removeRule(rule.id)}
        />
      ))}

      <Divider style={{ margin: '8px 0' }} />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        支持多列名(逗号或空格分隔);每条规则独立试运行预览,Apply All 逐条串行应用,失败可重试。
      </Typography.Text>
    </Modal>
  );
}