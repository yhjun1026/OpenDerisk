'use client';

import { apiInterceptors, getDbList, getMCPList, getModelList, getAgents } from '@/client/api';
import { listSpaces } from '@/client/api/knowledge-vault';
import { DatabaseOutlined, ApiOutlined, BookOutlined, RobotOutlined, CloudOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Tabs } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ResourcePicker from './resource-picker';
import type { Resource, ResourceItem, ResourceType } from './types';

interface ResourcesSectionProps {
  value?: Resource[];
  onChange: (value: Resource[]) => void;
}

type ResourceTab = {
  key: ResourceType;
  labelKey: string;
  icon: React.ReactNode;
  color: string;
  fetchRef: (item: any) => string;
  fetchLabel: (item: any) => string;
  fetchDescription: (item: any) => string;
};

export default function ResourcesSection({ value = [], onChange }: ResourcesSectionProps) {
  const { t } = useTranslation();
  const [activeKey, setActiveKey] = useState<ResourceType>('datasource');

  const { data: dbData, loading: dbLoading, refresh: dbRefresh } = useRequest(async () => {
    const [, res] = await apiInterceptors(getDbList());
    return res ?? [];
  });

  const { data: mcpData, loading: mcpLoading, refresh: mcpRefresh } = useRequest(
    async () => await apiInterceptors(getMCPList({ filter: '' }, { page: '1', page_size: '200' })),
  );

  const { data: spaceData, loading: spaceLoading, refresh: spaceRefresh } = useRequest(async () => {
    const [, res] = await apiInterceptors(listSpaces());
    return res ?? [];
  });

  const { data: agentData, loading: agentLoading, refresh: agentRefresh } = useRequest(async () => {
    const [, res] = await apiInterceptors(getAgents());
    return res ?? [];
  });

  const { data: modelData, loading: modelLoading, refresh: modelRefresh } = useRequest(async () => {
    const [, res] = await apiInterceptors(getModelList());
    return res ?? [];
  });

  const resourcesByType = useMemo(() => {
    const map: Record<ResourceType, Resource[]> = {
      datasource: [],
      mcp: [],
      knowledge: [],
      app: [],
      llm_model: [],
    };
    value.forEach((r) => {
      if (map[r.type]) {
        map[r.type].push(r);
      }
    });
    return map;
  }, [value]);

  const getSelectedRefs = (type: ResourceType) => resourcesByType[type].map((r) => r.ref);

  const handleToggle = (type: ResourceType, ref: string) => {
    const selectedRefs = getSelectedRefs(type);
    const isEnabled = selectedRefs.includes(ref);
    if (isEnabled) {
      onChange(value.filter((r) => !(r.type === type && r.ref === ref)));
    } else {
      onChange([...value, { type, ref }]);
    }
  };

  const tabs: { key: ResourceType; label: string; icon: React.ReactNode; color: string; items: ResourceItem[]; loading: boolean; refresh: () => void }[] = [
    {
      key: 'datasource',
      label: `${t('playbooks.visual_editor.resources.databases') || 'Databases'} (${resourcesByType.datasource.length})`,
      icon: <DatabaseOutlined />,
      color: 'green',
      items: (dbData || []).map((db: any) => ({
        key: db.db_name,
        name: db.db_name,
        label: db.db_name,
        description: db.comment || db.db_host || '--',
        tag: { label: db.db_type, color: 'default' },
      })),
      loading: dbLoading,
      refresh: dbRefresh,
    },
    {
      key: 'mcp',
      label: `${t('playbooks.visual_editor.resources.mcp') || 'MCP'} (${resourcesByType.mcp.length})`,
      icon: <ApiOutlined />,
      color: 'purple',
      items: (((mcpData?.[1] as any)?.items) || []).map((mcp: any) => ({
        key: mcp.mcp_code,
        name: mcp.name,
        label: mcp.name,
        description: mcp.description || '',
      })),
      loading: mcpLoading,
      refresh: mcpRefresh,
    },
    {
      key: 'knowledge',
      label: `${t('playbooks.visual_editor.resources.knowledge') || 'Knowledge'} (${resourcesByType.knowledge.length})`,
      icon: <BookOutlined />,
      color: 'sky',
      items: (spaceData || []).map((space: any) => ({
        key: space.slug,
        name: space.name,
        label: space.name,
        description: space.description || '',
      })),
      loading: spaceLoading,
      refresh: spaceRefresh,
    },
    {
      key: 'app',
      label: `${t('playbooks.visual_editor.resources.agents') || 'Agents'} (${resourcesByType.app.length})`,
      icon: <RobotOutlined />,
      color: 'blue',
      items: (agentData || []).map((agent: any) => ({
        key: agent.name,
        name: agent.name,
        label: agent.label || agent.name,
        description: agent.describe || agent.desc || '',
      })),
      loading: agentLoading,
      refresh: agentRefresh,
    },
    {
      key: 'llm_model',
      label: `${t('playbooks.visual_editor.resources.models') || 'Models'} (${resourcesByType.llm_model.length})`,
      icon: <CloudOutlined />,
      color: 'orange',
      items: (modelData || []).map((model: any) => ({
        key: model.model_name,
        name: model.model_name,
        label: model.model_name,
        description: model.worker_type || '',
      })),
      loading: modelLoading,
      refresh: modelRefresh,
    },
  ];

  return (
    <Tabs
      activeKey={activeKey}
      onChange={(key) => setActiveKey(key as ResourceType)}
      items={tabs.map((tab) => ({
        key: tab.key,
        label: tab.label,
        children: (
          <ResourcePicker
            items={tab.items}
            selectedRefs={getSelectedRefs(tab.key)}
            loading={tab.loading}
            onRefresh={tab.refresh}
            onToggle={(ref) => handleToggle(tab.key, ref)}
            getRef={(item: ResourceItem) => item.key}
            getLabel={(item: ResourceItem) => item.label || item.name || item.key}
            getDescription={(item: ResourceItem) => item.description || ''}
            getTag={(item: ResourceItem) => item.tag || null}
            icon={tab.icon}
            activeColor={tab.color}
          />
        ),
      }))}
    />
  );
}
