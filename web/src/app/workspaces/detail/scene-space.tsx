'use client';

import { useMemo } from 'react';
import { Button, Card, Spin, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { GPTVis } from '@antv/gpt-vis';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import { apiInterceptors, getArtifactInfo, listArtifacts } from '@/client/api';
import { Lobby } from './lobby';
import type { DetailContext } from './agent-types';

export interface SceneSpaceProps {
  context: DetailContext;
  previewItem?: any;
  activeTask?: any;
  workspaceId: number;
  workspaceCode: string;
  onBack: () => void;
  onSelectTask?: (taskId: number) => void;
  onSelectArtifact?: (artifact: any) => void;
}

const STATUS_COLOR: Record<string, string> = {
  running: 'processing',
  done: 'success',
  failed: 'error',
  pending: 'default',
};

// 按 key 识别长文本内容字段,走 markdown 渲染而非纯文本
const CONTENT_KEYS = new Set(['content_text', 'message', 'output', 'content', 'vis_final']);

function isHtml(text: string): boolean {
  const head = text.trimStart().slice(0, 200).toLowerCase();
  return head.startsWith('<!doctype') || head.startsWith('<html');
}

function Markdown({ text }: { text: string }) {
  return (
    // @ts-ignore rehypePlugins type mismatch is pre-existing repo-wide (see chat-detail-content.tsx)
    <GPTVis components={markdownComponents} {...markdownPlugins}>
      {preprocessLaTeX(text)}
    </GPTVis>
  );
}

/** 内容渲染器:html → 沙箱 iframe;JSON → 格式化代码块;长文本 → markdown。 */
function ContentView({ text }: { text: string }) {
  if (isHtml(text)) {
    return (
      <iframe
        className="ws-preview__html"
        sandbox="allow-same-origin"
        srcDoc={text}
        title="content preview"
      />
    );
  }
  const trimmed = text.trim();
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      const pretty = JSON.stringify(JSON.parse(trimmed), null, 2);
      return (
        <div className="ws-preview__markdown">
          <Markdown text={'```json\n' + pretty + '\n```'} />
        </div>
      );
    } catch {
      // 非合法 JSON,按 markdown 渲染
    }
  }
  return (
    <div className="ws-preview__markdown">
      <Markdown text={text} />
    </div>
  );
}

/** 把 payload 的原始值字段渲染为键值列表,内容字段走渲染器,复杂字段兜底 JSON。 */
function PayloadFields({ payload }: { payload: Record<string, any> }) {
  const { contents, primitives, complex } = useMemo(() => {
    const contents: Array<[string, string]> = [];
    const primitives: Array<[string, string]> = [];
    const complex: Array<[string, string]> = [];
    Object.entries(payload || {}).forEach(([k, v]) => {
      if (v === null || v === undefined) return;
      if (typeof v === 'string' && CONTENT_KEYS.has(k) && v.trim().length > 0) {
        contents.push([k, v]);
      } else if (['string', 'number', 'boolean'].includes(typeof v)) {
        primitives.push([k, String(v)]);
      } else {
        complex.push([k, JSON.stringify(v, null, 2)]);
      }
    });
    return { contents, primitives, complex };
  }, [payload]);

  return (
    <div className="ws-preview__fields">
      {contents.map(([k, v]) => (
        <section key={k} className="ws-preview__section">
          <div className="ws-preview__section-title">{k}</div>
          <ContentView text={v} />
        </section>
      ))}
      {primitives.length > 0 && (
        <div className="ws-preview__kv">
          {primitives.map(([k, v]) => (
            <div key={k} className="ws-preview__field">
              <span className="ws-preview__field-key">{k}</span>
              <span className="ws-preview__field-value">{v}</span>
            </div>
          ))}
        </div>
      )}
      {complex.map(([k, v]) => (
        <div key={k} className="ws-preview__field ws-preview__field--block">
          <span className="ws-preview__field-key">{k}</span>
          <pre className="ws-preview__json">{v}</pre>
        </div>
      ))}
      {contents.length === 0 && primitives.length === 0 && complex.length === 0 && (
        <div className="ws-preview__empty">暂无详情数据</div>
      )}
    </div>
  );
}

/** artifact_produced 等只带 id 的事件:拉取 artifact 详情后渲染内容 */
function ArtifactPreview({ artifactId, title, type }: { artifactId: number; title?: string; type?: string }) {
  const { data: res, loading } = useRequest(
    async () => apiInterceptors(getArtifactInfo(artifactId)),
    { refreshDeps: [artifactId] },
  );
  const artifact = res?.[1];
  if (loading) return <Spin />;
  if (!artifact) return <div className="ws-preview__empty">交付物不存在或已删除</div>;
  const content = artifact.content_text || '';
  return (
    <div className="ws-preview">
      <div className="ws-preview__head">
        <span className="ws-preview__title">{artifact.title || title || `artifact_${artifactId}`}</span>
        {(artifact.type || type) && <Tag color="blue">{artifact.type || type}</Tag>}
        {artifact.current_version != null && <Tag>v{artifact.current_version}</Tag>}
      </div>
      {content ? (
        <section className="ws-preview__section">
          <div className="ws-preview__section-title">内容</div>
          <ContentView text={content} />
        </section>
      ) : (
        <PayloadFields payload={artifact} />
      )}
    </div>
  );
}

