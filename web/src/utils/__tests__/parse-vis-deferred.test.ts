import { VisParser } from '../parse-vis';

const planFence = (uid: string, title: string, status = 'running') =>
  '```d-agent-plan\n' +
  JSON.stringify({ uid, type: 'incr', item_type: 'task', title, status }) +
  '\n```';

const windowPayload = (planning: string) =>
  JSON.stringify({ planning_window: planning, running_window: '', meta_window: null });

describe('VisParser deferred serialization (update + flush)', () => {
  it('produces the same result as immediate serialization after multiple chunks', () => {
    const eager = new VisParser();
    const lazy = new VisParser();

    const chunks = [
      windowPayload(planFence('tool-1', 'execute_sql')),
      windowPayload(planFence('tool-2', 'execute_sql')),
      windowPayload(planFence('tool-1', 'execute_sql', 'complete')),
    ];

    for (const c of chunks) eager.update(c);
    for (const c of chunks) lazy.update(c, false);
    lazy.flush();

    expect(JSON.parse(lazy.current)).toEqual(JSON.parse(eager.current));
    const pw = JSON.parse(lazy.current).planning_window;
    expect(pw).toContain('tool-1');
    expect(pw).toContain('tool-2');
    expect(pw).toContain('complete');
  });

  it('flush is idempotent when nothing is dirty', () => {
    const p = new VisParser();
    p.update(windowPayload(planFence('tool-1', 'Read')));
    const before = p.current;
    expect(p.flush()).toBe(before);
  });

  it('update with serialize=true after deferred chunks still works', () => {
    const p = new VisParser();
    p.update(windowPayload(planFence('tool-1', 'Read')), false);
    p.update(windowPayload(planFence('tool-2', 'Read')), false);
    p.update(windowPayload(planFence('tool-3', 'Write')), true);
    const pw = JSON.parse(p.current).planning_window;
    expect(pw).toContain('tool-1');
    expect(pw).toContain('tool-2');
    expect(pw).toContain('tool-3');
  });

  it('keeps meta_window passthrough across deferred merges', () => {
    const p = new VisParser();
    const payload = JSON.stringify({
      planning_window: planFence('tool-1', 'execute_sql'),
      meta_window: '{"total_steps":3}',
    });
    p.update(payload, false);
    p.flush();
    const parsed = JSON.parse(p.current);
    expect(parsed.meta_window).toBe('{"total_steps":3}');
  });
});
