'use client';
import { apiInterceptors, delDialogue, getDialogueListBByFilter } from '@/client/api';
import { ChatContext } from '@/contexts';
import { STORAGE_LANG_KEY, STORAGE_THEME_KEY } from '@/utils/constants/index';
import { getUserId } from '@/utils/storage';
import Icon, {
  ApiOutlined,
  BookOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DesktopOutlined,
  FileTextOutlined,
  GlobalOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  SettingOutlined,
  ShareAltOutlined,
  SearchOutlined,
  RobotOutlined,
  ExperimentOutlined,
  SafetyOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  MoonOutlined,
  SunOutlined,
  RightOutlined,
  CompassOutlined,
  DeploymentUnitOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { authService } from '@/services/auth';
import { App, Flex, Input, Popover, Spin, Tooltip, Typography } from 'antd';
import cls from 'classnames';
import moment from 'moment';
import 'moment/locale/zh-cn';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ReactNode, useCallback, useContext, useEffect, useMemo, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import ModelSvg from '../icons/model-svg';
import ChatIcon from '../icons/chat-icon';
import UserBar from './user-bar';
import copy from 'copy-to-clipboard';
import { useUserPermissions } from '@/hooks/use-user-permissions';

type SettingItem = {
  key: string;
  name: string;
  icon: ReactNode;
  noDropdownItem?: boolean;
  onClick?: () => void;
  items?: any[];
  onSelect?: (p: { key: string }) => void;
  defaultSelectedKeys?: string[];
  placement?: 'top' | 'topLeft';
  disable?: boolean;
};

export type RouteItem = {
  key: string;
  name: string;
  icon?: ReactNode;
  path?: string;
  isActive?: boolean;
  children?: RouteItem[];
  hideInMenu?: boolean;
};

interface Dialogue {
  chat_mode: string;
  conv_uid: string;
  conv_session_id?: string; // 会话ID，用于获取整个会话的消息
  user_input?: string;
  select_param?: string;
  app_code?: string;
  user_name?: string;
  gmt_created?: string;
  gmt_modified?: string;
}

interface DialogueListItem {
  key: string;
  name: string | undefined;
  path: string;
  dialogue: Dialogue;
}

interface GroupedDialogues {
  [key: string]: DialogueListItem[];
}

function smallMenuItemStyle(active?: boolean) {
  return `flex items-center justify-center mx-auto rounded w-14 h-14 text-xl hover:bg-[#f2f4f8] dark:hover:bg-theme-dark transition-colors cursor-pointer ${
    active ? 'bg-[#efeff1] text-[#14161c] dark:bg-theme-dark' : ''
  }`;
}

const MenuItem: React.FC<{
  item: any;
  refresh?: any;
  order: React.MutableRefObject<number>;
  historyLoading?: boolean;
  loading?: boolean;
}> = ({ item, refresh, historyLoading, loading }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const chatId = searchParams?.get('conv_uid') ?? '';
  const appCode = searchParams?.get('app_code') ?? '';
  const { modal, message } = App.useApp();
  const { refreshDialogList } = useContext(ChatContext);

  const handleDelChat = () => {
    modal.confirm({
      title: t('delete_chat'),
      content: t('delete_chat_confirm'),
      centered: true,
      onOk: async () => {
        const [err] = await apiInterceptors(delDialogue(item.conv_uid));
        if (err) {
          return;
        }
        refreshDialogList && (await refreshDialogList());
        router.push(`/chat`);
      },
    });
  };

  if (loading) {
    return (
      <Flex align='center' className='w-full h-10 px-3 rounded-lg mb-1'>
        <div className='flex items-center justify-center w-6 h-6 rounded-lg mr-3'>
          <Spin size='small' />
        </div>
        <div className='flex-1 min-w-0'>
          <div className='h-4 bg-gray-200 rounded animate-pulse'></div>
        </div>
      </Flex>
    );
  }
  const isActive = chatId === item.conv_uid && appCode === item.app_code;

  // 构建Tooltip内容：显示用户和创建时间
  const tooltipContent = (
    <div className='flex flex-col gap-1'>
      {item.user_name && (
        <div className='flex items-center gap-2'>
          <span className='text-gray-400'>{t('user')}:</span>
          <span>{item.user_name}</span>
        </div>
      )}
      {item.gmt_created && (
        <div className='flex items-center gap-2'>
          <span className='text-gray-400'>{t('created_time')}:</span>
          <span>{moment(item.gmt_created).format('YYYY-MM-DD HH:mm')}</span>
        </div>
      )}
    </div>
  );

  return (
    <Tooltip title={tooltipContent} placement='right'>
      <Flex
        align='center'
        className={cls(`group/item w-full cursor-pointer relative max-w-full my-0.5`)}
        onClick={() => {
          if (historyLoading) {
            return;
          }
          // 使用 conv_session_id（如果有）作为 URL 参数，否则使用 conv_uid
        const sessionParam = item.conv_session_id || item.conv_uid;
        router.push(`/chat/?conv_uid=${sessionParam}&app_code=${item.app_code}`);
        }}
      >
        <div className={cls('flex-1 flex flex-row min-w-0 overflow-hidden hover:bg-[#f2f4f8] dark:hover:bg-gray-800 rounded-lg px-3 py-2 transition-colors duration-200', {
          'bg-[#f2f4f8] dark:bg-gray-800': isActive,
        })}>
          <div className='mr-3 flex-shrink-0'>
            <ChatIcon className="w-5 h-5 text-[#8a92a6] dark:text-gray-400" />
          </div>
          <div className='flex-1 min-w-0 overflow-hidden'>
            <Typography.Text
              ellipsis={{
                tooltip: false, // 禁用Typography自己的tooltip，使用外层Tooltip
              }}
              className={cls('block text-[13px] font-normal', isActive ? 'text-[#14161c] dark:text-white' : 'text-[#5d6577] dark:text-gray-400')}
            >
              {item.label}
            </Typography.Text>
          </div>
          <div className='flex gap-1 ml-1 flex-shrink-0 items-center'>
            <div
              className='group-hover/item:opacity-100 cursor-pointer opacity-0 transition-opacity'
              onClick={e => {
                e.stopPropagation();
              }}
            >
              <ShareAltOutlined
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                style={{ fontSize: 14 }}
                onClick={() => {
                  const success = copy(`${location.origin}/chat?scene=${item.chat_mode}&id=${item.conv_uid}`);
                  message[success ? 'success' : 'error'](success ? t('copy_success') : t('copy_failed'));
                }}
              />
            </div>
            <div
              className='group-hover/item:opacity-100 cursor-pointer opacity-0 transition-opacity'
              onClick={e => {
                e.stopPropagation();
                handleDelChat();
              }}
            >
              <DeleteOutlined className="text-gray-400 hover:text-red-500" style={{ fontSize: 14 }} />
            </div>
          </div>
        </div>
      </Flex>
    </Tooltip>
  );
};

function SideBar() {
  const { isMenuExpand, setIsMenuExpand, mode, setMode, dialogueList, refreshDialogList } = useContext(ChatContext);
  const pathname = usePathname();
  const { t, i18n } = useTranslation();
  const [logo, setLogo] = useState<string>('/logo_zh_latest.png');
  const [dialogueLists, setDialogueLists] = useState<DialogueListItem[]>([]);
  const [closedSections, setClosedSections] = useState<Record<string, boolean>>({});
  const [searchValue, setSearchValue] = useState<string>('');
  const [oauthEnabled, setOauthEnabled] = useState(false);
  const { hasResourceRead, hasPermission } = useUserPermissions();

  useEffect(() => {
    authService.getOAuthStatus().then((s) => setOauthEnabled(s.enabled));
  }, []);

  const handleToggleMenu = useCallback(() => {
    setIsMenuExpand(!isMenuExpand);
  }, [isMenuExpand, setIsMenuExpand]);

  const handleToggleTheme = useCallback(() => {
    const theme = mode === 'light' ? 'dark' : 'light';
    setMode(theme);
    localStorage.setItem(STORAGE_THEME_KEY, theme);
  }, [mode, setMode]);

  const {
    run: fetchDialogueList,
    loading: listLoading,
  } = useRequest(async (name: string) => {
    const userId = getUserId();
    return await apiInterceptors(getDialogueListBByFilter(name, userId));
  },
   {
      manual: true,
      onSuccess: data => {
        if (data && data[1]) {
          const di = (data[1] as unknown as Dialogue[]).map(
            (dialogue: Dialogue): DialogueListItem => ({
              key: dialogue?.conv_uid,
              name: dialogue.user_input || dialogue.select_param,
              path: '/assistant',
              dialogue: dialogue,
            }),
          );
          setDialogueLists(dedupByConvUid(di));
        } else {
          setDialogueLists([]);
        }
      },
    },
 );
  // 暂时注释，后续完善中英文
  const handleChangeLang = useCallback(() => {
    const language = i18n.language === 'en' ? 'zh' : 'en';
    i18n.changeLanguage(language);
    if (language === 'zh') moment.locale('zh-cn');
    if (language === 'en') moment.locale('en');
    localStorage.setItem(STORAGE_LANG_KEY, language);
  }, [i18n]);
  const settings = useMemo(() => {
    const items: SettingItem[] = [
      {
        key: 'language',
        name: t('language'),
        icon: <GlobalOutlined />,
        items: [
          {
            key: 'en',
            label: (
              <div className='py-1 flex justify-between gap-8 '>
                <span className='flex gap-2'>
                  <Image src='/icons/english.png' alt='english' width={21} height={21}></Image>
                  <span>English</span>
                </span>
                <span
                  className={cls({
                    block: i18n.language === 'en',
                    hidden: i18n.language !== 'en',
                  })}
                >
                  ✓
                </span>
              </div>
            ),
          },
          {
            key: 'zh',
            label: (
              <div className='py-1 flex justify-between gap-8 '>
                <span className='flex gap-2'>
                  <Image src='/icons/zh.png' alt='english' width={21} height={21}></Image>
                  <span>简体中文</span>
                </span>
                <span
                  className={cls({
                    block: i18n.language === 'zh',
                    hidden: i18n.language !== 'zh',
                  })}
                >
                  ✓
                </span>
              </div>
            ),
          },
        ],
        onSelect: ({ key }: { key: string }) => {
          if (i18n.language === key) return;
          i18n.changeLanguage(key);
          if (key === 'zh') moment.locale('zh-cn');
          if (key === 'en') moment.locale('en');
          localStorage.setItem(STORAGE_LANG_KEY, key);
        },
        onClick: handleChangeLang,
        defaultSelectedKeys: [i18n.language],
      },
      {
        key: 'theme',
        name: mode === 'light' ? t('dark_mode') : t('light_mode'),
        icon: mode === 'light' ? <MoonOutlined /> : <SunOutlined />,
        onClick: handleToggleTheme,
        noDropdownItem: true,
      },
      {
        key: 'fold',
        name: t(isMenuExpand ? 'Close_Sidebar' : 'Show_Sidebar'),
        icon: isMenuExpand ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />,
        onClick: handleToggleMenu,
        noDropdownItem: true,
      },
    ];
    return items;
  }, [t, mode, handleToggleTheme, i18n, handleChangeLang, isMenuExpand, handleToggleMenu, setMode]);

  const searchParams = useSearchParams();

  /**
   * Extract readable user text from user_input.
   * user_input may be a plain string or a JSON stringified object
   * like {"type":"human","data":{"content":"...",...}} from V2 conversations.
   */
  const extractUserText = (raw: string | undefined): string => {
    if (!raw) return '';
    // If it starts with '{', try to parse as JSON and extract the text content
    if (raw.startsWith('{')) {
      try {
        const obj = JSON.parse(raw);
        // Extract content, ensuring it's a string (not an object)
        const content = obj.data?.content || obj.content;
        if (content) {
          // Handle case where content might be an object or array
          if (typeof content === 'string') return content;
          if (typeof content === 'object') {
            // For objects like {object, type}, stringify them
            return JSON.stringify(content);
          }
          return String(content);
        }
        return raw;
      } catch {
        return raw;
      }
    }
    return raw;
  };

  useEffect(() => {
     if (dialogueList && dialogueList[1]) {
      const di =  (dialogueList[1] as unknown as Dialogue[]).map(
        (dialogue: Dialogue): DialogueListItem => ({
          key: dialogue?.conv_uid,
          name: extractUserText(dialogue.user_input) || dialogue.select_param,
          path: '/assistant',
          dialogue: dialogue,
        }),
      );
     setDialogueLists(dedupByConvUid(di));
    }

  }, [dialogueList]);

  // 扁平分区导航(Linear 式):主导航 / 资源与能力 / 系统,无折叠组
  const navIcon = (el: ReactNode) => (
    <span className='w-5 h-5 flex items-center justify-center text-[15px] flex-shrink-0'>{el}</span>
  );

  const navSections = useMemo(() => {
    // ── 核心入口:智能体空间(场景空间为主业,不再单独入口) ──
    const mainItems: RouteItem[] = [
      ...(hasResourceRead('agent') ? [{
        key: 'explore',
        name: t('agent_space'),
        isActive: pathname.startsWith('/application/explore'),
        icon: navIcon(<CompassOutlined />),
        path: '/application/explore',
      }] : []),
    ];

    // ── 能力:Agent / Skill / MCP / 定时任务 / 任务引擎 / 消息渠道 ──
    const capabilityItems: RouteItem[] = [
      ...(hasResourceRead('agent') ? [{
        key: 'agents',
        name: t('Agents'),
        isActive: pathname.startsWith('/application/app'),
        icon: navIcon(<RobotOutlined />),
        path: '/application/app',
      }] : []),
      ...(hasResourceRead('tool') ? [{
        key: 'agent_skills',
        name: t('agent_skills'),
        isActive: pathname.startsWith('/agent-skills'),
        icon: navIcon(<ExperimentOutlined />),
        path: '/agent-skills',
      }] : []),
      ...(hasResourceRead('tool') ? [{
        key: 'MCP',
        name: 'MCP',
        isActive: pathname.startsWith('/mcp'),
        icon: navIcon(<ApiOutlined />),
        path: '/mcp',
      }] : []),
      ...(hasResourceRead('cron') || hasPermission('system', 'admin') ? [{
        key: 'cron',
        name: t('cron_page_title'),
        isActive: pathname.startsWith('/cron'),
        icon: navIcon(<ClockCircleOutlined />),
        path: '/cron',
      }] : []),
      ...(hasResourceRead('tool') ? [{
        key: 'jobs',
        name: '任务引擎',
        isActive: pathname.startsWith('/jobs'),
        icon: navIcon(<ThunderboltOutlined />),
        path: '/jobs',
      }] : []),
      ...(hasResourceRead('channel') || hasPermission('system', 'admin') ? [{
        key: 'channel',
        name: t('channel_page_title'),
        isActive: pathname.startsWith('/channel'),
        icon: navIcon(<MessageOutlined />),
        path: '/channel',
      }] : []),
    ];

    // ── 资产:知识库 / 语义资产 / 数据库 / 模型管理 ──
    const assetItems: RouteItem[] = [
      ...(hasResourceRead('knowledge') ? [{
        key: 'knowledge',
        name: t('knowledge_base'),
        isActive: pathname.startsWith('/knowledge-vault'),
        icon: navIcon(<BookOutlined />),
        path: '/knowledge-vault',
      }] : []),
      {
        key: 'ecp',
        name: t('ecp_page_title'),
        isActive: pathname.startsWith('/ecp'),
        icon: navIcon(<DeploymentUnitOutlined />),
        path: '/ecp',
      },
      ...(hasResourceRead('database') || hasResourceRead('tool') ? [{
        key: 'database',
        name: t('Database'),
        isActive: pathname.startsWith('/database'),
        icon: navIcon(<DatabaseOutlined />),
        path: '/database',
      }] : []),
      ...(hasResourceRead('model') ? [{
        key: 'models',
        name: t('model_manage'),
        isActive: pathname.startsWith('/models'),
        icon: navIcon(<Icon component={ModelSvg} />),
        path: '/models',
      }] : []),
    ];

    // ── 设置:监控 / 用量 / 系统配置 / 权限 / 审计日志 / GUI ──
    const settingItems: RouteItem[] = [
      ...(hasPermission('system', 'admin') ? [{
        key: 'monitoring',
        name: t('monitoring_page_title'),
        isActive: pathname.startsWith('/monitoring'),
        icon: navIcon(<DashboardOutlined />),
        path: '/monitoring',
      }] : []),
      ...(hasPermission('system', 'admin') ? [{
        key: 'usage',
        name: t('usage_page_title'),
        isActive: pathname.startsWith('/usage'),
        icon: navIcon(<BarChartOutlined />),
        path: '/usage',
      }] : []),
      ...(hasPermission('system', 'admin') ? [{
        key: 'system_config',
        name: t('system_config'),
        isActive: pathname.startsWith('/settings/config'),
        icon: navIcon(<SettingOutlined />),
        path: '/settings/config',
      }] : []),
      ...(hasPermission('system', 'admin') ? [{
        key: 'permissions',
        name: t('permissions_title'),
        isActive: pathname.startsWith('/settings/permissions'),
        icon: navIcon(<SafetyOutlined />),
        path: '/settings/permissions',
      }] : []),
      ...(hasPermission('system', 'admin') ? [{
        key: 'audit_logs',
        name: t('audit_logs_title'),
        isActive: pathname.startsWith('/audit-logs'),
        icon: navIcon(<FileTextOutlined />),
        path: '/audit-logs',
      }] : []),
      ...(hasPermission('system', 'admin') ? [{
        key: 'vis_merge_test',
        name: 'GUI',
        isActive: pathname.startsWith('/vis-merge-test'),
        icon: navIcon(<DesktopOutlined />),
        path: '/vis-merge-test',
      }] : []),
    ];

    return [
      { key: 'main', label: '', icon: null, items: mainItems, defaultOpen: true, flat: true },
      { key: 'capability', label: t('capability'), icon: navIcon(<ThunderboltOutlined />), items: capabilityItems, defaultOpen: false },
      { key: 'assets', label: t('assets'), icon: navIcon(<DatabaseOutlined />), items: assetItems, defaultOpen: false },
      { key: 'settings', label: t('settings_group'), icon: navIcon(<SettingOutlined />), items: settingItems, defaultOpen: false },
    ].filter(s => s.items.length > 0);
  }, [t, pathname, hasResourceRead, hasPermission]);

  useEffect(() => {
    const language = i18n.language;
    if (language === 'zh') moment.locale('zh-cn');
    if (language === 'en') moment.locale('en');
  }, []);

  useEffect(() => {
    setLogo(mode === 'dark' ? '/logo_s_latest.png' : '/logo_zh_latest.png');
  }, [mode]);

  const handleSearch = (value: string) => {
    setSearchValue(value);
    if (value.trim()) {
      fetchDialogueList(value);
    } else {
      if (dialogueList && dialogueList[1]) {
        const di = (dialogueList[1] as unknown as Dialogue[]).map(
          (dialogue: Dialogue): DialogueListItem => ({
            key: dialogue?.conv_uid,
            name: extractUserText(dialogue.user_input) || dialogue.select_param,
            path: '/assistant',
            dialogue: dialogue,
          }),
        );
        setDialogueLists(dedupByConvUid(di));
      }
    }
  };

  const getWeekRange = (date: string) => {
    const m = moment(date);
    const startOfWeek = m.clone().startOf('week');
    const endOfWeek = m.clone().endOf('week');
    const now = moment();
    
    if (now.isSame(startOfWeek, 'week')) {
      return t('this_week');
    }
    if (now.clone().subtract(1, 'week').isSame(startOfWeek, 'week')) {
      return t('last_week');
    }
    
    const weeksAgo = Math.floor(now.diff(startOfWeek, 'weeks'));
    return `${weeksAgo} ${t('weeks_ago')}`;
  };

  // 去重:同一 conv_uid 只保留最后活动时间最新的一条(防御后端偶发重复)
  const dedupByConvUid = (items: DialogueListItem[]): DialogueListItem[] => {
    const map = new Map<string, DialogueListItem>();
    for (const item of items) {
      const key = item.dialogue.conv_uid;
      if (!key) {
        map.set(`__no_key_${map.size}`, item);
        continue;
      }
      const prev = map.get(key);
      if (!prev) {
        map.set(key, item);
        continue;
      }
      const prevTime = prev.dialogue.gmt_modified || prev.dialogue.gmt_created || '';
      const curTime = item.dialogue.gmt_modified || item.dialogue.gmt_created || '';
      if (curTime > prevTime) {
        map.set(key, item);
      }
    }
    return Array.from(map.values());
  };

  const groupDialoguesByWeek = (dialogues: DialogueListItem[]): GroupedDialogues => {
    return dialogues.reduce((groups, item) => {
      const date = item.dialogue.gmt_modified || item.dialogue.gmt_created;
      if (date) {
        const weekRange = getWeekRange(date);
        if (!groups[weekRange]) {
          groups[weekRange] = [];
        }
        groups[weekRange].push(item);
      } else {
        if (!groups[t('unknown')]) {
          groups[t('unknown')] = [];
        }
        groups[t('unknown')].push(item);
      }
      return groups;
    }, {} as GroupedDialogues);
  };

  // Sort items within each group by last activity time descending
  const sortGroupedDialogues = (grouped: GroupedDialogues): GroupedDialogues => {
    const sorted: GroupedDialogues = {};
    for (const [key, items] of Object.entries(grouped)) {
      sorted[key] = [...items].sort((a, b) => {
        const aTime = a.dialogue.gmt_modified || a.dialogue.gmt_created || '';
        const bTime = b.dialogue.gmt_modified || b.dialogue.gmt_created || '';
        return bTime.localeCompare(aTime);
      });
    }
    return sorted;
  };

  const renderGroupedDialogues = (dialogues: DialogueListItem[]) => {
    const grouped = groupDialoguesByWeek(dialogues);
    const sorted = sortGroupedDialogues(grouped);

    // 按时间顺序排列分组：本周 > 上周 > X周前 > 未知
    const sortedGroups = Object.entries(sorted).sort((a, b) => {
      const thisWeekKey = t('this_week');
      const lastWeekKey = t('last_week');
      const weeksAgoKey = t('weeks_ago');
      const unknownKey = t('unknown');

      // 获取分组的排序权重
      const getGroupOrder = (groupName: string): number => {
        if (groupName === thisWeekKey) return 1;
        if (groupName === lastWeekKey) return 2;
        // 处理 "X 周前" 或 "X weeks ago" 格式
        if (groupName.includes(weeksAgoKey)) {
          // 提取数字，数字越大（周数越早），排序越靠后
          const match = groupName.match(/\d+/);
          const weeksNum = match ? parseInt(match[0], 10) : 999;
          return 3 + weeksNum;
        }
        if (groupName === unknownKey) return 9999;
        return 9998; // 其他未知分组
      };

      return getGroupOrder(a[0]) - getGroupOrder(b[0]);
    });

    return sortedGroups.map(([week, items], index) => (
      <div key={`group-${index}`} className="mb-4">
        <div className="flex items-center px-3 mb-2">
          <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">
            {week}
          </span>
        </div>
        {items.map((item) => (
          <MenuItem
            key={item.key}
            item={{
              label: item.name || 'Untitled',
              app_code: item.dialogue.app_code || '',
              ...item.dialogue,
              default: false,
            }}
            order={{ current: 0 }}
          />
        ))}
      </div>
    ));
  };

  // if (pathname === '/') return null;

  if (!isMenuExpand) {
    return (
      <div className='flex flex-col justify-between items-center pt-3 h-screen w-[64px] bg-[#f7f8fa] dark:bg-[#111] animate-fade animate-duration-300'>
        <div className='flex flex-col items-center'>
          <Link
            href='/'
            className='flex justify-center items-center w-11 h-11 mb-2 mt-0.5 rounded-[14px] bg-white dark:bg-[#232734] shadow-[0_1px_3px_rgba(16,24,40,0.08)] hover:shadow-[0_4px_12px_rgba(16,24,40,0.12)] transition-shadow'
          >
            <Image src='/LOGO_SMALL.png' alt='DeRisk' width={24} height={24} className='object-contain' />
          </Link>
          <div className='flex flex-col gap-1.5 items-center px-2'>
            {navSections.map(section => {
              // 一级单项(智能体空间/场景空间):直接是图标链接
              if ((section as any).flat) {
                return section.items.map(item => (
                  <Tooltip key={item.key} title={item.name} placement='right'>
                    <Link
                      className={cls(
                        'h-10 w-10 flex items-center justify-center rounded-xl transition-colors text-[#8a92a6] hover:bg-[#f2f4f8] hover:text-[#3b4154] dark:hover:bg-gray-800',
                        item.isActive && 'bg-[#e9eaee] text-[#3b4154]'
                      )}
                      href={item.path || '#'}
                    >
                      {item.icon}
                    </Link>
                  </Tooltip>
                ));
              }
              // 分组: hover 显示子菜单(带图标),点击展开侧边栏
              const anyActive = section.items.some(i => i.isActive);
              return (
                <Popover
                  key={section.key}
                  placement='right'
                  trigger='hover'
                  overlayInnerStyle={{ padding: 4 }}
                  content={
                    <div className='flex flex-col gap-0.5 min-w-[168px]'>
                      <div className='px-2.5 py-1.5 text-xs font-medium text-gray-400 dark:text-gray-500'>
                        {section.label}
                      </div>
                      {section.items.map(item => (
                        <Link
                          key={item.key}
                          href={item.path ?? '/'}
                          className={cls(
                            'flex items-center h-8 px-2.5 rounded-md transition-colors text-[13px]',
                            item.isActive
                              ? 'bg-[#f2f4f8] dark:bg-gray-700 text-[#14161c] dark:text-white font-medium'
                              : 'text-[#3b4154] dark:text-gray-300 hover:bg-[#f2f4f8] dark:hover:bg-gray-800'
                          )}
                        >
                          <span className='mr-2.5 flex items-center justify-center flex-shrink-0 text-[#5d6577] dark:text-gray-400'>
                            {item.icon}
                          </span>
                          <span className='truncate'>{item.name}</span>
                        </Link>
                      ))}
                    </div>
                  }
                >
                  <div
                    className={cls(
                      'h-10 w-10 flex items-center justify-center rounded-xl cursor-pointer transition-colors text-[#8a92a6] hover:bg-[#f2f4f8] hover:text-[#3b4154] dark:hover:bg-gray-800',
                      anyActive && 'bg-[#e9eaee] text-[#3b4154]'
                    )}
                    onClick={() => {
                      setClosedSections(prev => ({ ...prev, [section.key]: false }));
                      setIsMenuExpand(true);
                    }}
                  >
                    {(section as any).icon}
                  </div>
                </Popover>
              );
            })}
          </div>
        </div>
        <div className='py-4 flex flex-col items-center gap-1.5'>
          <UserBar onlyAvatar />
          {settings
            .filter(item => item.noDropdownItem)
            .map(item => (
              <Tooltip key={item.key} title={item.name} placement='right'>
                <div className='w-10 h-10 flex items-center justify-center hover:bg-[#f2f4f8] dark:hover:bg-gray-800 rounded-xl cursor-pointer transition-colors' onClick={item.onClick}>
                  {item.icon}
                </div>
              </Tooltip>
            ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cls(
        'flex flex-col justify-between flex-1 pt-3 overflow-hidden h-screen',
        'bg-[#f7f8fa] dark:bg-[#111]',
        'animate-fade animate-duration-300 max-w-[260px] w-[260px]',
      )}
    >
      <div className='flex flex-col w-full px-4 shrink-0'>
        {/* LOGO */}
        <Link href='/' className='flex flex-row justify-between items-center mb-4 pl-1'>
          <Image src={isMenuExpand ? logo : '/LOGO_SMALL.png'} alt='DB-GPT' width={120} height={30} className="object-contain" />
        </Link>

        </div>

      <div className="flex-1 min-h-0 flex flex-col px-4">
        <div className='flex-1 min-h-0 overflow-y-auto -mx-2 px-2 custom-scrollbar pr-1'>
        {/* Navigation Menu — 一级分组:Agent / 场景空间 / 资源 / 设置 */}
        <nav className='flex flex-col w-full mb-4'>
          {navSections.map((section) => {
            const linkCls = (active?: boolean) => cls(
              'flex items-center w-full h-8 cursor-pointer px-2.5 rounded-lg transition-all duration-150',
              active
                ? 'bg-[#e9eaee] dark:bg-gray-800 text-[#14161c] dark:text-white font-medium'
                : 'text-[#3b4154] dark:text-gray-400 hover:bg-[#efeff1] dark:hover:bg-gray-800'
            );
            const iconCls = (active?: boolean) => cls(
              'mr-2.5 flex items-center justify-center flex-shrink-0',
              active ? 'text-[#3b4154]' : 'text-[#5d6577]'
            );

            // 场景空间等一级单项:直接渲染
            if ((section as any).flat) {
              return section.items.map(item => (
                <Link href={item.path ?? '/'} className={cls(linkCls(item.isActive), 'h-9 px-3')} key={item.key}>
                  <span className={iconCls(item.isActive)}>{item.icon}</span>
                  <span className='text-[13px] truncate'>{item.name}</span>
                </Link>
              ));
            }

            const anyActive = section.items.some(i => i.isActive);
            const open = closedSections[section.key] !== undefined
              ? !closedSections[section.key]
              : (section as any).defaultOpen || anyActive;

            return (
              <div key={section.key} className='mb-1'>
                {/* 分组头:一级分类,可折叠 */}
                <div
                  className='flex items-center w-full h-9 px-3 rounded-lg cursor-pointer select-none hover:bg-[#efeff1] dark:hover:bg-gray-800 transition-colors group/nav'
                  onClick={() => setClosedSections(prev => ({ ...prev, [section.key]: open }))}
                >
                  <span className={cls('mr-2.5 flex items-center justify-center flex-shrink-0', anyActive ? 'text-[#3b4154]' : 'text-[#5d6577]')}>
                    {(section as any).icon}
                  </span>
                  <span className={cls('text-[13px] truncate flex-1', anyActive ? 'font-semibold text-[#14161c]' : 'font-medium text-[#14161c]')}>
                    {section.label}
                  </span>
                  <RightOutlined className={cls(
                    'text-[9px] text-[#b4bac8] group-hover/nav:text-[#8a92a6] transition-transform duration-200',
                    open && 'rotate-90'
                  )} />
                </div>
                {/* 子项:带图标与引导线缩进 */}
                {open && (
                  <div className='flex flex-col gap-0.5 ml-[21px] pl-2.5 mt-0.5 mb-1 border-l border-[#eff1f6] dark:border-gray-800'>
                    {section.items.map(item => (
                      <Link href={item.path ?? '/'} className={cls(linkCls(item.isActive), 'h-9 px-3')} key={item.key}>
                        <span className={iconCls(item.isActive)}>{item.icon}</span>
                        <span className='text-[13px] truncate'>{item.name}</span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Chat History Header */}
        <div className="flex items-center justify-between text-[11px] font-medium tracking-wider text-[#8a92a6] mb-1.5 px-3">
           <span>{t('chat_history')}</span>
           <Tooltip title='⌘K' placement='left'>
             <SearchOutlined
               className="cursor-pointer text-[#b4bac8] hover:text-[#5d6577] transition-colors"
               onClick={() => window.dispatchEvent(new Event('open-command-palette'))}
             />
           </Tooltip>
        </div>

        {listLoading ? (
          Array.from({ length: 3 }).map((_, index) => (
            <MenuItem
              key={`loading-${index}`}
              item={{}}
              order={{ current: 0 }}
              loading={true}
            />
          ))
        ) : dialogueLists.length > 0 ? (
          renderGroupedDialogues(dialogueLists)
        ) : (
          <div className='px-4 text-gray-400 text-xs py-4 text-center'>
            {searchValue ? t('no_matching_session') : t('no_history_session')}
          </div>
        )}
        </div>
      </div>

      {/* User & Settings */}
      <div className='px-4 py-4 mt-2 border-t border-[#eff1f6] dark:border-gray-800 bg-[#f7f8fa] dark:bg-[#111] flex items-center justify-between gap-2'>
        <div className='flex-1 min-w-0 overflow-hidden'>
           <UserBar />
        </div>
        <div className='flex items-center gap-1 shrink-0'>
          {settings.map(item => (
            <Tooltip key={item.key} title={item.name} placement='top'>
              <div 
                className={cls(
                  'w-8 h-8 flex items-center justify-center rounded-lg cursor-pointer transition-colors text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800', 
                  { 'text-gray-300 cursor-not-allowed': item.disable }
                )} 
                onClick={item.onClick}
              >
                {item.icon}
              </div>
            </Tooltip>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SideBar;