/** Agent 步骤(工具调用/思考)富预览 */
function StepPreview({ step }: { step: any }) {
  const payload = step?.payload || {};
  const output = typeof payload.output === 'string' ? payload.output : null;
  const actionInput = payload.action_input;
  return (
    <div className="ws-preview">
      <div className="ws-preview__head">
        <span className="ws-preview__title">{step?.title || '步骤详情'}</span>
        {payload.action && <Tag color="blue">{payload.action}</Tag>}
        {step?.status && <Tag color={STATUS_COLOR[step.status] || 'default'}>{step.status}</Tag>}
      </div>
      {actionInput && (
        <section className="ws-preview__section">
          <div className="ws-preview__section-title">输入参数</div>
          <pre className="ws-preview__json">{JSON.stringify(actionInput, null, 2)}</pre>
        </section>
      )}
      {output && (
        <section className="ws-preview__section">
          <div className="ws-preview__section-title">
            {payload.step_type === 'thinking' ? '内容' : '执行结果'}
          </div>
          <ContentView text={output} />
        </section>
      )}
      {!actionInput && !output && <PayloadFields payload={payload} />}
    </div>
  );
}

export function SceneSpace({
  context,
  previewItem,
  activeTask,
  workspaceId,
  workspaceCode,
  onBack,
  onSelectTask,
  onSelectArtifact,
}: SceneSpaceProps) {
  const taskId = context === 'task-detail' && previewItem?.id ? previewItem.id : undefined;
  const task = activeTask;

  const { data: artifactsRes } = useRequest(
    async () => (taskId ? apiInterceptors(listArtifacts({ task_id: taskId })) : null),
    { refreshDeps: [taskId] }
  );
  const artifacts = artifactsRes?.[1] || [];

  if (context === 'dashboard') {
    return (
      <div className="ws-scene-space ws-scene-space--dashboard">
        <Lobby
          workspaceId={workspaceId}
          workspaceCode={workspaceCode}
          onSelectTask={onSelectTask || (() => {})}
          onSelectArtifact={onSelectArtifact}
        />
      </div>
    );
  }

  const CONTEXT_TITLE: Record<string, string> = {
    'task-detail': '任务详情',
    'file-preview': '文件预览',
    'tool-result': '步骤详情',
    'entity-card': '实体信息',
  };

  return (
    <div className="ws-scene-space">
      <div className="ws-scene-space__header">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack} size="small" type="text">
          返回
        </Button>
        <span className="ws-scene-space__header-title">{CONTEXT_TITLE[context] || ''}</span>
      </div>
      {context === 'task-detail' && (
        <div className="ws-scene-space__body">
          {!task && <Spin />}
          {task && (
            <Card title={task.title || `Task ${task.id}`}>
              <p><Tag>{task.status}</Tag></p>
              <p>触发源: {task.triggered_by || '—'}</p>
              <p>创建时间: {task.created_at || '—'}</p>
              <p>更新时间: {task.updated_at || '—'}</p>
              {artifacts.length > 0 && (
                <div>
                  <strong>交付物:</strong>
                  {artifacts.map((a: any) => (
                    <div key={a.id}>{a.title || `artifact_${a.id}`} <Tag>{a.type}</Tag></div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
      {context === 'tool-result' && (
        <div className="ws-scene-space__body">
          <StepPreview step={previewItem} />
        </div>
      )}
      {context === 'file-preview' && (
        <div className="ws-scene-space__body">
          {previewItem?.payload?.artifact_id ? (
            <ArtifactPreview
              artifactId={previewItem.payload.artifact_id}
              title={previewItem.payload.title}
              type={previewItem.payload.type}
            />
          ) : (
            <div className="ws-preview">
              <div className="ws-preview__head">
                <span className="ws-preview__title">
                  {previewItem?.payload?.file_name || previewItem?.payload?.title || '文件预览'}
                </span>
              </div>
              <PayloadFields payload={previewItem?.payload || previewItem || {}} />
            </div>
          )}
        </div>
      )}
      {context === 'entity-card' && (
        <div className="ws-scene-space__body">
          {previewItem?.payload?.artifact_id ? (
            <ArtifactPreview
              artifactId={previewItem.payload.artifact_id}
              title={previewItem.payload.title}
              type={previewItem.payload.type}
            />
          ) : (
            <div className="ws-preview">
              <div className="ws-preview__head">
                <span className="ws-preview__title">实体信息</span>
              </div>
              <PayloadFields payload={previewItem?.payload || previewItem || {}} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
