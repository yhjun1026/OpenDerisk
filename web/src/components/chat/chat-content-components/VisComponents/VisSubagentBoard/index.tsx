import React, { useEffect, useMemo, useState } from 'react';
import { VisSubagentBoardWrap } from './style';
import { AppstoreOutlined, UpOutlined, DownOutlined } from '@ant-design/icons';

export interface SubagentItemData {
  sub_conv_id: string;
  agent_name?: string;
  task?: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'awaiting_authorization';
  mode?: string;
  authorization?: string;
}

export interface ISubagentBoardData {
  uid?: string;
  type?: string;
  items?: SubagentItemData[];
  total_count?: number;
  completed_count?: number;
}

interface IProps {
  otherComponents?: any;
  data: ISubagentBoardData;
}

const STATUS_LABEL: Record<SubagentItemData['status'], string> = {
  pending: '待开始',
  running: '运行中',
  done: '已完成',
  failed: '失败',
  awaiting_authorization: '待授权',
};

const isTerminal = (s: string) => s === 'done' || s === 'failed';

const VisSubagentBoard: React.FC<IProps> = ({ data }) => {
  const items: SubagentItemData[] = data.items || [];
  const [expanded, setExpanded] = useState(true);

  const toggleExpand = () => setExpanded(!expanded);

  const progress = useMemo(() => {
    const completed = items.filter((i) => isTerminal(i.status)).length;
    return { completed, total: items.length };
  }, [items]);

  // 全部终态自动折叠（参考 VisTodoList）；从完成态变回进行中则重新展开
  const allCompleted = items.length > 0 && items.every((i) => isTerminal(i.status));
  useEffect(() => {
    setExpanded(!allCompleted);
  }, [allCompleted]);

  const hasAuth = items.some((i) => i.status === 'awaiting_authorization');

  const openSubagent = (subConvId: string) => {
    // 新标签页打开子会话，复用 chat 页面完整渲染子任务对话流（含 VIS/消息流）。
    // 未来可改为右面板内联展开：VisManusRightPanel CLICK_FOLDER handler 加 sub_conv_id
    // 分支 + useChatPolling(sub_conv_id) 集成（sub_conv_id 不在 steps_map，当前会落空）。
    window.open(`/chat?app_code=chat_normal&conv_uid=${subConvId}`, '_blank');
  };

  return (
    <VisSubagentBoardWrap>
      <div className="board-header" onClick={toggleExpand}>
        <div className="header-left">
          <AppstoreOutlined className="header-icon" />
          <span className="header-title">{allCompleted ? '子任务完成' : '子任务'}</span>
          <span className="header-progress">{progress.completed}/{progress.total}</span>
          {hasAuth && <span className="header-auth-badge">待授权</span>}
        </div>
        <div className="header-expand">
          {expanded ? <UpOutlined /> : <DownOutlined />}
        </div>
      </div>

      {expanded && (
        <div className="board-items">
          {items.map((item) => (
            <div
              key={item.sub_conv_id}
              className={`subagent-item ${item.status}`}
              onClick={() => openSubagent(item.sub_conv_id)}
            >
              <div className="status-icon">
                {item.status === 'running' && <span className="spinner" />}
                {item.status === 'done' && <span className="dot done" />}
                {item.status === 'failed' && <span className="dot failed" />}
                {item.status === 'pending' && <span className="dot pending" />}
                {item.status === 'awaiting_authorization' && <span className="dot awaiting" />}
              </div>
              <div className="item-content">
                <div className={`item-title ${item.status}`}>
                  {item.agent_name || item.sub_conv_id.slice(0, 8)}
                </div>
                {item.task && (
                  <div className="item-task" title={item.task}>{item.task}</div>
                )}
                {item.authorization && (
                  <div className="item-auth">⚠ {item.authorization}</div>
                )}
              </div>
              <span className={`item-status-badge ${item.status}`}>
                {STATUS_LABEL[item.status]}
              </span>
            </div>
          ))}

          {items.length === 0 && (
            <div className="board-empty">
              <span>暂无子任务</span>
            </div>
          )}
        </div>
      )}
    </VisSubagentBoardWrap>
  );
};

export default VisSubagentBoard;
