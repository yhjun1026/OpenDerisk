'use client';

import { useState } from 'react';
import { GPTVis } from '@antv/gpt-vis';
import {
  LoadingOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  RightOutlined,
  ToolOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import type { WorkspaceExecutionStep, WorkspaceView } from './agent-workspace-types';

/** 长文本默认折叠的行数阈值(按字符粗估) */
const CLAMP_CHARS = 160;

function StatusIcon({ status }: { status: WorkspaceExecutionStep['status'] }) {
  if (status === 'running') {
    return <LoadingOutlined className="ws-step__icon ws-step__icon--running" spin />;
  }
  if (status === 'failed') {
    return <CloseCircleFilled className="ws-step__icon ws-step__icon--failed" />;
  }
  return <CheckCircleFilled className="ws-step__icon ws-step__icon--done" />;
}

/** 用户消息气泡(manus left panel 风格) */
function UserBubble({ text }: { text: string }) {
  return (
    <div className="ws-step-user">
      <div className="ws-step-user__bubble">{text}</div>
    </div>
  );
}

/** 工具步骤行:紧凑一行,点击进场景空间看详情(左面板语义) */
function ToolStepRow({
  step,
  onStepClick,
}: {
  step: WorkspaceExecutionStep;
  onStepClick?: (s: WorkspaceExecutionStep) => void;
}) {
  return (
    <div
      className={`ws-step ws-step--tool${step.status === 'running' ? ' ws-step--running' : ''}`}
      role={onStepClick ? 'button' : undefined}
      tabIndex={onStepClick ? 0 : undefined}
      onClick={() => onStepClick?.(step)}
      onKeyDown={(e) => {
        if (onStepClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onStepClick(step);
        }
      }}
    >
      <StatusIcon status={step.status} />
      <span className="ws-step__badge ws-step__badge--tool">
        <ToolOutlined />
      </span>
      <span className="ws-step__title">{step.title}</span>
      {onStepClick && <RightOutlined className="ws-step__chevron" />}
    </div>
  );
}

/** 思考/阶段回复:弱化内联文本,过长折叠 */
function ThinkingBlock({ step }: { step: WorkspaceExecutionStep }) {
  const [expanded, setExpanded] = useState(false);
  const text = step.output || '';
  const needClamp = text.length > CLAMP_CHARS;
  return (
    <div className="ws-step-think">
      <div className="ws-step-think__head">
        <BulbOutlined className="ws-step-think__icon" />
        <span className="ws-step-think__label">{step.title}</span>
        {step.status === 'running' && <LoadingOutlined className="ws-step__icon ws-step__icon--running" spin />}
      </div>
      <div className={`ws-step-think__text${needClamp && !expanded ? ' ws-step-think__text--clamp' : ''}`}>
        {text}
      </div>
      {needClamp && (
        <span className="ws-step-think__toggle" onClick={() => setExpanded((v) => !v)}>
          {expanded ? '收起' : '展开'}
        </span>
      )}
    </div>
  );
}

const PLAN_STATUS_ICON: Record<string, string> = {
  pending: '○',
  running: '◐',
  done: '●',
  failed: '✕',
};

export interface AgentWorkspaceRendererProps {
  view: WorkspaceView;
  onStepClick?: (step: WorkspaceExecutionStep) => void;
}

export function AgentWorkspaceRenderer({ view, onStepClick }: AgentWorkspaceRendererProps) {
  return (
    <div className="ws-agent-renderer">
      {view.planning && (
        <div className="ws-agent-renderer__planning">
          <div className="ws-agent-renderer__goal">{view.planning.goal}</div>
          {view.planning.steps.map((s) => (
            <div key={s.id} className="ws-agent-renderer__plan-step">
              {PLAN_STATUS_ICON[s.status] ?? '○'} {s.title}
            </div>
          ))}
        </div>
      )}
      {view.execution.map((step) => {
        if (step.type === 'user') {
          return <UserBubble key={step.id} text={step.output || ''} />;
        }
        if (step.type === 'thinking') {
          return <ThinkingBlock key={step.id} step={step} />;
        }
        return <ToolStepRow key={step.id} step={step} onStepClick={onStepClick} />;
      })}
      {view.summary && (
        <div className="ws-agent-renderer__summary">
          {/* @ts-ignore rehypePlugins type mismatch is pre-existing repo-wide (see chat-detail-content.tsx) */}
          <GPTVis components={markdownComponents} {...markdownPlugins}>
            {preprocessLaTeX(view.summary)}
          </GPTVis>
        </div>
      )}
      {!view.execution.length && !view.summary && (
        <div className="ws-agent-renderer__empty">Agent 就绪,输入指令开始工作</div>
      )}
    </div>
  );
}
