'use client';

import { ChatContext } from '@/contexts';
import {
  ClockCircleOutlined,
  CompassOutlined,
  ConsoleSqlOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  MessageOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  BookOutlined,
} from '@ant-design/icons';
import cls from 'classnames';
import { useRouter } from 'next/navigation';
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * ⌘K 命令面板 — Raycast 式全局跳转。
 * 数据源:静态页面清单 + ChatContext 中的最近会话。
 */

interface CommandItem {
  key: string;
  group: 'page' | 'chat';
  label: string;
  hint?: string;
  icon: React.ReactNode;
  action: () => void;
}

const ICON_CLS = 'text-[14px]';

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const { t } = useTranslation();
  const { dialogueList } = useContext(ChatContext);

  // 全局快捷键:⌘K / Ctrl+K 切换,Esc 关闭;侧边栏搜索按钮通过事件唤起
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery('');
        setActiveIndex(0);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    const openHandler = () => {
      setOpen(true);
      setQuery('');
      setActiveIndex(0);
    };
    window.addEventListener('keydown', handler);
    window.addEventListener('open-command-palette', openHandler);
    return () => {
      window.removeEventListener('keydown', handler);
      window.removeEventListener('open-command-palette', openHandler);
    };
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
  }, [open]);

  const go = useCallback(
    (path: string) => {
      setOpen(false);
      router.push(path);
    },
    [router],
  );

  const pages: CommandItem[] = useMemo(
    () => [
      { key: 'explore', group: 'page', label: t('agent_space'), icon: <CompassOutlined className={ICON_CLS} />, action: () => go('/application/explore') },
      { key: 'agents', group: 'page', label: t('Agents'), icon: <RobotOutlined className={ICON_CLS} />, action: () => go('/application/app') },
      { key: 'workspaces', group: 'page', label: t('workspaces') || 'Workspaces', icon: <TeamOutlined className={ICON_CLS} />, action: () => go('/workspaces') },
      { key: 'knowledge', group: 'page', label: t('knowledge_base'), icon: <BookOutlined className={ICON_CLS} />, action: () => go('/knowledge-vault') },
      { key: 'database', group: 'page', label: t('Database'), icon: <DatabaseOutlined className={ICON_CLS} />, action: () => go('/database') },
      { key: 'skills', group: 'page', label: t('agent_skills'), icon: <ThunderboltOutlined className={ICON_CLS} />, action: () => go('/agent-skills') },
      { key: 'mcp', group: 'page', label: 'MCP', icon: <ConsoleSqlOutlined className={ICON_CLS} />, action: () => go('/mcp') },
      { key: 'models', group: 'page', label: t('model_manage'), icon: <DashboardOutlined className={ICON_CLS} />, action: () => go('/models') },
      { key: 'cron', group: 'page', label: t('cron_page_title'), icon: <ClockCircleOutlined className={ICON_CLS} />, action: () => go('/cron') },
      { key: 'settings', group: 'page', label: t('system_config'), icon: <SettingOutlined className={ICON_CLS} />, action: () => go('/settings/config') },
    ],
    [t, go],
  );

  const chats: CommandItem[] = useMemo(() => {
    const raw = (dialogueList?.[1] as unknown as Array<Record<string, string>>) || [];
    return raw.slice(0, 30).map((d) => {
      let name = d.user_input || d.select_param || 'Untitled';
      if (name.startsWith('{')) {
        try {
          const obj = JSON.parse(name);
          name = obj.data?.content || obj.content || name;
          if (typeof name !== 'string') name = JSON.stringify(name);
        } catch { /* keep raw */ }
      }
      return {
        key: d.conv_uid,
        group: 'chat' as const,
        label: name,
        hint: d.app_code,
        icon: <MessageOutlined className={ICON_CLS} />,
        action: () => go(`/chat/?conv_uid=${d.conv_session_id || d.conv_uid}&app_code=${d.app_code || ''}`),
      };
    });
  }, [dialogueList, go]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (item: CommandItem) =>
      !q || item.label.toLowerCase().includes(q) || item.hint?.toLowerCase().includes(q);
    const matchedPages = pages.filter(match);
    const matchedChats = chats.filter(match).slice(0, q ? 8 : 5);
    return [...matchedPages, ...matchedChats];
  }, [pages, chats, query]);

  useEffect(() => setActiveIndex(0), [query]);

  // 键盘导航
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        filtered[activeIndex]?.action();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, filtered, activeIndex]);

  // 激活项滚动可见
  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-idx="${activeIndex}"]`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (!open) return null;

  let lastGroup: string | null = null;

  return (
    <div
      className='fixed inset-0 z-[1000] flex items-start justify-center pt-[16vh] bg-black/20 backdrop-blur-[2px]'
      onClick={() => setOpen(false)}
    >
      <div
        className='w-[560px] max-w-[92vw] glass-panel rounded-2xl border border-[#eeeff3] shadow-[0_24px_80px_rgba(16,24,40,0.2)] overflow-hidden animate-rise'
        style={{ animationDuration: '0.25s' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 搜索输入 */}
        <div className='flex items-center gap-3 px-4 h-[52px] border-b border-[#eff1f6]'>
          <SearchOutlined className='text-[#8a92a6] text-[15px]' />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('command_palette_placeholder') || '搜索页面、会话…'}
            className='flex-1 bg-transparent outline-none text-[15px] text-[#14161c] placeholder:text-[#b4bac8]'
          />
          <kbd className='text-[10px] text-[#8a92a6] bg-[#f2f4f8] rounded px-1.5 py-0.5 font-mono'>ESC</kbd>
        </div>

        {/* 结果列表 */}
        <div ref={listRef} className='max-h-[46vh] overflow-y-auto py-2'>
          {filtered.length === 0 && (
            <div className='py-10 text-center text-[13px] text-[#8a92a6]'>
              {t('no_matching_session') || '无匹配结果'}
            </div>
          )}
          {filtered.map((item, idx) => {
            const showGroup = item.group !== lastGroup;
            lastGroup = item.group;
            return (
              <div key={`${item.group}-${item.key}`}>
                {showGroup && (
                  <div className='px-4 pt-2 pb-1 text-[11px] font-medium tracking-wider text-[#8a92a6]'>
                    {item.group === 'page' ? (t('command_palette_pages') || '页面') : (t('chat_history') || '会话')}
                  </div>
                )}
                <div
                  data-idx={idx}
                  onClick={item.action}
                  onMouseEnter={() => setActiveIndex(idx)}
                  className={cls(
                    'flex items-center gap-3 mx-2 px-3 h-10 rounded-lg cursor-pointer transition-colors',
                    idx === activeIndex ? 'bg-[#efeff1]' : '',
                  )}
                >
                  <span className='text-[#8a92a6] w-5 flex justify-center'>{item.icon}</span>
                  <span className='flex-1 text-[13px] text-[#3b4154] truncate'>{item.label}</span>
                  {item.hint && <span className='text-[11px] text-[#b4bac8] font-mono'>{item.hint}</span>}
                  {idx === activeIndex && (
                    <kbd className='text-[10px] text-[#8a92a6] bg-white rounded px-1.5 py-0.5 font-mono shadow-sm'>↵</kbd>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* 底部提示 */}
        <div className='flex items-center gap-4 px-4 h-9 border-t border-[#eff1f6] text-[11px] text-[#b4bac8]'>
          <span>↑↓ 选择</span>
          <span>↵ 打开</span>
          <span className='ml-auto font-mono'>⌘K</span>
        </div>
      </div>
    </div>
  );
}
