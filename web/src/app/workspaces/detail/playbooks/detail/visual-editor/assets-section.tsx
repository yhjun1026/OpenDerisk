'use client';

import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { Button, Input, Select, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import type { AssetRequired } from './types';

interface AssetsSectionProps {
  value?: AssetRequired[];
  onChange: (value: AssetRequired[]) => void;
}

const ASSET_TYPES = [
  { value: 'historical_artifact', label: 'historical_artifact' },
  { value: 'knowledge_doc', label: 'knowledge_doc' },
  { value: 'datasource_record', label: 'datasource_record' },
];

export default function AssetsSection({ value = [], onChange }: AssetsSectionProps) {
  const { t } = useTranslation();

  const handleAdd = () => {
    onChange([...value, { type: 'historical_artifact', query: '' }]);
  };

  const handleRemove = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  const handleChange = (index: number, field: keyof AssetRequired, newValue: string) => {
    const next = value.map((item, i) => (i === index ? { ...item, [field]: newValue } : item));
    onChange(next);
  };

  return (
    <div className="space-y-3">
      {value.length === 0 && (
        <Empty description={t('playbooks.visual_editor.assets_required.empty') || 'No assets configured'} />
      )}
      {value.map((item, index) => (
        <div key={index} className="flex items-center gap-2 p-3 border border-gray-100 rounded-xl bg-gray-50/20">
          <Select
            value={item.type}
            options={ASSET_TYPES}
            onChange={(val) => handleChange(index, 'type', val)}
            className="w-48"
            placeholder={t('playbooks.visual_editor.assets_required.type') || 'Asset Type'}
          />
          <Input
            value={item.query}
            onChange={(e) => handleChange(index, 'query', e.target.value)}
            placeholder={t('playbooks.visual_editor.assets_required.query') || 'Query'}
            className="flex-1"
          />
          <Button
            icon={<DeleteOutlined />}
            danger
            size="small"
            onClick={() => handleRemove(index)}
          />
        </div>
      ))}
      <Button type="dashed" icon={<PlusOutlined />} onClick={handleAdd}>
        {t('playbooks.visual_editor.assets_required.add') || 'Add Asset'}
      </Button>
    </div>
  );
}
