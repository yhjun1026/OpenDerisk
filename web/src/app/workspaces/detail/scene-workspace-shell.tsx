'use client';

import './scene-workspace.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { apiInterceptors, getTaskInfo, listPlaybooks } from '@/client/api';
import type { WorkspaceEvent } from '@/hooks/use-chat';
import type { AgentStep, DetailContext } from './agent-types';
import { AgentWorkspace } from './agent-workspace';
import { SceneSpace } from './scene-space';
import { SceneTaskRail } from './scene-task-rail';
import type { AgentWorkspaceInputHandle } from './agent-workspace-types';

/** 判断当前任务列表里是否有活跃任务(running 等会变化的状态),决定是否开轮询。 */
export function hasActiveTask(tasks: any[]): boolean {
  const active = new Set(['running', 'pending_trigger', 'blocked', 'awaiting_human', 'draft']);
  return (tasks || []).some((t) => active.has(t?.status));
}

interface SceneWorkspaceShellProps {
  workspace: any;
  tasks: any[];
  interventions: any[];
  workspaceConvUid: string;
  appCode: string;
  onRefreshLists?: () => void;
  onConvChanged?: (convUid: string) => void;
  convLoadError?: string | null;
  retryLoadConv?: () => void;
}

export function SceneWorkspaceShell({
  workspace,
  tasks,
  interventions,
  workspaceConvUid,
  appCode,
  onRefreshLists,
  onConvChanged,
  convLoadError,
  retryLoadConv,
}: SceneWorkspaceShellProps) {
  const workspaceId = workspace?.id;
  const [previewItem, setPreviewItem] = useState<any>(null);
  const [detailContext, setDetailContext] = useState<DetailContext>('dashboard');
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null);
  const [activeTask, setActiveTask] = useState<any>(null);
  const [taskConvUid, setTaskConvUid] = useState<string>('');
  const [switchingTask, setSwitchingTask] = useState(false);
  // rail 抽屉(中屏)与单列 tab(小屏)状态
  const [railOpen, setRailOpen] = useState(true);
  const [mobilePane, setMobilePane] = useState<'rail' | 'space' | 'agent'>('space');
  // 隐式上下文:用户点 × 取消带入当前关注的交付物
  const [focusDismissed, setFocusDismissed] = useState(false);
  const prevActiveTaskId = useRef<number | null>(null);
  const agentInputRef = useRef<AgentWorkspaceInputHandle>(null);

  // 隐式上下文:用户当前在中间区域查看的交付物(artifact),发消息时自动带入 agent 上下文。
  // 仅 file-preview/entity-card 且有 artifact_id 时生效;点 chip × 设 focusDismissed 取消带入。
  const focus = useMemo<{ id: number; title: string } | null>(() => {
    if (focusDismissed) return null;
    if (detailContext !== 'file-preview' && detailContext !== 'entity-card') return null;
    const p = previewItem;
    const id = p?.payload?.artifact_id || p?.payload?.file_id || p?.artifact_id;
    if (!id) return null;
    const title = p?.payload?.title || p?.title || `artifact_${id}`;
    return { id: Number(id), title };
  }, [detailContext, previewItem, focusDismissed]);

  // 双向联动:把场景内容(任务)引用进 Agent 输入框
  const handleReference = (task: any) => {
    const title = task?.title || `task_${task?.id}`;
    agentInputRef.current?.insertText(`@任务#${task.id}「${title}」`);
    setMobilePane('agent');
  };

  // 中屏(900–1279px)默认收起左 rail 为抽屉;小屏默认展示场景空间
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(max-width: 1279px)');
    const apply = () => setRailOpen(!mq.matches);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  const { data: playbooks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [, data] = await apiInterceptors(listPlaybooks({ workspace_id: Number(workspaceId) }));
    return (data || []).map((p: any) => ({ playbook_id: p.id, playbook_name: p.name }));
  }, { refreshDeps: [workspaceId] });

  useEffect(() => {
    if (activeTaskId === prevActiveTaskId.current) return;
    prevActiveTaskId.current = activeTaskId;

    if (!activeTaskId) {
      setTaskConvUid('');
      setActiveTask(null);
      setSwitchingTask(false);
      return;
    }

    setSwitchingTask(true);
    setActiveTask(null);
    let cancelled = false;
    apiInterceptors(getTaskInfo(activeTaskId))
      .then(([, res]) => {
        if (!cancelled) {
          setTaskConvUid(res?.conv_session_id || '');
          setActiveTask(res || null);
          setSwitchingTask(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSwitchingTask(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeTaskId]);

  // 运行时轮询:有活跃任务时每 4s 刷新任务/介入列表,无活跃任务时停。
  // 后台 run_task 的状态变更无法走 workspace 事件流(fire-and-forget,无 SSE 连接),
  // 用轮询替代;task_created 事件触发的 onRefreshLists 仍保留。
  useEffect(() => {
    if (!hasActiveTask(tasks) || !onRefreshLists) return;
    const timer = setInterval(onRefreshLists, 4000);
    return () => clearInterval(timer);
  }, [tasks, onRefreshLists]);

  const handlePreview = (item: any, kind: 'task' | 'intervention') => {
    setPreviewItem(item);
    setDetailContext(kind === 'task' ? 'task-detail' : 'entity-card');
  };

  const handleEnterConversation = (taskId: number) => {
    setActiveTaskId(taskId);
    const task = tasks.find((t) => t.id === taskId);
    if (task) {
      setPreviewItem(task);
      setDetailContext('task-detail');
    }
  };

  const handleBackToDashboard = () => {
    setDetailContext('dashboard');
    setPreviewItem(null);
  };

  const handleStepClick = (step: AgentStep) => {
    setFocusDismissed(false);
    if (step.type === 'tool_call' || step.type === 'llm') {
      setPreviewItem(step);
      setDetailContext('tool-result');
      setMobilePane('space');
    } else if (step.payload?.file_id || step.payload?.file_name) {
      setPreviewItem(step);
      setDetailContext('file-preview');
      setMobilePane('space');
    } else if (step.payload?.task_id || step.payload?.asset_id) {
      setPreviewItem(step);
      setDetailContext('entity-card');
      setMobilePane('space');
    }
  };

  const handleWorkspaceEvent = (event: WorkspaceEvent) => {
    switch (event.type) {
      case 'artifact_produced':
        onRefreshLists?.();
        if (event.payload?.file_id || event.payload?.artifact_id) {
          setPreviewItem(event);
          setDetailContext(event.payload?.file_id ? 'file-preview' : 'entity-card');
          setFocusDismissed(false);
        }
        break;
      case 'task_created':
      case 'delivery_sent':
        onRefreshLists?.();
        break;
      case 'asset_referenced':
        setPreviewItem(event);
        setDetailContext('entity-card');
        setFocusDismissed(false);
        break;
      case 'intervention_triggered':
        onRefreshLists?.();
        if (event.payload?.task_id) {
          const task = tasks.find((t) => t.id === event.payload.task_id);
          if (task) {
            setPreviewItem(task);
            setDetailContext('task-detail');
          } else {
            setPreviewItem(event);
            setDetailContext('entity-card');
          }
        } else {
          setPreviewItem(event);
          setDetailContext('entity-card');
        }
        break;
      case 'context_loaded':
        // no-op: context was loaded
        break;
      default:
        break;
    }
  };

  const rightConvUid = activeTaskId ? taskConvUid : workspaceConvUid;
  const rightTaskId = activeTaskId ? activeTaskId : undefined;

  return (
    <div
      className={`ws-scene-shell${railOpen ? '' : ' ws-scene-shell--rail-closed'}`}
      data-pane={mobilePane}
    >
      <div className="ws-scene-shell__mobile-tabs" role="tablist">
        {([['rail', '任务'], ['space', '空间'], ['agent', 'Agent']] as const).map(([key, label]) => (
          <span
            key={key}
            role="tab"
            aria-selected={mobilePane === key}
            className={`ws-scene-shell__mobile-tab${mobilePane === key ? ' ws-scene-shell__mobile-tab--on' : ''}`}
            onClick={() => setMobilePane(key)}
          >
            {label}
          </span>
        ))}
      </div>
      <button
        type="button"
        className="ws-scene-shell__rail-toggle"
        aria-label={railOpen ? '收起任务栏' : '展开任务栏'}
        onClick={() => setRailOpen((v) => !v)}
      >
        {railOpen ? '‹' : '›'}
      </button>
      <div className="ws-scene-shell__rail">
        <SceneTaskRail
          tasks={tasks}
          interventions={interventions}
          workspaceId={workspaceId}
          activeTaskId={activeTaskId}
          disabled={switchingTask}
          playbooks={playbooks}
          onRefreshLists={onRefreshLists}
          onPreview={(item, kind) => {
            handlePreview(item, kind);
            setMobilePane('space');
            if (window.matchMedia('(max-width: 1279px)').matches) setRailOpen(false);
          }}
          onEnterConversation={(taskId) => {
            handleEnterConversation(taskId);
            setMobilePane('agent');
          }}
          onReference={handleReference}
        />
      </div>
      <div className="ws-scene-shell__space">
        <SceneSpace
          context={detailContext}
          previewItem={previewItem}
          activeTask={activeTask}
          workspaceId={workspaceId}
          workspaceCode={workspace?.workspace_code}
          onBack={handleBackToDashboard}
          onSelectTask={(taskId) => {
            const task = tasks.find((t) => t.id === taskId);
            if (task) handlePreview(task, 'task');
          }}
          onSelectArtifact={(artifact) => {
            setPreviewItem({ payload: { artifact_id: artifact.id, title: artifact.title, type: artifact.type } });
            setDetailContext('entity-card');
            setFocusDismissed(false);
          }}
        />
      </div>
      <div className="ws-scene-shell__agent">
        {activeTaskId && (
          <div className="ws-scene-shell__agent-mode">
            <span>任务对话: {activeTaskId}</span>
            <Button size="small" icon={<CloseOutlined />} onClick={() => setActiveTaskId(null)}>退出任务对话</Button>
          </div>
        )}
        <AgentWorkspace
          convUid={rightConvUid}
          appCode={appCode}
          workspaceId={workspaceId}
          taskId={rightTaskId}
          focus={focus}
          onClearFocus={() => setFocusDismissed(true)}
          onStepClick={handleStepClick}
          onWorkspaceEvent={handleWorkspaceEvent}
          onConvChanged={onConvChanged}
          inputRef={agentInputRef}
          switchingTask={switchingTask}
          convLoadError={convLoadError}
          retryLoadConv={retryLoadConv}
          playbooks={playbooks}
        />
      </div>
    </div>
  );
}