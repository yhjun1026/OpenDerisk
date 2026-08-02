'use client';

import './scene-workspace.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { App, Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { apiInterceptors, createConversation, getTaskInfo, linkConversation, listConversations, listPlaybooks, setCurrentConversation } from '@/client/api';
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
  onConvChanged?: (convUid: string, taskId?: number | null) => void;
  convLoadError?: string | null;
  retryLoadConv?: () => void;
  /** 从会话列表选中会话时携带的 task_id:number=进 task 对话,null=workspace 级会话,
   * undefined=非列表触发(初始/任务栏进入)。 */
  pendingTaskId?: number | null | undefined;
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
  pendingTaskId,
}: SceneWorkspaceShellProps) {
  const workspaceId = workspace?.id;
  const [previewItem, setPreviewItem] = useState<any>(null);
  const [detailContext, setDetailContext] = useState<DetailContext>('dashboard');
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null);
  const [activeTask, setActiveTask] = useState<any>(null);
  const [taskConvUid, setTaskConvUid] = useState<string>('');
  const [switchingTask, setSwitchingTask] = useState(false);
  const { message } = App.useApp();
  // rail 抽屉(中屏)与单列 tab(小屏)状态
  const [railOpen, setRailOpen] = useState(true);
  const [mobilePane, setMobilePane] = useState<'rail' | 'space' | 'agent'>('space');
  // 隐式上下文:用户点 × 取消带入当前关注的交付物
  const [focusDismissed, setFocusDismissed] = useState(false);
  // 收件箱刷新信号:中间区域确认/否决 ECP 提案后 bump,通知左侧 rail 重新拉待办。
  const [inboxTick, setInboxTick] = useState(0);
  const bumpInbox = () => setInboxTick((t) => t + 1);
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

  // 一键清空上下文(新开会话):复用 ConversationSwitcher.handleNew 逻辑--
  // 新 conv_uid 在 gpts_messages/gpts_conversations/chat_history_message 三表无行,
  // agent 上下文天然干净;旧会话保留在会话列表可回溯。
  const handleClearContext = async () => {
    if (!workspaceId) return;
    const [, newConv] = await apiInterceptors(createConversation({ workspace_id: workspaceId }));
    if (!newConv?.conv_uid) return;
    await apiInterceptors(linkConversation({ workspace_id: workspaceId, conv_uid: newConv.conv_uid, user_id: undefined }));
    await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
    onConvChanged?.(newConv.conv_uid);
    message.success('已清空上下文');
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

  // 会话维度列表:剧本任务会话 + 大厅会话统一按 conv 维度展示。
  // refreshDeps 含 workspaceConvUid/taskConvUid:清理(新开会话)/切换会话/进入任务对话后自动刷新,
  // 新会话按 gmt_modified 倒序自然置顶。
  const { data: conversations } = useRequest(
    async () => {
      if (!workspaceId) return [];
      const [, data] = await apiInterceptors(listConversations({ workspace_id: workspaceId, limit: 200 }));
      return data || [];
    },
    { refreshDeps: [workspaceId, workspaceConvUid, taskConvUid] },
  );

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

  const handlePreview = (item: any, kind: 'task' | 'intervention' | 'ecp_proposal') => {
    setPreviewItem(item);
    if (kind === 'task') setDetailContext('task-detail');
    else if (kind === 'ecp_proposal') setDetailContext('ecp-proposal');
    else setDetailContext('entity-card');
  };

  const handleEnterConversation = (taskId: number) => {
    setActiveTaskId(taskId);
    const task = tasks.find((t) => t.id === taskId);
    if (task) {
      setPreviewItem(task);
      setDetailContext('task-detail');
    }
  };

  // 从会话列表选中会话:有 task_id -> 进 task 对话(复用 handleEnterConversation,
  // 由 activeTaskId effect 调 getTaskInfo 恢复 taskConvUid);无 task_id -> 回 dashboard。
  // pendingTaskId === undefined 表示非列表触发,不动(初始/任务栏进入走各自路径)。
  useEffect(() => {
    if (pendingTaskId === undefined) return;
    if (pendingTaskId === null) {
      setActiveTaskId(null);
      setDetailContext('dashboard');
      setPreviewItem(null);
    } else {
      handleEnterConversation(pendingTaskId);
    }
  }, [pendingTaskId]);

  const handleBackToDashboard = () => {
    setDetailContext('dashboard');
    setPreviewItem(null);
  };

  // 从「会话」视图进入对应对话:剧本任务会话(有 task_id)进任务对话,
  // 大厅会话(无 task_id)切回 workspace 级会话并回到 dashboard。
  const handleOpenConversation = async (convUid: string, taskId: number | null) => {
    if (taskId) {
      handleEnterConversation(taskId);
      return;
    }
    await apiInterceptors(setCurrentConversation(workspaceId, convUid));
    setActiveTaskId(null);
    setDetailContext('dashboard');
    setPreviewItem(null);
    onConvChanged?.(convUid, null);
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
          inboxTick={inboxTick}
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
          conversations={conversations || []}
          currentConvUid={rightConvUid}
          onOpenConversation={(convUid, taskId) => {
            handleOpenConversation(convUid, taskId);
            setMobilePane(taskId ? 'agent' : 'space');
            if (window.matchMedia('(max-width: 1279px)').matches) setRailOpen(false);
          }}
        />
      </div>
      <div className="ws-scene-shell__space">
        <SceneSpace
          context={detailContext}
          previewItem={previewItem}
          activeTask={activeTask}
          workspaceId={workspaceId}
          workspaceCode={workspace?.workspace_code}
          playbooks={playbooks}
          onBack={handleBackToDashboard}
          onProposalResolved={bumpInbox}
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
          onClearContext={activeTaskId ? undefined : handleClearContext}
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