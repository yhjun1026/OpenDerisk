'use client';

import { useEffect, useRef } from 'react';
import { Alert, Button, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep } from './agent-types';
import { AgentWorkspaceInput } from './agent-workspace-input';
import { AgentWorkspaceRenderer } from './agent-workspace-renderer';
import { ConversationSwitcher } from './conversation-switcher';
import type { AgentWorkspaceInputHandle } from './agent-workspace-types';
import { useSceneAgentChat } from './use-scene-agent-chat';

export interface AgentWorkspaceProps {
  convUid?: string;
  appCode?: string;
  workspaceId?: number | string;
  taskId?: number | string;
  focus?: { id: number; title: string } | null;
  onClearFocus?: () => void;
  onStepClick?: (step: AgentStep) => void;
  onWorkspaceEvent?: (event: WorkspaceEvent) => void;
  onConvChanged?: (convUid: string) => void;
  inputRef?: React.Ref<AgentWorkspaceInputHandle>;
  switchingTask?: boolean;
  convLoadError?: string | null;
  retryLoadConv?: () => void;
  playbooks?: { playbook_id: number; playbook_name: string }[];
}

export function AgentWorkspace({
  convUid,
  appCode,
  workspaceId,
  taskId,
  focus,
  onClearFocus,
  onStepClick,
  onWorkspaceEvent,
  onConvChanged,
  inputRef: inputRefProp,
  switchingTask,
  convLoadError,
  retryLoadConv,
  playbooks,
}: AgentWorkspaceProps) {
  const inputRefInner = useRef<AgentWorkspaceInputHandle>(null);
  const inputRef = inputRefProp ?? inputRefInner;
  const { steps, workspaceView, loading, error, lastInput, send, clearSteps, clearWorkspaceView } = useSceneAgentChat({
    convUid,
    appCode,
    workspaceId,
    taskId,
    focusArtifactId: focus?.id,
    onWorkspaceEvent,
  });

  useEffect(() => {
    clearSteps();
    clearWorkspaceView();
  }, [convUid, clearSteps, clearWorkspaceView]);

  return (
    <div className="ws-agent-workspace">
      <div className="ws-agent-workspace__header">
        <span
          className={`ws-agent-workspace__status${
            loading ? ' ws-agent-workspace__status--running' : error ? ' ws-agent-workspace__status--error' : ''
          }`}
        />
        <span className="ws-agent-workspace__header-title">
          {taskId ? `任务 #${taskId} · Agent` : 'Agent 空间'}
        </span>
        {onConvChanged && !taskId && workspaceId && convUid && (
          <ConversationSwitcher
            workspaceId={Number(workspaceId)}
            currentConvUid={convUid}
            onChanged={onConvChanged}
          />
        )}
        <span className="ws-agent-workspace__header-state">
          {loading ? '运行中…' : error ? '出错了' : '就绪'}
        </span>
      </div>
      <div className="ws-agent-workspace__process">
        {error && <Alert message={error} type="error" showIcon className="ws-agent-workspace__error" />}
        {switchingTask ? (
          <div className="ws-agent-workspace__loading">
            <Spin tip="切换任务对话中..." />
          </div>
        ) : convLoadError && !convUid ? (
          <div className="ws-agent-workspace__error-card">
            <Alert
              message="会话加载失败"
              description={convLoadError}
              type="error"
              showIcon
              action={
                retryLoadConv ? (
                  <Button size="small" icon={<ReloadOutlined />} onClick={retryLoadConv}>重试</Button>
                ) : undefined
              }
            />
          </div>
        ) : !convUid ? (
          <div className="ws-agent-workspace__loading"><Spin /></div>
        ) : (
          <AgentWorkspaceRenderer
            view={workspaceView}
            onStepClick={onStepClick ? (s) => onStepClick({
              id: s.id,
              type: s.type === 'thinking' ? 'llm' : 'tool_call',
              title: s.title,
              status: s.status === 'running' ? 'running' : s.status === 'failed' ? 'failed' : 'done',
              timestamp: Date.now(),
              payload: {
                action: s.action,
                action_input: s.action_input,
                output: s.output,
                step_type: s.type,
              },
            }) : undefined}
          />
        )}
      </div>
      <div className="ws-agent-workspace__input">
        <AgentWorkspaceInput
          ref={inputRef}
          convUid={convUid}
          onSend={(p) => send(p)}
          loading={loading}
          disabled={!convUid || switchingTask}
          lastInput={lastInput ? { text: typeof lastInput.text === 'string' ? lastInput.text : '' } : null}
          onRetry={lastInput ? () => send(lastInput) : undefined}
          playbooks={playbooks}
          focus={focus}
          onClearFocus={onClearFocus}
        />
      </div>
    </div>
  );
}