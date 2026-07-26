import { ChartData, ChatHistoryResponse, IChatDialogueSchema, UserChatContent } from '@/types/chat';
import { IApp } from '@/types/app';
import { createContext } from 'react';
import type { ITodoListData } from '@/components/chat/chat-content-components/VisComponents/VisTodoList';
import type { ISubagentBoardData } from '@/components/chat/chat-content-components/VisComponents/VisSubagentBoard';

export const CompactChatContext = createContext<boolean>(false);

export interface SelectedSkill {
  skill_code: string;
  name: string;
  description?: string;
  type?: string;
  icon?: string;
  author?: string;
  version?: string;
}

interface ChatContentProps {
  history: ChatHistoryResponse;
  replyLoading: boolean;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  canAbort: boolean;
  chartsData: ChartData[];
  agent: string;
  currentDialogue: IChatDialogueSchema;
  currentConvSessionId: string;
  appInfo: IApp;
  temperatureValue: number;
  maxNewTokensValue: number;
  resourceValue: Record<string, unknown>;
  modelValue: string;
  selectedSkills: SelectedSkill[];
  chatInParams: Array<{
    param_type: string;
    param_value: string;
    sub_type: string;
  }>;
  setModelValue: React.Dispatch<React.SetStateAction<string>>;
  setTemperatureValue: React.Dispatch<React.SetStateAction<number>>;
  setMaxNewTokensValue: React.Dispatch<React.SetStateAction<number>>;
  setResourceValue: React.Dispatch<React.SetStateAction<Record<string, unknown>>>;
  setSelectedSkills: React.Dispatch<React.SetStateAction<SelectedSkill[]>>;
  setChatInParams: (params: Array<{
    param_type: string;
    param_value: string;
    sub_type: string;
  }>) => void;
  setAppInfo: React.Dispatch<React.SetStateAction<IApp>>;
  setAgent: React.Dispatch<React.SetStateAction<string>>;
  setCanAbort: React.Dispatch<React.SetStateAction<boolean>>;
  setReplyLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setCurrentConvSessionId: React.Dispatch<React.SetStateAction<string>>;
  handleChat: (content: UserChatContent, data?: Record<string, unknown>) => Promise<void>;
  refreshDialogList: () => void;
  refreshHistory: () => void;
  refreshAppInfo: () => void;
  setHistory: React.Dispatch<React.SetStateAction<ChatHistoryResponse>>;
  isShowDetail?: boolean;
  setIsShowDetail?: React.Dispatch<React.SetStateAction<boolean>>;
  isDebug?: boolean;
  isPollingMode?: boolean;
  /** 当前进度 todo list（输入框上方固定面板展示，由 todowrite 工具推送） */
  todoList?: ITodoListData | null;
  setTodoList?: React.Dispatch<React.SetStateAction<ITodoListData | null>>;
  /** 子任务面板（输入框上方固定展示，由 SubAgent async 派发/coordinator 推送） */
  subagentBoard?: ISubagentBoardData | null;
  setSubagentBoard?: React.Dispatch<React.SetStateAction<ISubagentBoardData | null>>;
  /** Start a brand-new conversation session (create backend conv + navigate). */
  onNewChat?: () => Promise<void>;
}

export const ChatContentContext = createContext<ChatContentProps>({
  history: [],
  replyLoading: false,
  scrollRef: { current: null },
  canAbort: false,
  chartsData: [],
  agent: '',
  currentDialogue: {} as IChatDialogueSchema,
  currentConvSessionId: '',
  appInfo: {} as IApp,
  temperatureValue: 0.5,
  maxNewTokensValue: 1024,
  resourceValue: {},
  chatInParams: [],
  selectedSkills: [],
  modelValue: '',
  setChatInParams: () => {},
  setModelValue: () => {},
  setResourceValue: () => {},
  setSelectedSkills: () => {},
  setTemperatureValue: () => {},
  setMaxNewTokensValue: () => {},
  setAppInfo: () => {},
  setAgent: () => {},
  setCanAbort: () => {},
  setReplyLoading: () => {},
  setCurrentConvSessionId: () => {},
  refreshDialogList: () => {},
  refreshHistory: () => {},
  refreshAppInfo: () => {},
  setHistory: () => {},
  handleChat: () => Promise.resolve(),
  isShowDetail: true,
  setIsShowDetail: () => {},
  isDebug: false,
  isPollingMode: false,
  todoList: null,
  setTodoList: () => {},
  subagentBoard: null,
  setSubagentBoard: () => {},
});
