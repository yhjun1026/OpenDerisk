import { statusToTab, statusLabel, parseEcpProposalSource } from '../scene-task-rail';

describe('statusToTab', () => {
  it('maps running variants to running tab', () => {
    expect(statusToTab('running')).toBe('running');
    expect(statusToTab('draft')).toBe('running');
    expect(statusToTab('pending_trigger')).toBe('running');
    expect(statusToTab('blocked')).toBe('running');
  });
  it('maps awaiting_human to awaiting tab', () => {
    expect(statusToTab('awaiting_human')).toBe('awaiting');
  });
  it('maps delivered/closed to done tab', () => {
    expect(statusToTab('delivered')).toBe('done');
    expect(statusToTab('closed')).toBe('done');
  });
  it('maps failed to failed tab', () => {
    expect(statusToTab('failed')).toBe('failed');
  });
  it('falls back to all', () => {
    expect(statusToTab('whatever')).toBe('all');
    expect(statusToTab(undefined)).toBe('all');
  });
});

describe('statusLabel', () => {
  it('returns 人话文案', () => {
    expect(statusLabel('running')).toBe('运行中');
    expect(statusLabel('awaiting_human')).toBe('待你介入');
    expect(statusLabel('delivered')).toBe('已交付');
    expect(statusLabel('failed')).toBe('失败');
  });
});

describe('parseEcpProposalSource', () => {
  // source_id 由后端 ecp_sync 构造为 f"{ecp_ws}:{obj.id}@v{version}"。
  // 场景空间就地确认依赖此解析拿到派生 ECP workspace + 提案 id + 版本,
  // 不再跳转全局 ECP 模块、不选错空间、能定位到具体提案。
  it('parses derived ecp workspace / obj id / version', () => {
    expect(parseEcpProposalSource('ecp_ws_abc123:metric_revenue@v3')).toEqual({
      workspaceId: 'ecp_ws_abc123',
      objId: 'metric_revenue',
      version: 3,
    });
  });

  it('handles workspace codes with underscores and multi-digit versions', () => {
    expect(parseEcpProposalSource('ecp_ws_a1b2c3d4:entity_customer@v12')).toEqual({
      workspaceId: 'ecp_ws_a1b2c3d4',
      objId: 'entity_customer',
      version: 12,
    });
  });

  it('returns null for malformed source_id (no jump to wrong space)', () => {
    expect(parseEcpProposalSource('not-a-valid-source')).toBeNull();
    expect(parseEcpProposalSource('ecp_ws:obj')).toBeNull();
    expect(parseEcpProposalSource('ecp_ws:obj@v')).toBeNull();
    expect(parseEcpProposalSource('')).toBeNull();
  });
});