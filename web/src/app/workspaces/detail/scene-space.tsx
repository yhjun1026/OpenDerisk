'use client';

import { useMemo } from 'react';
import { Button, Spin, Tag } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { GPTVis } from '@antv/gpt-vis';
import dayjs from 'dayjs';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import { apiInterceptors, getArtifactInfo, listArtifacts, listDeliveries, listUsageCalls } from '@/client/api';
import { Lobby } from './lobby';
import { AgentWorkspaceRenderer } from './agent-workspace-renderer';
import { parseWorkspaceView } from './parse-workspace-view';
import { parseSceneAgentWorkspaceString } from './parse-scene-agent-workspace-string';
import { statusLabel, triggerLabel } from './scene-task-rail';
import type { WorkspaceView } from './agent-workspace-types';
import type { DetailContext } from './agent-types';

export interface SceneSpaceProps {
  context: DetailContext;
  previewItem?: any;
  activeTask?: any;
  workspaceId: number;
  workspaceCode: string;
  playbooks?: { playbook_id: number; playbook_name: string }[];
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

const DELIVERY_STATUS_COLOR: Record<string, string> = {
  sent: 'success',
  failed: 'error',
  pending: 'default',
};

function fmtTime(v?: string | null): string {
  return v ? dayjs(v).format('MM-DD HH:mm') : '—';
}

function fmtSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="ws-preview__field">
      <span className="ws-preview__field-key">{k}</span>
      <span className="ws-preview__field-value">{v}</span>
    </div>
  );
}

/** 任务详情:基本信息(触发/剧本/时间) + 产物 + 交付 + 消耗 */
function TaskDetail({
  task,
  playbookName,
  artifacts,
  deliveries,
  usage,
  onSelectArtifact,
}: {
  task: any;
  playbookName?: string | null;
  artifacts: any[];
  deliveries: any[];
  usage: { calls: number; tokens: number; cost: number } | null;
  onSelectArtifact?: (a: any) => void;
}) {
  return (
    <div className="ws-preview">
      <div className="ws-preview__head">
        <span className="ws-preview__title">{task.title || `Task ${task.id}`}</span>
        <Tag color={STATUS_COLOR[task.status] || 'default'}>{statusLabel(task.status)}</Tag>
      </div>
      {task.description && (
        <section className="ws-preview__section">
          <div className="ws-preview__section-title">描述</div>
          <div className="ws-preview__markdown">{task.description}</div>
        </section>
      )}
      <section className="ws-preview__section">
        <div className="ws-preview__section-title">基本信息</div>
        <div>
          <KV k="触发" v={`${triggerLabel(task)}${task.trigger_ref ? ` · ${task.trigger_ref}` : ''}`} />
          <KV k="剧本" v={playbookName || (task.playbook_id ? `playbook_${task.playbook_id}` : '—')} />
          <KV k="类型" v={task.type || 'adhoc'} />
          <KV k="创建时间" v={fmtTime(task.gmt_created)} />
          <KV k="更新时间" v={fmtTime(task.gmt_modified)} />
          <KV k="开始时间" v={fmtTime(task.started_at)} />
          <KV k="关闭时间" v={fmtTime(task.closed_at)} />
        </div>
      </section>
      <section className="ws-preview__section">
        <div className="ws-preview__section-title">产出 ({artifacts.length})</div>
        {artifacts.length === 0 && <div className="ws-preview__empty">暂无产出</div>}
        {/* 最终答复:最终发送给 Human 的 message 内容,直接渲染 */}
        {artifacts.filter((a: any) => a.type === 'final_message').map((a: any) => (
          <div key={a.id} className="ws-preview__markdown" style={{ marginBottom: 12 }}>
            {a.content_text ? <Markdown text={a.content_text} /> : <div className="ws-preview__empty">(无内容)</div>}
          </div>
        ))}
        {/* 产出文件:运行期间标记的交付文件,点击打开文件链接 */}
        {artifacts.filter((a: any) => a.type === 'file').map((a: any) => (
          <div
            key={a.id}
            className="ws-preview__field ws-td-link"
            role="button"
            tabIndex={0}
            onClick={() => (a.content_ref ? window.open(a.content_ref, '_blank') : onSelectArtifact?.(a))}
            onKeyDown={(e) => { if (e.key === 'Enter') (a.content_ref ? window.open(a.content_ref, '_blank') : onSelectArtifact?.(a)); }}
          >
            <span className="ws-preview__field-value">{a.title || `artifact_${a.id}`}</span>
            <Tag color="blue">文件</Tag>
            {a.provenance?.file_size ? (
              <span className="ws-preview__field-key">{fmtSize(a.provenance.file_size)}</span>
            ) : null}
          </div>
        ))}
        {/* 其他类型(历史数据 report/alert 等):保持原有点击查看 */}
        {artifacts.filter((a: any) => a.type !== 'final_message' && a.type !== 'file').map((a: any) => (
          <div
            key={a.id}
            className="ws-preview__field ws-td-link"
            role="button"
            tabIndex={0}
            onClick={() => onSelectArtifact?.(a)}
            onKeyDown={(e) => { if (e.key === 'Enter') onSelectArtifact?.(a); }}
          >
            <span className="ws-preview__field-value">{a.title || `artifact_${a.id}`}</span>
            <Tag>{a.type}</Tag>
          </div>
        ))}
      </section>
      <section className="ws-preview__section">
        <div className="ws-preview__section-title">交付 ({deliveries.length})</div>
        {deliveries.length === 0 && <div className="ws-preview__empty">暂无交付记录</div>}
        {deliveries.map((d: any) => (
          <div key={d.id} className="ws-preview__field">
            <span className="ws-preview__field-value">{d.title || `delivery_${d.id}`}</span>
            <Tag>{d.channel}</Tag>
            <Tag color={DELIVERY_STATUS_COLOR[d.status] || 'default'}>{d.status}</Tag>
            <span className="ws-preview__field-key">{fmtTime(d.sent_at || d.gmt_created)}</span>
          </div>
        ))}
      </section>
      <section className="ws-preview__section">
        <div className="ws-preview__section-title">消耗</div>
        {usage ? (
          <div>
            <KV k="调用次数" v={String(usage.calls)} />
            <KV k="Tokens" v={usage.tokens.toLocaleString()} />
            <KV k="费用" v={`$${usage.cost.toFixed(4)}`} />
          </div>
        ) : (
          <div className="ws-preview__empty">暂无调用记录</div>
        )}
      </section>
    </div>
  );
}

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

