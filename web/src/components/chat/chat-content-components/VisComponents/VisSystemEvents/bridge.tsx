'use client';

import React, { FC, useContext, useEffect } from 'react';
import VisSystemEvents from './index';
import { CompactChatContext } from '@/contexts/chat-content-context';
import { ee, EVENTS } from '@/utils/event-emitter';

/**
 * SystemEventsBridge — d-system-events 的渲染桥接。
 *
 * 任何布局下都把最新状态事件数据广播到事件总线(SYSTEM_EVENTS);
 * manus 布局(compact 上下文)不再内嵌渲染——状态事件统一由
 * 输入框上方的固定 badge 区展示,避免它混在消息流里位置飘忽。
 */
const SystemEventsBridge: FC<{ data: any }> = ({ data }) => {
  const compact = useContext(CompactChatContext);

  useEffect(() => {
    ee.emit(EVENTS.SYSTEM_EVENTS, data);
  }, [data]);

  if (compact) return null;
  return <VisSystemEvents data={data} />;
};

export default SystemEventsBridge;
