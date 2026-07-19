'use client';

import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { Button, Input, Select, Switch, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import type { DistillConfig, DistillProduce } from './types';

interface DistillSectionProps {
  value?: DistillConfig;
  onChange: (value: DistillConfig) => void;
}

const PRODUCE_TYPES = [
  { value: 'historical_artifact', label: 'historical_artifact' },
  { value: 'knowledge_doc', label: 'knowledge_doc' },
  { value: 'case', label: 'case' },
];

export default function DistillSection({ value = { forced: true, produce: [] }, onChange }: DistillSectionProps) {
  const { t } = useTranslation();

  const handleForcedChange = (checked: boolean) => {
    onChange({ ...value, forced: checked });
  };

  const handleAddProduce = () => {
    onChange({
      ...value,
      produce: [...(value.produce || []), { type: 'historical_artifact', from: 'deliverable.0' }],
    });
  };

  const handleRemoveProduce = (index: number) => {
    onChange({
      ...value,
      produce: (value.produce || []).filter((_, i) => i !== index),
    });
  };

  const handleProduceChange = (index: number, field: keyof DistillProduce, newValue: string) => {
    const next = (value.produce || []).map((item, i) =>
      i === index ? { ...item, [field]: newValue } : item,
    );
    onChange({ ...value, produce: next });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-700">
          {t('playbooks.visual_editor.distill.forced') || 'Forced Distill'}
        </span>
        <Switch checked={value.forced} onChange={handleForcedChange} />
      </div>

      {(value.produce || []).length === 0 && (
        <Empty description={t('playbooks.visual_editor.distill.empty') || 'No produce entries configured'} />
      )}
      {(value.produce || []).map((item, index) => (
        <div key={index} className="flex items-center gap-2 p-3 border border-gray-100 rounded-xl bg-gray-50/20">
          <Select
            value={item.type}
            options={PRODUCE_TYPES}
            onChange={(val) => handleProduceChange(index, 'type', val)}
            className="w-44"
            placeholder={t('playbooks.visual_editor.distill.type') || 'Produce Type'}
          />
          <Input
            value={item.from}
            onChange={(e) => handleProduceChange(index, 'from', e.target.value)}
            placeholder={t('playbooks.visual_editor.distill.from') || 'From (e.g. deliverable.0)'}
            className="flex-1"
          />
          <Input
            value={item.when || ''}
            onChange={(e) => handleProduceChange(index, 'when', e.target.value)}
            placeholder={t('playbooks.visual_editor.distill.when') || 'Condition (optional)'}
            className="flex-1"
          />
          <Button
            icon={<DeleteOutlined />}
            danger
            size="small"
            onClick={() => handleRemoveProduce(index)}
          />
        </div>
      ))}
      <Button type="dashed" icon={<PlusOutlined />} onClick={handleAddProduce}>
        {t('playbooks.visual_editor.distill.add_produce') || 'Add Produce Entry'}
      </Button>
    </div>
  );
}
