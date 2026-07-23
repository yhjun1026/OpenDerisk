import { Alert } from 'antd';
import React from 'react';

interface VisErrorData {
  title?: string;
  content?: string;
}

interface IProps {
  data?: VisErrorData;
}

/**
 * 对话运行中断时的错误卡片:已流式产出的内容正常保留,
 * 该卡片追加在内容末尾展示错误原因。
 */
const VisError: React.FC<IProps> = ({ data }) => {
  return (
    <Alert
      className='my-2'
      type='error'
      showIcon
      message={data?.title || '对话发生错误'}
      {...(data?.content && data.content !== (data?.title || '对话发生错误')
        ? { description: data.content }
        : {})}
    />
  );
};

/**
 * 生成 d-error vis 围栏 markdown,追加到已流式内容末尾。
 */
export function buildVisErrorMarkdown(reason: string): string {
  const data: VisErrorData = { content: reason || '对话发生错误，请稍后重试' };
  return `\n\n\`\`\`d-error\n${JSON.stringify(data)}\n\`\`\``;
}

/**
 * 将错误卡片注入到 context 末尾,兼容两种消息布局:
 * - manus/incremental 布局:context 是 final_view JSON
 *   ({planning_window, running_window, meta_window})。此时若直接把 d-error
 *   围栏追加到 JSON 字符串末尾会破坏 JSON 结构,导致左面板 planning_window
 *   解析失败降级成一大坨 raw JSON 文本、右面板 running_window 因 JSON.parse
 *   失败而丢失。故这里把 d-error 围栏注入 planning_window 字段末尾,保持
 *   JSON 结构完整。
 * - 其他布局:context 是围栏 markdown,直接追加到末尾。
 * JSON.parse 失败时回退到直接追加,不比现状差。
 */
export function appendErrorToContext(context: string, reason: string): string {
  const errorMd = buildVisErrorMarkdown(reason);
  const base = context || '';
  if (base.trim().startsWith('{')) {
    try {
      const parsed = JSON.parse(base);
      if (parsed && typeof parsed === 'object' && 'planning_window' in parsed) {
        parsed.planning_window = (parsed.planning_window || '') + errorMd;
        return JSON.stringify(parsed);
      }
    } catch {
      // 非有效 JSON,回退到末尾追加
    }
  }
  return base + errorMd;
}

export default VisError;
