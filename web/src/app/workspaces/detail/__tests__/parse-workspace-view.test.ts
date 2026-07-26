import { parseWorkspaceView } from '../parse-workspace-view';
import type { WorkspaceView } from '../agent-workspace-types';

describe('parseWorkspaceView', () => {
  test('首次 chunk 建立 execution', () => {
    const chunk = {
      render_name: 'scene_agent_workspace',
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: '搜索', status: 'running', action: 'search' }],
      summary: null,
    };
    const view = parseWorkspaceView(chunk, null);
    expect(view.execution).toHaveLength(1);
    expect(view.execution[0].id).toBe('s1');
    expect(view.execution[0].status).toBe('running');
  });

  test('同 id 步骤去重更新状态', () => {
    const prev: WorkspaceView = {
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: '搜索', status: 'running', action: 'search' }],
      summary: null,
    };
    const chunk = {
      render_name: 'scene_agent_workspace',
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: '搜索', status: 'done', action: 'search', output: 'OK' }],
      summary: '完成',
    };
    const view = parseWorkspaceView(chunk, prev);
    expect(view.execution).toHaveLength(1);
    expect(view.execution[0].status).toBe('done');
    expect(view.execution[0].output).toBe('OK');
    expect(view.summary).toBe('完成');
  });

  test('新 id 步骤追加', () => {
    const prev: WorkspaceView = {
      planning: null,
      execution: [{ id: 's1', type: 'tool_call', title: 'A', status: 'done' }],
      summary: null,
    };
    const chunk = {
      render_name: 'scene_agent_workspace',
      planning: { goal: 'G', steps: [{ id: 'p1', title: 'P1', status: 'done' }] },
      execution: [{ id: 's1', type: 'tool_call', title: 'A', status: 'done' }, { id: 's2', type: 'artifact', title: 'B', status: 'running' }],
      summary: null,
    };
    const view = parseWorkspaceView(chunk, prev);
    expect(view.execution.map(e => e.id)).toEqual(['s1', 's2']);
    expect(view.planning?.goal).toBe('G');
  });

  test('非法 payload 返回 prev', () => {
    const prev: WorkspaceView = { planning: null, execution: [], summary: null };
    expect(parseWorkspaceView(null, prev)).toBe(prev);
    expect(parseWorkspaceView({ execution: 'no' }, prev)).toBe(prev);
  });

  test('混合时区 ts 按真实时序排序(UTC Z vs 本地 naive)', () => {
    // 服务端步骤是本地 naive ISO,乐观用户步骤是 UTC 带 Z。
    // 本地 +08: 服务端 22:00 naive == UTC 14:00Z;乐观 14:05Z 应排在它后面。
    const prev: WorkspaceView = {
      planning: null,
      execution: [
        { id: 'user1', type: 'user', title: '我', status: 'done', output: 'q1', ts: '2026-07-25T22:00:00' },
        { id: 'tool1', type: 'tool_call', title: 'A', status: 'done', ts: '2026-07-25T22:01:03.123456' },
      ],
      summary: null,
    };
    const chunk = {
      render_name: 'scene_agent_workspace',
      planning: null,
      execution: [
        { id: 'user2-opt', type: 'user', title: '我', status: 'done', output: 'q2', ts: '2026-07-25T14:05:00.000Z' },
      ],
      summary: null,
    };
    const view = parseWorkspaceView(chunk, prev);
    expect(view.execution.map(e => e.id)).toEqual(['user1', 'tool1', 'user2-opt']);
  });
});