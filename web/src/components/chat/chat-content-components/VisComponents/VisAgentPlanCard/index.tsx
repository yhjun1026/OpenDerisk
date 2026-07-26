import React, { useEffect, useState, useMemo } from 'react';
import { VisAgentPlanCardWrap } from './style';
import { GPTVis } from '@antv/gpt-vis';
import 'katex/dist/katex.min.css';
import {
  codeComponents,
  type MarkdownComponent,
  markdownPlugins,
} from '../../config';
import {
  CheckCircleOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  PauseCircleOutlined,
  SyncOutlined,
  UpOutlined,
  FlagFilled,
  DatabaseOutlined,
  CodeOutlined,
  GlobalOutlined,
  FileTextOutlined,
  ApiOutlined,
  SearchOutlined,
  CloudOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Tooltip } from 'antd';
import { ee, EVENTS } from '@/utils/event-emitter';
import { groupConsecutivePlanCards } from '@/utils/group-agent-plan-cards';

const StatusMap: Record<string, string> = {
  todo: '待执行',
  running: '执行中',
  waiting: '等待中',
  retrying: '重试中',
  failed: '失败',
  complete: '成功',
};

const getStatusText = (status: string): string =>
  StatusMap[status] ?? status ?? '成功';

const iconUrlMap: Record<string, string> = {
  report:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*xaTaQ5rDghgAAAAALTAAAAgAeprcAQ/original',
  tool: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  blankaction:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  knowledge:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*P2sCQKUZoAUAAAAAOhAAAAgAeprcAQ/original',
  code: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*pPozSIZ_0u4AAAAAO7AAAAgAeprcAQ/original',
  deriskcodeaction:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*pPozSIZ_0u4AAAAAO7AAAAgAeprcAQ/original',
  monitor:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*F4pAT4italwAAAAANhAAAAgAeprcAQ/original',
  agent: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*b_vFSpByHFcAAAAAQBAAAAgAeprcAQ/original',
  plan: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  planningaction:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  stage:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  llm: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*b_vFSpByHFcAAAAAQBAAAAgAeprcAQ/original',
  task: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  hidden: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  default: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
};

const taskTypeLabels: Record<string, string> = {
  tool: '工具调用',
  code: '代码执行',
  report: '报告生成',
  knowledge: '知识检索',
  monitor: '监控检查',
  agent: '智能体',
  plan: '计划规划',
  stage: '阶段任务',
  llm: 'LLM推理',
  task: '任务执行',
  blankaction: '空白操作',
  deriskcodeaction: '代码执行',
  planningaction: '规划动作',
  hidden: '隐藏任务',
  default: '任务',
};

const getTaskIcon = (taskType: string): string => {
  const normalizedType = String(taskType).toLowerCase();
  return iconUrlMap[normalizedType] || iconUrlMap.default;
};

/**
 * Map tool names to specific Ant Design icons for visual differentiation.
 * Returns a React node if a match is found, null otherwise (falls back to image icon).
 */
const toolNameIconMap: Array<{ keywords: string[]; icon: React.ReactNode; color: string; label: string }> = [
  { keywords: ['skill'], icon: <ThunderboltOutlined />, color: '#5d6577', label: '技能' },
  { keywords: ['sql', 'database', 'db_', 'mysql', 'postgres', 'sqlite', 'query', 'table_spec', 'table_info', 'schema', 'get_table'], icon: <DatabaseOutlined />, color: '#5d6577', label: 'SQL' },
  { keywords: ['shell', 'bash', 'terminal', 'command', 'exec_command', 'ssh'], icon: <CodeOutlined />, color: '#5d6577', label: '终端' },
  { keywords: ['browser', 'web', 'http', 'url', 'crawl', 'scrape', 'fetch_url'], icon: <GlobalOutlined />, color: '#5d6577', label: '浏览器' },
  { keywords: ['file', 'read_file', 'write_file', 'write', 'read', 'upload', 'download', 'document', 'csv', 'excel', 'pdf', 'save', 'mkdir', 'copy', 'move', 'rename', 'delete_file'], icon: <FileTextOutlined />, color: '#5d6577', label: '文件' },
  { keywords: ['api', 'rest', 'graphql', 'endpoint'], icon: <ApiOutlined />, color: '#5d6577', label: 'API' },
  { keywords: ['search', 'retrieve', 'lookup', 'find'], icon: <SearchOutlined />, color: '#5d6577', label: '搜索' },
  { keywords: ['cloud', 'deploy', 'server', 'container', 'docker'], icon: <CloudOutlined />, color: '#5d6577', label: '云服务' },
];

