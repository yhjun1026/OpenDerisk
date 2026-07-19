'use client';

import React, { memo, useMemo } from 'react';
import { GPTVis } from '@antv/gpt-vis';
import markdownComponents, { markdownPlugins } from './config';
import { splitVisFences } from '@/utils/split-vis-fences';

const CodeBlock: any = (markdownComponents as any).code;

/**
 * 单个 vis 围栏段 — 以 uid 为 key 挂载,memo 到 body 级别:
 * 流式更新中,只有内容发生变化的组件会重渲染,其余组件完全跳过。
 * 删除的围栏随 key 消失而卸载,顺序变化由 React 按 key 移动。
 */
const FenceBlock = memo(function FenceBlock({ lang, body }: { lang?: string; body: string }) {
  if (!CodeBlock) {
    return <pre className="text-xs overflow-auto">{body}</pre>;
  }
  return (
    <div className="vis-fence-segment">
      <CodeBlock className={lang ? `language-${lang}` : ''}>{body}</CodeBlock>
    </div>
  );
});

/** 文本段 — 交给 GPTVis 完整 markdown 渲染(与原来整串渲染的排版一致) */
const TextBlock = memo(function TextBlock({
  body,
  components,
}: {
  body: string;
  components?: any;
}) {
  return (
    // @ts-expect-error GPTVis 组件类型与实际用法不完全匹配(全项目一致的处理方式)
    <GPTVis components={components ?? markdownComponents} {...markdownPlugins}>
      {body}
    </GPTVis>
  );
});

/**
 * VisSegmentedMarkdown — VIS 组件级局部渲染。
 *
 * 把合并后的 VIS markdown(planning_window)按围栏切成有序段,
 * vis 组件以 uid 为 key 挂载,配合 memo 实现"只有变化的组件重渲染",
 * 替代整串 markdown 每次全量 GPTVis 渲染 —— 长会话/高频流式下
 * 渲染成本从 O(全部组件) 降为 O(变化组件)。
 */
const VisSegmentedMarkdown = memo(function VisSegmentedMarkdown({
  content,
  components,
}: {
  content: string;
  components?: any;
}) {
  const segments = useMemo(() => splitVisFences(content), [content]);
  return (
    <>
      {segments.map((seg) =>
        seg.kind === 'fence' ? (
          <FenceBlock key={seg.key} lang={seg.lang} body={seg.body} />
        ) : (
          <TextBlock key={seg.key} body={seg.body} components={components} />
        ),
      )}
    </>
  );
});

export default VisSegmentedMarkdown;
