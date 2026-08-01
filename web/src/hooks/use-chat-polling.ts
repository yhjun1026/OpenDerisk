import { useState, useEffect, useRef, useCallback } from 'react';
import { queryChatStatus, ChatQueryResponse } from '@/client/api/chat';

export type ConversationState = 'RUNNING' | 'COMPLETE' | 'FAILED' | 'WAITING' | 'UNKNOWN';

interface UseChatPollingOptions {
  convId: string | null;
  enabled?: boolean;
  interval?: number;
  /** 强制历史/轮询用指定 converter 组装 vis_final(如通用页传 vis_manus) */
  visRender?: string;
  onComplete?: (response: ChatQueryResponse) => void;
  onError?: (error: Error) => void;
  /** 每次成功 queryChatStatus(含首次历史拉取与后续轮询)回调,供调用方增量合并 vis_final */
  onPoll?: (response: ChatQueryResponse) => void;
}

interface UseChatPollingReturn {
  state: ConversationState;
  isPolling: boolean;
  data: ChatQueryResponse | null;
  startPolling: () => void;
  stopPolling: () => void;
  checkStatus: () => Promise<ChatQueryResponse | null>;
}

export function useChatPolling({
  convId,
  enabled = true,
  interval = 2000,
  visRender,
  onComplete,
  onError,
  onPoll,
}: UseChatPollingOptions): UseChatPollingReturn {
  const [state, setState] = useState<ConversationState>('UNKNOWN');
  const [isPolling, setIsPolling] = useState(false);
  const [data, setData] = useState<ChatQueryResponse | null>(null);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);
  // onPoll 用 ref 承载,避免它进入 checkStatus 依赖导致频繁重建/重复请求
  const onPollRef = useRef(onPoll);
  onPollRef.current = onPoll;

  const checkStatus = useCallback(async (): Promise<ChatQueryResponse | null> => {
    if (!convId) return null;
    
    try {
      const response = await queryChatStatus(convId, visRender);
      const result = response.data?.data;
      if (!result) {
        // 后端返回 success:false / 无 data(如会话尚未生成),不更新状态,避免读 undefined 崩溃
        return null;
      }

      if (mountedRef.current) {
        setData(prev => {
          if (prev?.vis_final === result.vis_final && prev?.state === result.state) {
            return prev;
          }
          return result;
        });
        setState(result.state as ConversationState);
        // 每次成功拉取(首次历史 + 后续轮询)都通知调用方增量合并 vis_final;
        // parseWorkspaceView 按 id 幂等合并,重复推送相同内容无害
        onPollRef.current?.(result);
      }
      
      return result;
    } catch (error) {
      if (mountedRef.current) {
        setState('UNKNOWN');
      }
      onError?.(error as Error);
      return null;
    }
  }, [convId, visRender, onError]);

  const startPolling = useCallback(() => {
    if (!convId || !enabled) return;
    
    setIsPolling(true);
    
    // 立即检查一次
    checkStatus().then(result => {
      if (result && result.state !== 'RUNNING') {
        // 如果不是运行中，不开始轮询
        setIsPolling(false);
        return;
      }
      
      // 开始轮询
      intervalRef.current = setInterval(async () => {
        const status = await checkStatus();
        
        if (status && status.state !== 'RUNNING') {
          // 对话完成或失败，停止轮询
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          setIsPolling(false);
          onComplete?.(status);
        }
      }, interval);
    });
  }, [convId, enabled, checkStatus, interval, onComplete]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  // 组件卸载时清理
  useEffect(() => {
    mountedRef.current = true;
    
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  // enabled 变为 false 时主动停止轮询(如 SSE 接管)。
  // 恢复由下方 convId effect 负责:其依赖含 enabled,false→true 时会自动 checkStatus + 按需 startPolling。
  useEffect(() => {
    if (!enabled && isPolling) {
      stopPolling();
    }
  }, [enabled, isPolling, stopPolling]);

  // convId 变化时，检查状态
  useEffect(() => {
    if (convId && enabled) {
      checkStatus().then(result => {
        if (result?.state === 'RUNNING') {
          startPolling();
        }
      });
    }
    
    return () => {
      stopPolling();
    };
  }, [convId, enabled, checkStatus, startPolling, stopPolling]);

  return {
    state,
    isPolling,
    data,
    startPolling,
    stopPolling,
    checkStatus,
  };
}

export default useChatPolling;