export const getToolNameIcon = (toolName?: string, title?: string): { icon: React.ReactNode; color: string; label: string } | null => {
  if (!toolName && !title) return null;
  const text = `${toolName || ''} ${title || ''}`.toLowerCase();
  for (const entry of toolNameIconMap) {
    if (entry.keywords.some((kw) => text.includes(kw))) {
      return entry;
    }
  }
  return null;
};

/**
 * Format raw tool-call args (usually a JSON string) into a concise, readable
 * summary for the task row — raw JSON with braces/quotes is noise in the UI.
 * The FIRST value is treated as the primary argument (path/db_name/command...)
 * and is always shown (truncated if long); a second short value may follow.
 */
export const formatArgsSummary = (raw: string): string => {
  const trimmed = raw.trim();
  if (!trimmed.startsWith('{')) return trimmed;
  let values: string[] = [];
  try {
    const obj = JSON.parse(trimmed);
    values = Object.values(obj)
      .filter((v): v is string | number => typeof v === 'string' || typeof v === 'number')
      .map(String);
  } catch {
    // Truncated JSON (streaming) — pull out the complete "key": "value" pairs
    values = [...trimmed.matchAll(/"[^"]+"\s*:\s*"([^"]*)"/g)].map((m) => m[1]);
  }
  const parts = values.map((s) => s.replace(/\s+/g, ' ').trim()).filter(Boolean);
  if (parts.length === 0) return '';
  // 主参数优先取第一个"非纯数字"的值(path/db_name/command 等),
  // 纯数字通常是 limit/offset/timeout 之类的修饰参数,不适合做主显示
  const primaryRaw = parts.find((s) => !/^\d+(\.\d+)?$/.test(s)) ?? parts[0];
  const primary = primaryRaw.length <= 48 ? primaryRaw : `${primaryRaw.slice(0, 48)}…`;
  const secondary = parts.find((s) => s !== primaryRaw && s.length <= 24);
  return secondary ? `${primary} · ${secondary}` : primary;
};

const getTaskLabel = (taskType: string): string => {
  const normalizedType = String(taskType).toLowerCase();
  return taskTypeLabels[normalizedType] || taskType;
};

const IconMap = {
  complete: <CheckCircleOutlined style={{ color: '#22c55e', fontSize: 12 }} />,
  todo: <CheckCircleOutlined style={{ color: '#b4bac8', fontSize: 12 }} />,
  running: <LoadingOutlined style={{ color: '#4f46e5', fontSize: 12 }} />,
  waiting: <PauseCircleOutlined style={{ color: '#f59e0b', fontSize: 12 }} />,
  retrying: <SyncOutlined style={{ color: '#f59e0b', fontSize: 12 }} />,
  failed: (
    <ExclamationCircleOutlined style={{ color: '#ef4444', fontSize: 12 }} />
  ),
};

interface IProps {
  otherComponents?: MarkdownComponent;
  data: Record<string, unknown>;
}

const VisAgentPlanCard: React.FC<IProps> = ({ otherComponents, data }) => {
  const [expanded, setExpanded] = useState((data.expand as boolean) ?? true);
  const [isSelected, setIsSelected] = useState(false);
  const [dynamicCost, setDynamicCost] = useState(
    (data?.cost as number) ?? 0,
  );

  const taskUid = useMemo(() => {
    return (data?.uid as string) || (data?.task_id as string) || '';
  }, [data?.uid, data?.task_id]);

  const toggleExpand = () => {
    setExpanded((prev) => !prev);
  };

  const formatTime = (timeStr: string) => {
    if (!timeStr) return '';
    try {
      const date = new Date(timeStr);
      if (Number.isNaN(date.getTime())) return timeStr;
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      const seconds = String(date.getSeconds()).padStart(2, '0');
      return `${hours}:${minutes}:${seconds}`;
    } catch {
      return timeStr;
    }
  };

  useEffect(() => {
    if (data.expand !== undefined) {
      setExpanded(Boolean(data.expand));
    }
  }, [data.expand]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    if (
      (data?.cost as number) === 0 &&
      (data?.status as string) === 'running'
    ) {
      setDynamicCost(0);
      interval = setInterval(() => {
        setDynamicCost((prev) => prev + 1);
      }, 1000);
    } else {
      setDynamicCost((data?.cost as number) ?? 0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [data?.cost, data?.status]);

  useEffect(() => {
    const handler = (payload: { uid?: string }) => {
      const matched = payload?.uid === taskUid;
      if (matched) setIsSelected(true);
      else setIsSelected(false);
    };
    ee.on(EVENTS.CLICK_FOLDER, handler);
    return () => {
      ee.off(EVENTS.CLICK_FOLDER, handler);
    };
  }, [taskUid]);

  const hasChildren =
    data?.markdown ||
    (Array.isArray(data?.children) && (data.children as unknown[]).length > 0);
  const isReport = data?.task_type === 'report';
  const isPlan = data?.item_type === 'plan';
  const isTask = data?.item_type === 'task';
  const isAgent = data?.item_type === 'agent';
  const isStage = data?.item_type === 'stage';
  const layerCount = (data?.layer_count as number) ?? 0;

  const markdownContent = useMemo(() => {
    if (!expanded || !data?.markdown) return null;
    return (
      <div
        className={`markdown-content-wrap ${isStage ? 'markdown-content-wrap-stage' : ''}`}
      >
        {/* @ts-expect-error GPTVis + markdownPlugins spread */}
        <GPTVis
          components={{ ...codeComponents, ...(otherComponents ?? {}) }}
          {...markdownPlugins}
        >
          {/* 嵌套 markdown 里相邻的同工具步骤同样做聚合(纯展示层变换) */}
          {groupConsecutivePlanCards(String(data.markdown))}
        </GPTVis>
      </div>
    );
  }, [expanded, data?.markdown, isStage, otherComponents]);

  return (
    <VisAgentPlanCardWrap
      onClick={(e: React.MouseEvent) => {
        e.stopPropagation();
        if (taskUid) {
          ee.emit(EVENTS.CLICK_FOLDER, {
            uid: taskUid,
          });
          ee.emit(EVENTS.OPEN_PANEL);
        }
      }}
      className={`VisAgentPlanCardClass level-${layerCount} ${isSelected ? 'selected' : ''}`}
    >
      <div
        className={`header ${isPlan ? 'header-plan' : ''} ${isTask ? 'header-task' : ''} ${isAgent ? 'header-agent' : ''} ${isStage ? 'header-stage' : ''} ${!isPlan && !isTask && !isAgent && !isStage ? 'header-default' : ''}`}
        onClick={toggleExpand}
      >
        <div className="content-wrapper">
          <div className="header-row">
            <div className="content-header">
              {Boolean(data?.agent_name) && !isStage && (
                <div className={`agent_name ${isAgent ? 'agent_name-leading' : ''}`} title={String(data.agent_name)}>
                  {!isPlan && !isAgent && (
                    <Avatar
                      size={20}
                      src={data.agent_avatar as string}
                      className="avatar-shrink"
                    />
                  )}
                  <div className="agent_name-badge">
                    <Tooltip title={String(data.agent_name)}>
                      {String(data.agent_name)}
                    </Tooltip>
                  </div>
                </div>
              )}
              {(isTask || isStage) && (
                isStage ? (
                  <div className="task-icon stage-icon-wrapper">
                     <FlagFilled style={{ color: '#4f46e5', fontSize: 14 }} />
                  </div>
                ) : (() => {
                  const toolMeta = getToolNameIcon(data?.tool_name as string, data?.title as string);
                  return toolMeta ? (
                    <Tooltip title={toolMeta.label}>
                      <span
                        className="task-icon-chip"
                        style={{ backgroundColor: `${toolMeta.color}14`, color: toolMeta.color }}
                      >
                        {React.cloneElement(toolMeta.icon as React.ReactElement, { style: { fontSize: 11 } })}
                      </span>
                    </Tooltip>
                  ) : (
                    <Tooltip title={getTaskLabel(String(data?.task_type))}>
                      <span className="task-icon-chip task-icon-chip-default">
                        <img
                          className="task-icon"
                          src={getTaskIcon(String(data?.task_type))}
                          alt={getTaskLabel(String(data?.task_type))}
                        />
                      </span>
                    </Tooltip>
                  );
                })()
              )}
              {!isAgent && (
                <div
                  className={`title title-text title-level-${layerCount} ${isTask ? 'title-task-with-markdown' : ''}`}
                >
                  <div className="title-flex-container">
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        flex: '1 1 0%', // 强制flex容器在溢出时优先压缩自己，不依赖内容宽度
                        minWidth: 0,
                        overflow: 'hidden',
                      }}
                    >
                      {isTask && data?.description != null ? (
                        <span className="task-title-line" title={`${data?.title ?? '未命名任务'} ${String(data.description)}`}>
                          <span className="task-title-name">{String(data?.title ?? '未命名任务')}</span>
                          {formatArgsSummary(String(data.description)) && (
                            <span className="task-args-summary">{formatArgsSummary(String(data.description))}</span>
                          )}
                        </span>
                      ) : (
                        <span className="title-text-ellipsis">
                          <Tooltip title={String(data?.title ?? '未命名任务')}>
                            {String(data?.title ?? '未命名任务')}
                          </Tooltip>
                        </span>
                      )}
                      {hasChildren && !isReport && (
                        <Button
                          type="text"
                          size="small"
                          icon={expanded ? <UpOutlined /> : <DownOutlined />}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleExpand();
                          }}
                          className={`expand-btn ${expanded ? 'expanded' : 'collapsed'} button-shrink`}
                        />
                      )}
                    </div>
                    {isTask || isStage ? (
                      <span
                        className="button-shrink"
                        style={{ marginLeft: 8 }}
                      >
                        {
                          IconMap[
                            (data?.status as keyof typeof IconMap) ?? 'running'
                          ]
                        }
                      </span>
                    ) : (
                      <span className="status status-badge">
                        {getStatusText((data?.status as string) ?? '')}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="flex-container">
            {Boolean(data?.description) && layerCount < 2 && !isAgent && !isTask && (
              <div
                className={`task-description ${layerCount === 0 ? 'task-description-level-0' : 'task-description-level-other'} task-description-container`}
              >
                <Tooltip title={String(data.description)}>
                  {String(data.description)}
                </Tooltip>
              </div>
            )}
            {isPlan && (
              <div className="time-info">
                <div>{formatTime((data?.start_time as string) ?? '')}</div>
                <div className="time-cost">{dynamicCost} s</div>
              </div>
            )}
          </div>
        </div>
      </div>
      {markdownContent}
    </VisAgentPlanCardWrap>
  );
};

export default React.memo(VisAgentPlanCard);
