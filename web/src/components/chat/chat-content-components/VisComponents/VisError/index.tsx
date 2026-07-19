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

export default VisError;