/** 历史脏数据兜底:vis_final 协议帧曾被错存为交付物内容,识别后走 workspace 渲染而非 raw JSON。 */
function tryParseVisWorkspaceView(text: string): WorkspaceView | null {
  if (!text.includes('scene_agent_workspace')) return null;
  const parsed = parseSceneAgentWorkspaceString(text);
  if (!parsed || !Array.isArray(parsed.execution)) return null;
  return parseWorkspaceView(parsed, null);
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
  const visView = tryParseVisWorkspaceView(text);
  if (visView) {
    return <AgentWorkspaceRenderer view={visView} />;
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
  const fileUrl = artifact.content_ref || '';
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
      ) : fileUrl ? (
        <section className="ws-preview__section">
          <div className="ws-preview__section-title">文件</div>
          {artifact.provenance?.description && (
            <div className="ws-preview__markdown" style={{ marginBottom: 8 }}>{artifact.provenance.description}</div>
          )}
          <Button type="primary" onClick={() => window.open(fileUrl, '_blank')}>
            打开 / 下载文件
          </Button>
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
  playbooks,
  onBack,
  onSelectTask,
  onSelectArtifact,
}: SceneSpaceProps) {
  const taskId = context === 'task-detail' && previewItem?.id ? previewItem.id : undefined;
  // 点击任务卡片走 handlePreview(不进任务对话),activeTask 不会被填充;
  // 用列表已有的 previewItem 兜底,否则 Spin 永不结束
  const task = activeTask || (context === 'task-detail' ? previewItem : undefined);

  const { data: artifactsRes } = useRequest(
    async () => (taskId ? apiInterceptors(listArtifacts({ task_id: taskId })) : null),
    { refreshDeps: [taskId] }
  );
  const artifacts = artifactsRes?.[1] || [];

  const { data: deliveriesRes } = useRequest(
    async () => (taskId ? apiInterceptors(listDeliveries({ workspace_id: workspaceId, task_id: taskId })) : null),
    { refreshDeps: [taskId, workspaceId] }
  );
  const deliveries = deliveriesRes?.[1] || [];

  const convSessionId = task?.conv_session_id;
  const { data: usageRes } = useRequest(
    async () => (convSessionId ? apiInterceptors(listUsageCalls({ conv_id: convSessionId, page_size: 200 })) : null),
    { refreshDeps: [convSessionId] }
  );
  const usage = useMemo(() => {
    const items: any[] = usageRes?.[1]?.items || [];
    if (!items.length) return null;
    return {
      calls: usageRes?.[1]?.total_count ?? items.length,
      tokens: items.reduce((s, c) => s + (c.total_tokens || 0), 0),
      cost: items.reduce((s, c) => s + (c.cost_usd || 0), 0),
    };
  }, [usageRes]);

  const playbookName = useMemo(
    () => playbooks?.find((p) => p.playbook_id === task?.playbook_id)?.playbook_name || null,
    [playbooks, task?.playbook_id],
  );

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
            <TaskDetail
              task={task}
              playbookName={playbookName}
              artifacts={artifacts}
              deliveries={deliveries}
              usage={usage}
              onSelectArtifact={onSelectArtifact}
            />
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
