/** @jest-environment jsdom */
import { render, fireEvent, screen } from '@testing-library/react';
import { AgentWorkspaceInput } from '../agent-workspace-input';

jest.mock('@/client/api', () => ({
  apiInterceptors: jest.fn(() => Promise.resolve([null, []])),
  getModelList: jest.fn(),
  postChatModeParamsFileLoad: jest.fn(),
}));
jest.mock('ahooks', () => ({ useRequest: () => ({ loading: false }) }));

describe('AgentWorkspaceInput', () => {
  test('输入 / 且有 playbooks 时显示剧本列表', () => {
    const onSend = jest.fn();
    render(
      <AgentWorkspaceInput
        convUid="c1"
        onSend={onSend}
        playbooks={[{ playbook_id: 1, playbook_name: '营收分析' }]}
      />,
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '/' } });
    expect(screen.getByText('营收分析')).toBeInTheDocument();
  });

  test('选中剧本后 onSend 携带 playbookCommand 与主题文本', () => {
    const onSend = jest.fn();
    render(
      <AgentWorkspaceInput
        convUid="c1"
        onSend={onSend}
        playbooks={[{ playbook_id: 1, playbook_name: '营收分析' }]}
      />,
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '本月营收/' } });
    fireEvent.click(screen.getByText('营收分析'));
    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({
        text: '本月营收',
        playbookCommand: { playbook_id: 1, playbook_name: '营收分析' },
      }),
    );
  });

  test('focus 存在时渲染当前关注 chip, 点 × 调 onClearFocus', () => {
    const onSend = jest.fn();
    const onClearFocus = jest.fn();
    render(
      <AgentWorkspaceInput
        convUid="c1"
        onSend={onSend}
        focus={{ id: 42, title: '周报' }}
        onClearFocus={onClearFocus}
      />,
    );
    expect(screen.getByText('周报')).toBeInTheDocument();
    expect(screen.getByText('当前关注')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('取消带入当前关注'));
    expect(onClearFocus).toHaveBeenCalled();
  });

  test('focus 为 null 时不渲染关注 chip', () => {
    const onSend = jest.fn();
    render(
      <AgentWorkspaceInput convUid="c1" onSend={onSend} focus={null} />,
    );
    expect(screen.queryByText('当前关注')).not.toBeInTheDocument();
  });
});