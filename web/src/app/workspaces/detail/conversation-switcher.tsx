'use client';

import { useState } from 'react';
import { Dropdown, Button, Modal, Input, message } from 'antd';
import { useRequest } from 'ahooks';
import {
  apiInterceptors,
  listConversations,
  setCurrentConversation,
  renameConversation,
  createConversation,
  linkConversation,
  queryChatStatus,
} from '@/client/api';

export interface ConversationSwitcherProps {
  workspaceId: number;
  currentConvUid: string;
  onChanged: (convUid: string, taskId?: number | null) => void;
}

export function ConversationSwitcher({
  workspaceId,
  currentConvUid,
  onChanged,
}: ConversationSwitcherProps) {
  const [renameTarget, setRenameTarget] = useState<{ convUid: string; title: string } | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const { data: listRes, refresh } = useRequest(
    async () => apiInterceptors(listConversations({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const conversations = listRes?.[1] || [];
  const [convStates, setConvStates] = useState<Record<string, string>>({});

  // Dropdown 打开时并发查询每个会话的运行状态,供列表项展示运行中/失败徽标
  const handleOpenChange = async (open: boolean) => {
    if (!open || conversations.length === 0) return;
    const entries = await Promise.all(
      conversations.map(async (c: any) => {
        try {
          const r = await queryChatStatus(c.conv_uid, 'scene_agent_workspace');
          return [c.conv_uid, r?.data?.data?.state ?? 'UNKNOWN'] as [string, string];
        } catch {
          return [c.conv_uid, 'UNKNOWN'] as [string, string];
        }
      }),
    );
    setConvStates(Object.fromEntries(entries));
  };

  const handleNew = async () => {
    const [, newConv] = await apiInterceptors(createConversation({ workspace_id: workspaceId }));
    if (!newConv?.conv_uid) return;
    await apiInterceptors(
      linkConversation({
        workspace_id: workspaceId,
        conv_uid: newConv.conv_uid,
        user_id: undefined,
      }),
    );
    await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
    refresh();
    onChanged(newConv.conv_uid, null);
    message.success('已新建会话');
  };

  const handleSelect = async (convUid: string, taskId?: number | null) => {
    await apiInterceptors(setCurrentConversation(workspaceId, convUid));
    onChanged(convUid, taskId);
  };

  const handleRename = async () => {
    if (!renameTarget) return;
    await apiInterceptors(renameConversation(renameTarget.convUid, renameValue));
    setRenameTarget(null);
    refresh();
    message.success('已重命名');
  };

  const items = [
    ...conversations.map((c: any) => ({
      key: c.conv_uid,
      label: (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontWeight: c.conv_uid === currentConvUid ? 600 : 400,
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
            {convStates[c.conv_uid] === 'RUNNING' && (
              <span style={{ color: '#52c41a', fontSize: 12, flexShrink: 0 }} title="运行中">● 运行中</span>
            )}
            {convStates[c.conv_uid] === 'FAILED' && (
              <span style={{ color: '#ff4d4f', fontSize: 12, flexShrink: 0 }} title="失败">● 失败</span>
            )}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {c.title || c.conv_uid.slice(0, 8)}
            </span>
          </span>
          <Button
            type="link"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              setRenameTarget({ convUid: c.conv_uid, title: c.title || '' });
              setRenameValue(c.title || '');
            }}
          >
            重命名
          </Button>
        </div>
      ),
      onClick: () => handleSelect(c.conv_uid, c.task_id),
    })),
    { type: 'divider' as const },
    { key: '__new__', label: '+ 新建会话', onClick: handleNew },
  ];

  return (
    <>
      <Dropdown menu={{ items }} trigger={['click']} onOpenChange={handleOpenChange}>
        <Button size="small">会话切换</Button>
      </Dropdown>
      <Modal
        title="重命名会话"
        open={!!renameTarget}
        onOk={handleRename}
        onCancel={() => setRenameTarget(null)}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          placeholder="输入新的会话标题"
        />
      </Modal>
    </>
  );
}
