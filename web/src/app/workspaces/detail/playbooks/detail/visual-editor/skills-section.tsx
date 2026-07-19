'use client';

import { apiInterceptors, getSkillList } from '@/client/api';
import { AppstoreOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useMemo } from 'react';
import ResourcePicker from './resource-picker';
import type { ResourceItem, SkillRef } from './types';

interface SkillsSectionProps {
  value?: SkillRef[];
  onChange: (value: SkillRef[]) => void;
}

export default function SkillsSection({ value = [], onChange }: SkillsSectionProps) {
  const { data: skillData, loading, refresh } = useRequest(
    async () => await apiInterceptors(getSkillList({ filter: '' }, { page: 1, page_size: 200 })),
  );

  const skills = useMemo(() => {
    const [, res] = skillData || [];
    const items = res?.items || [];
    return items.map((item: any) => ({
      key: item.skill_code,
      name: item.name,
      label: item.name,
      description: item.description || '',
      type: 'skill',
      skillCode: item.skill_code,
      author: item.author,
    }));
  }, [skillData]);

  const selectedRefs = useMemo(() => {
    return value
      .map((skill) => (typeof skill === 'string' ? skill : skill?.name))
      .filter((name): name is string => !!name);
  }, [value]);

  const handleToggle = (ref: string) => {
    const isEnabled = selectedRefs.includes(ref);
    if (isEnabled) {
      onChange(value.filter((skill) => {
        const name = typeof skill === 'string' ? skill : skill?.name;
        return name !== ref;
      }));
    } else {
      onChange([...value, { type: 'skill', name: ref }]);
    }
  };

  return (
    <ResourcePicker
      items={skills}
      selectedRefs={selectedRefs}
      loading={loading}
      onRefresh={refresh}
      onToggle={handleToggle}
      getRef={(item: ResourceItem) => item.key}
      getLabel={(item: ResourceItem) => item.label || item.name || item.key}
      getDescription={(item: ResourceItem) => item.description || item.type || ''}
      icon={<AppstoreOutlined />}
      activeColor="orange"
    />
  );
}
