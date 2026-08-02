'use client';

import { Alert, Collapse, Input, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import AssetsSection from './assets-section';
import DeliverablesSection from './deliverables-section';
import DistillSection from './distill-section';
import ResourcesSection from './resources-section';
import SkillsSection from './skills-section';
import TextContentSection from './text-content-section';
import type { PlaybookDeclaration } from './types';

interface VisualEditorProps {
  declaration: PlaybookDeclaration;
  onDeclarationChange: (partial: Partial<PlaybookDeclaration>) => void;
  metaName?: string;
  onMetaNameChange?: (name: string) => void;
  metaScenarioType?: string;
  onMetaScenarioTypeChange?: (scenarioType: string) => void;
  metaTaskType?: string;
  onMetaTaskTypeChange?: (taskType: string) => void;
  invalidJson?: boolean;
  invalidJsonMessage?: string;
  workspaceId?: number;
}

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

export default function VisualEditor({
  declaration,
  onDeclarationChange,
  metaName,
  onMetaNameChange,
  metaScenarioType,
  onMetaScenarioTypeChange,
  metaTaskType,
  onMetaTaskTypeChange,
  invalidJson,
  invalidJsonMessage,
  workspaceId,
}: VisualEditorProps) {
  const { t } = useTranslation();

  if (invalidJson) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t('playbooks.visual_editor.invalid_json_warning') || 'JSON is invalid, cannot render visual editor.'}
        description={invalidJsonMessage}
      />
    );
  }

  const showMeta =
    onMetaNameChange !== undefined ||
    onMetaScenarioTypeChange !== undefined ||
    onMetaTaskTypeChange !== undefined;

  const collapseItems = [
    {
      key: 'text_content',
      label: t('playbooks.visual_editor.text_content') || 'Text Content',
      children: (
        <TextContentSection
          value={declaration.text_content}
          onChange={(text_content) => onDeclarationChange({ text_content })}
        />
      ),
    },
    {
      key: 'skills',
      label: t('playbooks.visual_editor.skills') || 'Skills',
      children: (
        <SkillsSection
          value={declaration.skills}
          onChange={(skills) => onDeclarationChange({ skills })}
        />
      ),
    },
    {
      key: 'resources',
      label: t('playbooks.visual_editor.resources') || 'Resources',
      children: (
        <ResourcesSection
          value={declaration.context?.resources}
          onChange={(resources) =>
            onDeclarationChange({
              context: { ...declaration.context, resources },
            })
          }
          workspaceId={workspaceId}
        />
      ),
    },
    {
      key: 'assets_required',
      label: t('playbooks.visual_editor.assets_required') || 'Assets Required',
      children: (
        <AssetsSection
          value={declaration.context?.assets_required}
          onChange={(assets_required) =>
            onDeclarationChange({
              context: { ...declaration.context, assets_required },
            })
          }
        />
      ),
    },
    {
      key: 'deliverables',
      label: t('playbooks.visual_editor.deliverables') || 'Deliverables',
      children: (
        <DeliverablesSection
          value={declaration.deliverables}
          onChange={(deliverables) => onDeclarationChange({ deliverables })}
        />
      ),
    },
    {
      key: 'distill',
      label: t('playbooks.visual_editor.distill') || 'Distill',
      children: (
        <DistillSection
          value={declaration.distill}
          onChange={(distill) => onDeclarationChange({ distill })}
        />
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {showMeta && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 border border-gray-100 rounded-xl bg-gray-50/20">
          {onMetaNameChange && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('playbooks.name') || 'Name'}
              </label>
              <Input
                value={metaName}
                onChange={(e) => onMetaNameChange?.(e.target.value)}
                placeholder={t('playbooks.name') || 'Name'}
              />
            </div>
          )}
          {onMetaScenarioTypeChange && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('playbooks.scenario') || 'Scenario'}
              </label>
              <Select
                value={metaScenarioType}
                options={SCENARIO_OPTIONS}
                onChange={(val) => onMetaScenarioTypeChange?.(val)}
                className="w-full"
              />
            </div>
          )}
          {onMetaTaskTypeChange && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('playbooks.task_type') || 'Task Type'}
              </label>
              <Select
                value={metaTaskType}
                options={TASK_TYPE_OPTIONS}
                onChange={(val) => onMetaTaskTypeChange?.(val)}
                className="w-full"
              />
            </div>
          )}
        </div>
      )}

      <Collapse
        defaultActiveKey={['text_content', 'skills', 'resources', 'deliverables']}
        items={collapseItems}
      />
    </div>
  );
}
