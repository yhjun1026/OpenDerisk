'use client';

import { apiInterceptors, listResources } from '@/client/api';
import { DatabaseOutlined, ApiOutlined, BookOutlined, RobotOutlined, CloudOutlined, DeploymentUnitOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Tabs } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ResourcePicker from './resource-picker';
import type { Resource, ResourceItem, ResourceType } from './types';

interface ResourcesSectionProps {
  value?: Resource[];
  onChange: (value: Resource[]) => void;
  workspaceId?: number;
}

type ResourceTab = {
  key: ResourceType;
  label: string;
  icon: React.ReactNode;
  color: string;
  items: ResourceItem[];
  loading: boolean;
  refresh: () => void;
};

export default function ResourcesSection({ value = [], onChange, workspaceId }: ResourcesSectionProps) {
  const { t } = useTranslation();
  const [activeKey, setActiveKey] = useState<ResourceType>('datasource');

  const { data: resourceData, loading, refresh } = useRequest(
    async () => {
      if (!workspaceId) return [];
      const [err, res] = await apiInterceptors(listResources({ workspace_id: workspaceId }));
      return err ? [] : res || [];
    },
    { ready: !!workspaceId, refreshDeps: [workspaceId] },
  );

  const groups = useMemo(() => {
    const map: Record<ResourceType, any[]> = {
      datasource: [],
      mcp: [],
      knowledge: [],
      app: [],
      llm_model: [],
      ecp: [],
    };
    (resourceData || []).forEach((r: any) => {
      // 后端 workspace_resource.type -> 前端 ResourceType 映射
      const typeMap: Record<string, ResourceType> = {
        data_source: 'datasource',
        knowledge_space: 'knowledge',
        mcp: 'mcp',
        app: 'app',
        llm_model: 'llm_model',
        environment: 'app',
        ecp: 'ecp',
      };
      const key = typeMap[r.type];
      if (key) {
        map[key].push(r);
      }
    });
    return map;
  }, [resourceData]);

  const resourcesByType = useMemo(() => {
    const map: Record<ResourceType, Resource[]> = {
      datasource: [],
      mcp: [],
      knowledge: [],
      app: [],
      llm_model: [],
      ecp: [],
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

  const tabs: ResourceTab[] = [
    {
      key: 'datasource',
      label: `${t('playbooks.visual_editor.resources.databases') || 'Databases'} (${resourcesByType.datasource.length})`,
      icon: <DatabaseOutlined />,
      color: 'green',
      items: groups.datasource.map((r: any) => ({
        key: r.physical_ref || r.name,
        name: r.name,
        label: r.physical_ref || r.name,
        description: r.name !== (r.physical_ref || r.name) ? r.name : '',
      })),
      loading,
      refresh,
    },
    {
      key: 'mcp',
      label: `${t('playbooks.visual_editor.resources.mcp') || 'MCP'} (${resourcesByType.mcp.length})`,
      icon: <ApiOutlined />,
      color: 'purple',
      items: groups.mcp.map((r: any) => ({
        key: r.physical_ref || r.name,
        name: r.name,
        label: r.name,
        description: r.physical_ref || '',
      })),
      loading,
      refresh,
    },
    {
      key: 'knowledge',
      label: `${t('playbooks.visual_editor.resources.knowledge') || 'Knowledge'} (${resourcesByType.knowledge.length})`,
      icon: <BookOutlined />,
      color: 'sky',
      items: groups.knowledge.map((r: any) => ({
        key: r.physical_ref || r.name,
        name: r.name,
        label: r.name,
        description: r.physical_ref || '',
      })),
      loading,
      refresh,
    },
    {
      key: 'app',
      label: `${t('playbooks.visual_editor.resources.agents') || 'Agents'} (${resourcesByType.app.length})`,
      icon: <RobotOutlined />,
      color: 'blue',
      items: groups.app.map((r: any) => ({
        key: r.physical_ref || r.name,
        name: r.name,
        label: r.name,
        description: r.physical_ref || '',
      })),
      loading,
      refresh,
    },
    {
      key: 'llm_model',
      label: `${t('playbooks.visual_editor.resources.models') || 'Models'} (${resourcesByType.llm_model.length})`,
      icon: <CloudOutlined />,
      color: 'orange',
      items: groups.llm_model.map((r: any) => ({
        key: r.physical_ref || r.name,
        name: r.name,
        label: r.name,
        description: r.physical_ref || '',
      })),
      loading,
      refresh,
    },
    {
      key: 'ecp',
      label: `${t('playbooks.visual_editor.resources.ecp') || 'ECP 语义层'} (${resourcesByType.ecp.length})`,
      icon: <DeploymentUnitOutlined />,
      color: 'volcano',
      items: groups.ecp.map((r: any) => ({
        key: r.physical_ref || r.name,
        name: r.name,
        label: r.name,
        description: r.physical_ref || '',
      })),
      loading,
      refresh,
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
