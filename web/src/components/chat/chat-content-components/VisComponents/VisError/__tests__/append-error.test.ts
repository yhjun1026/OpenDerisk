// index.tsx 依赖 antd Alert,在 node 测试环境用 mock 规避,只测纯函数逻辑。
jest.mock('antd', () => ({ Alert: () => null }));

import { appendErrorToContext, buildVisErrorMarkdown } from '../index';

const manusContext = (planning = '```d-agent-plan\n{"uid":"a"}\n```') =>
  JSON.stringify({
    planning_window: planning,
    running_window: '```manus-right-panel\n{"uid":"b"}\n```',
    meta_window: '{"total_steps":1}',
  });

describe('appendErrorToContext', () => {
  it('复现 bug:旧逻辑(直接追加围栏)会破坏 manus JSON context', () => {
    const ctx = manusContext();
    const broken = ctx + buildVisErrorMarkdown('网络错误');
    expect(() => JSON.parse(broken)).toThrow();
  });

  it('manus JSON context:注入 planning_window,保持 JSON 结构,running_window/meta_window 不变', () => {
    const ctx = manusContext();
    const out = appendErrorToContext(ctx, '对话连接中断: network error');

    // 仍是有效 JSON(修复前会抛)
    const parsed = JSON.parse(out);
    expect(parsed.running_window).toBe('```manus-right-panel\n{"uid":"b"}\n```');
    expect(parsed.meta_window).toBe('{"total_steps":1}');
    // planning_window 保留原内容并追加 d-error 围栏
    expect(parsed.planning_window).toContain('```d-agent-plan');
    expect(parsed.planning_window).toContain('```d-error');
    expect(parsed.planning_window).toContain('对话连接中断: network error');
  });

  it('围栏 markdown context(非 JSON):直接追加末尾,行为不变', () => {
    const ctx = '```d-agent-plan\n{"uid":"a"}\n```';
    expect(appendErrorToContext(ctx, 'err')).toBe(ctx + buildVisErrorMarkdown('err'));
  });

  it('空 context:仅返回错误围栏', () => {
    expect(appendErrorToContext('', 'err')).toBe(buildVisErrorMarkdown('err'));
    expect(appendErrorToContext(undefined as any, 'err')).toBe(buildVisErrorMarkdown('err'));
  });

  it('畸形 JSON(parse 失败):回退到直接追加,不比现状差', () => {
    const ctx = '{not valid json';
    expect(appendErrorToContext(ctx, 'err')).toBe(ctx + buildVisErrorMarkdown('err'));
  });

  it('JSON 但无 planning_window 字段:回退到直接追加', () => {
    const ctx = JSON.stringify({ foo: 'bar' });
    expect(appendErrorToContext(ctx, 'err')).toBe(ctx + buildVisErrorMarkdown('err'));
  });
});
