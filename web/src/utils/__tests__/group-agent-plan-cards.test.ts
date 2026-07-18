import { groupConsecutivePlanCards } from '../group-agent-plan-cards';

const planFence = (uid: string, title: string, extra: Record<string, any> = {}) =>
  '```d-agent-plan\n' +
  JSON.stringify({
    uid,
    type: 'incr',
    item_type: 'task',
    parent_uid: null,
    layer_count: 0,
    title,
    description: '{}',
    status: 'complete',
    ...extra,
  }) +
  '\n```';

describe('groupConsecutivePlanCards', () => {
  it('returns markdown unchanged when no d-agent-plan fence exists', () => {
    const md = 'hello\n```drsk-content\n{"markdown":"x"}\n```';
    expect(groupConsecutivePlanCards(md)).toBe(md);
  });

  it('groups 3+ consecutive same-title task fences into one group fence', () => {
    const md = [
      '前置文本',
      planFence('tool-1', 'execute_sql'),
      planFence('tool-2', 'execute_sql'),
      planFence('tool-3', 'execute_sql'),
      '后续文本',
    ].join('\n');
    const result = groupConsecutivePlanCards(md);
    expect(result).toContain('```d-agent-plan-group');
    expect(result).not.toContain('```d-agent-plan\n');
    const groupJson = result.match(/```d-agent-plan-group\n([\s\S]*?)\n```/)![1];
    const parsed = JSON.parse(groupJson);
    expect(parsed.uid).toBe('group-tool-1');
    expect(parsed.title).toBe('execute_sql');
    expect(parsed.items.map((i: any) => i.uid)).toEqual(['tool-1', 'tool-2', 'tool-3']);
    expect(result.startsWith('前置文本')).toBe(true);
    expect(result.endsWith('后续文本')).toBe(true);
  });

  it('keeps runs shorter than minGroupSize as individual fences', () => {
    const md = [planFence('tool-1', 'execute_sql'), planFence('tool-2', 'execute_sql')].join('\n');
    const result = groupConsecutivePlanCards(md);
    expect(result).not.toContain('d-agent-plan-group');
    expect(result).toContain('tool-1');
    expect(result).toContain('tool-2');
  });

  it('breaks the run when narrative text intervenes', () => {
    const md = [
      planFence('tool-1', 'execute_sql'),
      planFence('tool-2', 'execute_sql'),
      '正在继续分析...',
      planFence('tool-3', 'execute_sql'),
      planFence('tool-4', 'execute_sql'),
      planFence('tool-5', 'execute_sql'),
    ].join('\n');
    const result = groupConsecutivePlanCards(md);
    expect(result.match(/d-agent-plan-group/g)!.length).toBe(1);
    const groupJson = result.match(/```d-agent-plan-group\n([\s\S]*?)\n```/)![1];
    expect(JSON.parse(groupJson).items.map((i: any) => i.uid)).toEqual(['tool-3', 'tool-4', 'tool-5']);
    expect(result).toContain('正在继续分析...');
  });

  it('breaks the run when the tool title changes', () => {
    const md = [
      planFence('tool-1', 'execute_sql'),
      planFence('tool-2', 'execute_sql'),
      planFence('tool-3', 'Read'),
      planFence('tool-4', 'execute_sql'),
    ].join('\n');
    expect(groupConsecutivePlanCards(md)).not.toContain('d-agent-plan-group');
  });

  it('does not group explicitly parented or non-task items', () => {
    const md = [
      planFence('tool-1', 'execute_sql', { parent_uid: 'agent-1' }),
      planFence('tool-2', 'execute_sql', { parent_uid: 'agent-1' }),
      planFence('tool-3', 'execute_sql', { item_type: 'plan' }),
    ].join('\n');
    expect(groupConsecutivePlanCards(md)).not.toContain('d-agent-plan-group');
  });

  it('groups same-level sibling tasks regardless of layer_count (nested in agent markdown)', () => {
    const md = [
      planFence('tool-1', 'execute_sql', { layer_count: 2 }),
      planFence('tool-2', 'execute_sql', { layer_count: 2 }),
      planFence('tool-3', 'execute_sql', { layer_count: 2 }),
    ].join('\n');
    expect(groupConsecutivePlanCards(md)).toContain('d-agent-plan-group');
  });

  it('keeps unparseable fences untouched', () => {
    const broken = '```d-agent-plan\n{not-json\n```';
    const md = [planFence('tool-1', 'execute_sql'), broken, planFence('tool-2', 'execute_sql')].join('\n');
    const result = groupConsecutivePlanCards(md);
    expect(result).toContain(broken);
    expect(result).not.toContain('d-agent-plan-group');
  });

  it('preserves surrounding blank lines when a run is not grouped', () => {
    const md = `\n${planFence('tool-1', 'execute_sql')}\n\n${planFence('tool-2', 'Read')}\n`;
    expect(groupConsecutivePlanCards(md)).toBe(md);
  });
});
