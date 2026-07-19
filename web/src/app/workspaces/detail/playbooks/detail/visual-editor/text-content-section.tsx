'use client';

import { Input } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TextContent } from './types';

const { TextArea } = Input;

interface TextContentSectionProps {
  value?: TextContent;
  onChange: (value: TextContent) => void;
}

const FIELDS: { key: keyof TextContent; rows: number }[] = [
  { key: 'role_definition', rows: 3 },
  { key: 'goal', rows: 3 },
  { key: 'workflow', rows: 6 },
  { key: 'behavior_constraints', rows: 4 },
  { key: 'background', rows: 3 },
];

export default function TextContentSection({ value = {}, onChange }: TextContentSectionProps) {
  const { t } = useTranslation();

  const handleChange = (field: keyof TextContent, newValue: string) => {
    onChange({ ...value, [field]: newValue });
  };

  return (
    <div className="space-y-4">
      {FIELDS.map(({ key, rows }) => (
        <div key={key}>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t(`playbooks.visual_editor.${key}`) || key}
          </label>
          <TextArea
            className="font-mono text-xs"
            value={value[key] || ''}
            onChange={(e) => handleChange(key, e.target.value)}
            autoSize={{ minRows: rows, maxRows: rows + 4 }}
            placeholder=""
          />
        </div>
      ))}
    </div>
  );
}
