import markdownComponents, {
  markdownPlugins,
  preprocessLaTeX,
} from "@/components/chat/chat-content-components/config";
import { ChatContentContext } from "@/contexts";
import { CompactChatContext } from "@/contexts/chat-content-context";
import { IChatDialogueMessageSchema } from "@/types/chat";
import { STORAGE_USERINFO_KEY } from "@/utils/constants/storage";
import { groupConsecutivePlanCards } from "@/utils/group-agent-plan-cards";
import VisSegmentedMarkdown from "@/components/chat/chat-content-components/VisSegmentedMarkdown";
import {
  CheckOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { GPTVis } from "@antv/gpt-vis";
import { Avatar } from "antd";
import classNames from "classnames";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import React, { memo, useContext, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { transformFileUrl } from "@/utils";

const UserIcon: React.FC = () => {
  const [user, setUser] = React.useState<any>({});

  React.useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_USERINFO_KEY);
      if (stored) {
        setUser(JSON.parse(stored));
      }
    } catch (e) {
      console.error(e);
    }
  }, []);

  return (
    <Avatar
      src={user?.avatar_url || undefined}
      className="bg-gradient-to-tr from-[#31afff] to-[#1677ff] cursor-pointer shrink-0"
      size={32}
    >
      {user?.nick_name?.charAt(0) || "U"}
    </Avatar>
  );
};

const AgentIcon: React.FC = () => {
  const { appInfo } = useContext(ChatContentContext);
  
  return (
    <Avatar
      src={appInfo?.icon || undefined}
      className="bg-gradient-to-tr from-[#52c41a] to-[#389e0d] cursor-pointer shrink-0"
      size={32}
    >
      {appInfo?.app_name?.charAt(0) || 'A'}
    </Avatar>
  );
};

type DBGPTView = {
  name: string;
  status: "todo" | "runing" | "failed" | "completed" | (string & {});
  result?: string;
  err_msg?: string;
};

type MarkdownComponent = Parameters<typeof GPTVis>["0"]["components"];

const pluginViewStatusMapper: Record<
  DBGPTView["status"],
  { bgClass: string; icon: React.ReactNode }
> = {
  todo: {
    bgClass: "bg-gray-500",
    icon: <ClockCircleOutlined className="ml-2" />,
  },
  runing: {
    bgClass: "bg-blue-500",
    icon: <LoadingOutlined className="ml-2" />,
  },
  failed: {
    bgClass: "bg-red-500",
    icon: <CloseOutlined className="ml-2" />,
  },
  completed: {
    bgClass: "bg-green-500",
    icon: <CheckOutlined className="ml-2" />,
  },
};

const formatMarkdownVal = (val: string) => {
  return val
    .replaceAll("\\n", "\n")
    .replace(/<table(\w*=[^>]+)>/gi, "<table $1>")
    .replace(/<tr(\w*=[^>]+)>/gi, "<tr $1>");
};

const formatMarkdownValForAgent = (val: string) => {
  return val
    ?.replace(/<table(\w*=[^>]+)>/gi, "<table $1>")
    .replace(/<tr(\w*=[^>]+)>/gi, "<tr $1>");
};

function getRobotContext(context: string): { left: string; right: string } {
  try {
    const robotContext = JSON.parse(context);
    return robotContext;
  } catch (e: unknown) {
    // console.log(e);
    return {
      left: "",
      right: "",
    };
  }
}

