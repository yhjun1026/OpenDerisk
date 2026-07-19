'use client';

import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { Button, Card, Input, Select, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import type { Deliverable, DeliveryChannel } from './types';

interface DeliverablesSectionProps {
  value?: Deliverable[];
  onChange: (value: Deliverable[]) => void;
}

const DELIVERABLE_TYPES = [
  { value: 'report', label: 'report' },
  { value: 'alert', label: 'alert' },
  { value: 'notification', label: 'notification' },
  { value: 'artifact', label: 'artifact' },
];

const CATEGORY_OPTIONS = [
  { value: 'notify', label: 'notify' },
  { value: 'store', label: 'store' },
  { value: 'forward', label: 'forward' },
];

const CHANNEL_OPTIONS = [
  { value: 'in_app', label: 'in_app' },
  { value: 'email', label: 'email' },
  { value: 'webhook', label: 'webhook' },
  { value: 'dingtalk', label: 'dingtalk' },
  { value: 'feishu', label: 'feishu' },
];

const TARGET_OPTIONS = [
  { value: 'self', label: 'self' },
  { value: 'team', label: 'team' },
  { value: 'workspace', label: 'workspace' },
  { value: 'all', label: 'all' },
];

const FORMAT_OPTIONS = [
  { value: 'message_card', label: 'message_card' },
  { value: 'plain_text', label: 'plain_text' },
  { value: 'markdown', label: 'markdown' },
  { value: 'json', label: 'json' },
];

const INTERVENTION_OPTIONS = [
  { value: 'none', label: 'none' },
  { value: 'low', label: 'low' },
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
];

const DEFAULT_DELIVERY: DeliveryChannel = {
  category: 'notify',
  channel: 'in_app',
  target: 'self',
};

export default function DeliverablesSection({ value = [], onChange }: DeliverablesSectionProps) {
  const { t } = useTranslation();

  const handleAddDeliverable = () => {
    onChange([...value, { type: 'report', delivery: [{ ...DEFAULT_DELIVERY }] }]);
  };

  const handleRemoveDeliverable = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  const handleDeliverableChange = (index: number, field: keyof Deliverable, newValue: any) => {
    const next = value.map((item, i) => (i === index ? { ...item, [field]: newValue } : item));
    onChange(next);
  };

  const handleAddDelivery = (deliverableIndex: number) => {
    const next = value.map((item, i) =>
      i === deliverableIndex
        ? { ...item, delivery: [...item.delivery, { ...DEFAULT_DELIVERY }] }
        : item,
    );
    onChange(next);
  };

  const handleRemoveDelivery = (deliverableIndex: number, deliveryIndex: number) => {
    const next = value.map((item, i) =>
      i === deliverableIndex
        ? { ...item, delivery: item.delivery.filter((_, j) => j !== deliveryIndex) }
        : item,
    );
    onChange(next);
  };

  const handleDeliveryChange = (
    deliverableIndex: number,
    deliveryIndex: number,
    field: keyof DeliveryChannel,
    newValue: string,
  ) => {
    const next = value.map((item, i) => {
      if (i !== deliverableIndex) return item;
      return {
        ...item,
        delivery: item.delivery.map((d, j) => (j === deliveryIndex ? { ...d, [field]: newValue } : d)),
      };
    });
    onChange(next);
  };

  return (
    <div className="space-y-4">
      {value.length === 0 && (
        <Empty description={t('playbooks.visual_editor.deliverables.empty') || 'No deliverables configured'} />
      )}
      {value.map((deliverable, dIdx) => (
        <Card
          key={dIdx}
          size="small"
          className="border-gray-100"
          title={
            <div className="flex items-center gap-2">
              <Select
                value={deliverable.type}
                options={DELIVERABLE_TYPES}
                onChange={(val) => handleDeliverableChange(dIdx, 'type', val)}
                className="w-40"
              />
              <Input
                value={deliverable.title || ''}
                onChange={(e) => handleDeliverableChange(dIdx, 'title', e.target.value)}
                placeholder={t('playbooks.visual_editor.deliverables.title') || 'Title (optional)'}
                className="w-64"
              />
            </div>
          }
          extra={
            <Button
              icon={<DeleteOutlined />}
              danger
              size="small"
              onClick={() => handleRemoveDeliverable(dIdx)}
            />
          }
        >
          <div className="space-y-3">
            {deliverable.delivery.map((delivery, delIdx) => (
              <div
                key={delIdx}
                className="flex flex-wrap items-center gap-2 p-3 border border-gray-100 rounded-xl bg-gray-50/20"
              >
                <Select
                  value={delivery.category}
                  options={CATEGORY_OPTIONS}
                  onChange={(val) => handleDeliveryChange(dIdx, delIdx, 'category', val)}
                  className="w-28"
                  placeholder={t('playbooks.visual_editor.deliverables.category') || 'Category'}
                />
                <Select
                  value={delivery.channel}
                  options={CHANNEL_OPTIONS}
                  onChange={(val) => handleDeliveryChange(dIdx, delIdx, 'channel', val)}
                  className="w-32"
                  placeholder={t('playbooks.visual_editor.deliverables.channel') || 'Channel'}
                />
                <Select
                  value={delivery.target}
                  options={TARGET_OPTIONS}
                  onChange={(val) => handleDeliveryChange(dIdx, delIdx, 'target', val)}
                  className="w-32"
                  placeholder={t('playbooks.visual_editor.deliverables.target') || 'Target'}
                />
                <Select
                  value={delivery.format || undefined}
                  options={FORMAT_OPTIONS}
                  onChange={(val) => handleDeliveryChange(dIdx, delIdx, 'format', val)}
                  className="w-36"
                  placeholder={t('playbooks.visual_editor.deliverables.format') || 'Format'}
                  allowClear
                />
                <Select
                  value={delivery.require_intervention || undefined}
                  options={INTERVENTION_OPTIONS}
                  onChange={(val) => handleDeliveryChange(dIdx, delIdx, 'require_intervention', val)}
                  className="w-36"
                  placeholder={t('playbooks.visual_editor.deliverables.require_intervention') || 'Intervention'}
                  allowClear
                />
                <Button
                  icon={<DeleteOutlined />}
                  danger
                  size="small"
                  onClick={() => handleRemoveDelivery(dIdx, delIdx)}
                />
              </div>
            ))}
            <Button
              type="dashed"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => handleAddDelivery(dIdx)}
            >
              {t('playbooks.visual_editor.deliverables.add_delivery') || 'Add Delivery'}
            </Button>
          </div>
        </Card>
      ))}
      <Button type="dashed" icon={<PlusOutlined />} onClick={handleAddDeliverable}>
        {t('playbooks.visual_editor.deliverables.add') || 'Add Deliverable'}
      </Button>
    </div>
  );
}
