import { splitVisFences } from '../split-vis-fences';

describe('splitVisFences', () => {
  it('splits text and fences with stable uid keys', () => {
    const md = [
      '前置文本',
      '```d-agent-plan',
      '{"uid":"tool-1","title":"execute_sql"}',
      '```',
      '中间叙述',
      '```d-agent-plan',
      '{"uid":"tool-2","title":"Read"}',
      '```',
      '结尾',
    ].join('\n');
    const segs = splitVisFences(md);
    expect(segs.map((s) => s.kind)).toEqual(['text', 'fence', 'text', 'fence', 'text']);
    expect(segs[1].lang).toBe('d-agent-plan');
    expect(segs[1].key).toBe('tool-1');
    expect(segs[3].key).toBe('tool-2');
    expect(segs[0].body).toBe('前置文本');
    expect(segs[2].body).toBe('中间叙述');
  });

  it('does not mistake inline ``` inside JSON body for a fence close', () => {
    const body = '{"uid":"x1","markdown":"代码: ```sql\\nselect 1\\n``` 结束"}';
    const md = ['```drsk-content', body, '```'].join('\n');
    const segs = splitVisFences(md);
    expect(segs.length).toBe(1);
    expect(segs[0].kind).toBe('fence');
    expect(segs[0].body).toBe(body);
  });

  it('keeps unclosed streaming fence as a fence segment', () => {
    const md = ['文本', '```d-agent-plan', '{"uid":"tool-9","title":"Bash"}'].join('\n');
    const segs = splitVisFences(md);
    expect(segs.map((s) => s.kind)).toEqual(['text', 'fence']);
    expect(segs[1].key).toBe('tool-9');
  });

  it('falls back to sequence key when uid missing', () => {
    const md = ['```html', '<div>hi</div>', '```'].join('\n');
    const segs = splitVisFences(md);
    expect(segs.length).toBe(1);
    expect(segs[0].lang).toBe('html');
    expect(segs[0].key).toBe('f0-html');
  });

  it('returns empty array for empty input', () => {
    expect(splitVisFences('')).toEqual([]);
  });

  it('handles bare fence opener', () => {
    const md = ['```', 'plain code', '```'].join('\n');
    const segs = splitVisFences(md);
    expect(segs.length).toBe(1);
    expect(segs[0].kind).toBe('fence');
    expect(segs[0].body).toBe('plain code');
  });
});