const ChatContent: React.FC<{
  content: Omit<IChatDialogueMessageSchema, "context"> & {
    context:
      | string
      | {
          template_name: string;
          template_introduce: string;
        };
  };
  onLinkClick?: () => void;
  messages: any[];
  compact?: boolean;
}> = ({ content, onLinkClick, messages, compact }) => {
  const { t } = useTranslation();
  const { context, role, thinking } = content;
  const isRobot = useMemo(() => role === "view", [role]);

  const { value, cachePluginContext } = useMemo<{
    relations: string[];
    value: string;
    cachePluginContext: DBGPTView[];
  }>(() => {
    if (typeof context !== "string") {
      return {
        relations: [],
        value: "",
        cachePluginContext: [],
      };
    }
    const [value, relation] = context.split("\trelations:");
    const relations = relation ? relation.split(",") : [];
    const cachePluginContext: DBGPTView[] = [];

    let cacheIndex = 0;
    const result = value.replace(
      /<dbgpt-view[^>]*>[^<]*<\/dbgpt-view>/gi,
      (matchVal) => {
        try {
          const pluginVal = matchVal
            .replaceAll("\n", "\\n")
            .replace(/<[^>]*>|<\/[^>]*>/gm, "");
          const pluginContext = JSON.parse(pluginVal) as DBGPTView;
          const replacement = `<custom-view>${cacheIndex}</custom-view>`;

          cachePluginContext.push({
            ...pluginContext,
            result: formatMarkdownVal(pluginContext.result ?? ""),
          });
          cacheIndex++;

          return replacement;
        } catch (e) {
          console.error(e);
          return matchVal;
        }
      }
    );
    return {
      relations,
      cachePluginContext,
      value: result,
    };
  }, [context]);

  const extraMarkdownComponents = useMemo<MarkdownComponent>(
    () => ({
      "custom-view"({ children }) {
        const index = +children.toString();
        if (!cachePluginContext[index]) {
          return children;
        }
        const { name, status, err_msg, result } = cachePluginContext[index];

        const { bgClass, icon } = pluginViewStatusMapper[status] ?? {};
        return (
          <div className="bg-white dark:bg-[#212121] rounded-lg overflow-hidden my-2 flex flex-col lg:max-w-[80%]">
            <div
              className={classNames(
                "flex px-4 md:px-6 py-2 items-center text-white text-sm",
                bgClass
              )}
            >
              {name}
              {icon}
            </div>
            {result ? (
              <div className="px-4 md:px-6 py-4 text-sm">
                {/* @ts-ignore */}
                <GPTVis components={markdownComponents} {...markdownPlugins}>
                  {preprocessLaTeX(result ?? "")}
                </GPTVis>
              </div>
            ) : (
              <div className="px-4 md:px-6 py-4 text-sm">{err_msg}</div>
            )}
          </div>
        );
      },
    }),
    [cachePluginContext]
  );

  const MAX_CONTEXT_PARSE_SIZE = 10_000_000; // 10MB limit for JSON parsing

  const _context = useMemo(() => {
    if (typeof value === 'string' && value.trim().startsWith('{')) {
      // Size check: skip parsing if context is too large
      if (value.length > MAX_CONTEXT_PARSE_SIZE) {
        console.warn(`[ChatContent] Context too large (${value.length} chars), returning raw value`);
        return value;
      }
      try {
        const parsed = JSON.parse(value);
        // 检查 planning_window 字段是否存在（即使为空字符串也应该使用它，
        // 因为这意味着这是一个多窗口布局的数据格式）
        if ('planning_window' in parsed) {
          let pw = parsed.planning_window || '';
          // Strip trailing plain text after the last VIS tag block to avoid
          // duplicate rendering (vis_final may append a conclusion that already
          // appears in the structured VIS component or right-panel summary).
          if (pw.includes('```manus-left-panel') || pw.includes('```manus-right-panel')) {
            const lastVisClose = pw.lastIndexOf('\n```');
            if (lastVisClose > 0) {
              const afterClose = lastVisClose + 4; // length of '\n```'
              const trailing = pw.substring(afterClose).trim();
              if (trailing) {
                pw = pw.substring(0, afterClose);
              }
            }
          }
          // Collapse excessive blank lines that produce empty paragraphs and
          // make the compact Manus left panel feel too sparse. Skip code blocks
          // so their internal formatting is preserved.
          const codeBlocks: string[] = [];
          pw = pw.replace(/(```[\s\S]*?```)/g, (match) => {
            codeBlocks.push(match);
            return '__MANUS_CODE_BLOCK_' + (codeBlocks.length - 1) + '__';
          });
          pw = pw.replace(/\n{3,}/g, '\n\n');
          pw = pw.replace(/__MANUS_CODE_BLOCK_(\d+)__/g, (_, index) => codeBlocks[parseInt(index)]);
          // 把相邻的同工具步骤围栏聚合成一个分组卡片(纯展示层变换,
          // 不影响上游 VisParser 的 uid 增量合并)。
          pw = groupConsecutivePlanCards(pw);
          return pw;
        }
        if (parsed?.vis) {
          const visData = typeof parsed.vis === 'string' ? JSON.parse(parsed.vis) : parsed.vis;
          if ('planning_window' in visData) {
            return groupConsecutivePlanCards(visData.planning_window || '');
          }
        }
      } catch {
      }
    }
    return value;
  }, [value]);

  return (
    <>
      {!isRobot && (
        <div className='flex flex-1 justify-end items-start pb-4 pt-6' style={{ gap: 12 }}>
          <span
            className='break-words min-w-0'
            style={{
              maxWidth: '95%',
              minWidth: 0,
            }}
          >
            {typeof context === 'string' ? (
              <div
                className='flex-1 text-sm text-[#1c2533] dark:text-white'
                style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
              >
                {typeof context === 'string' && (
                  <div>
                    {/* @ts-ignore */}
                    <GPTVis
                      components={{
                        ...markdownComponents,
                        // @ts-ignore
                        img: ({ src, alt, ...props }) => (
                          <img
                            src={transformFileUrl(src || '')}
                            alt={alt || 'image'}
                            className='max-w-full md:max-w-[80%] lg:max-w-[70%] object-contain'
                            style={{ maxHeight: '200px' }}
                            {...props}
                          />
                        ),
                        
                      }}
                      {...markdownPlugins}
                    >
                      {preprocessLaTeX(formatMarkdownVal(value))}
                    </GPTVis>
                  </div>
                )}
              </div>
            ) : (
              context?.template_introduce || ''
            )}
          </span>
          <UserIcon />
        </div>
      )}
      {isRobot && (
        <div className={classNames('flex flex-1 justify-start items-start', compact ? 'pb-1 pt-1.5' : 'pb-4 pt-6')} style={{ gap: 12 }}>
          <AgentIcon />
          <div className='flex flex-col flex-1 min-w-0 border-dashed border-r0 overflow-x-auto compact-markdown-container'>
            {/* @ts-ignore */}
            <CompactChatContext.Provider value={!!compact}>
              <style dangerouslySetInnerHTML={{ __html: `
                /* react-markdown 把每个 vis 代码块(agent-plans / agent-messages /
                   VisContentCard 等)各包成一个 <pre>,作为 .markdown-content-wrap 的直接
                   子节点纵向堆叠。
                   实测:pre 自身 margin 已清零、pre 之间也查不到中间节点,但空白仍定位在
                   markdown-content-wrap 这个父容器上——根因是父容器的 line-height / 残留
                   padding / inline 空白文本节点把相邻 <pre> 撑开。
                   彻底治理:用 :has(> pre) 只命中"直接子级是 <pre>"的那份外层 .markdown-content-wrap
                   (VisAgentPlanCard 内部展开用的同名包裹其直接子级是 <div>/GPTVis 输出而非 <pre>,
                   不会被命中),把它变成 column flex + gap:0 + line-height:0,子项再恢复 line-height。
                   必须无条件注入:BasicChatContent 等非 compact 路径同样受影响。 */
                .markdown-content-wrap:has(> pre) {
                  display: flex;
                  flex-direction: column;
                  gap: 0;
                  line-height: 0;
                  padding: 0 !important;
                }
                .markdown-content-wrap:has(> pre) > * {
                  margin-top: 0 !important;
                  margin-bottom: 0 !important;
                  line-height: normal; /* 还原子项正常行高 */
                }
                .markdown-content-wrap:has(> pre) > p:empty {
                  display: none !important; /* fence 间空行产生的空段落,0 高度 */
                }
                /* 审美间距:文本卡片(VisContentCard)与 task 卡片之间贴齐(0px),
                   仅相邻两个都是 task(VisAgentPlanCard)时,后者向下推开 8px,
                   形成任务流内的分组呼吸感,而非所有卡片一刀切。用 + 前驱兄弟选择器
                   精确命中"前一个 pre 内是 task 卡片"的连续 task。 */
                .markdown-content-wrap:has(> pre) > pre:has(> .VisAgentPlanCardClass) + pre:has(> .VisAgentPlanCardClass) {
                  margin-top: 8px !important;
                }
                /* 分段渲染(VisSegmentedMarkdown)下等价的 task-task 间距 */
                .vis-fence-segment:has(> .VisAgentPlanCardClass) + .vis-fence-segment:has(> .VisAgentPlanCardClass) {
                  margin-top: 8px;
                }
                .vis-fence-segment {
                  line-height: normal;
                }
                .compact-markdown-container pre {
                  padding: 0 !important;
                  margin: 0 !important;
                  background: transparent !important;
                  font-size: 100% !important;
                }
              `}} />
              {/* 组件级局部渲染:vis 围栏按 uid 挂载,只有变化的组件重渲染 */}
              <VisSegmentedMarkdown
                content={preprocessLaTeX(formatMarkdownValForAgent(_context))}
                components={{
                  ...markdownComponents,
                  ...extraMarkdownComponents,
                }}
              />
            </CompactChatContext.Provider>
            {thinking && !context && (
              <div className='flex items-center gap-2'>
                <span className='flex text-sm text-[#1c2533] dark:text-white'>{t('thinking')}</span>
                <div className='flex'>
                  <div className='w-1 h-1 rounded-full mx-1 animate-pulse1'></div>
                  <div className='w-1 h-1 rounded-full mx-1 animate-pulse2'></div>
                  <div className='w-1 h-1 rounded-full mx-1 animate-pulse3'></div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default memo(ChatContent);
