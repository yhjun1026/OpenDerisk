'use client';

import { useEffect, useMemo, useState, useCallback } from 'react';
import { apiInterceptors, validateCron } from '@/client/api';
import {
  Card, Input, InputNumber, Radio, Segmented, Spin, Tag, Typography, TimePicker, App,
} from 'antd';
import {
  CalendarOutlined, ReloadOutlined, CheckOutlined, CodeOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text } = Typography;

const WEEKDAYS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 0, label: '周日' },
];

const PRESETS = [
  { label: '每天 09:00', expr: '0 9 * * *', mode: 'daily' as const, hour: 9, minute: 0 },
  { label: '工作日 09:00', expr: '0 9 * * 1-5', mode: 'weekly' as const, hour: 9, minute: 0, weekdays: [1, 2, 3, 4, 5] },
  { label: '每周一 09:00', expr: '0 9 * * 1', mode: 'weekly' as const, hour: 9, minute: 0, weekdays: [1] },
  { label: '每月 1 日 09:00', expr: '0 9 1 * *', mode: 'monthly' as const, hour: 9, minute: 0, monthDays: [1] },
  { label: '每小时', expr: '0 * * * *', mode: 'interval' as const, intervalMinutes: 60 },
  { label: '每 30 分钟', expr: '*/30 * * * *', mode: 'interval' as const, intervalMinutes: 30 },
  { label: '每 10 分钟', expr: '*/10 * * * *', mode: 'interval' as const, intervalMinutes: 10 },
  { label: '每 5 分钟', expr: '*/5 * * * *', mode: 'interval' as const, intervalMinutes: 5 },
];

interface CronEditorProps {
  value?: string;
  onChange?: (expr: string) => void;
  tz?: string;
}

type CustomMode = 'daily' | 'weekly' | 'monthly' | 'interval';
type EditorMode = 'visual' | 'advanced';

function pad(n: number) {
  return String(n).padStart(2, '0');
}

function describeExpr(expr: string): string {
  const preset = PRESETS.find(p => p.expr === expr);
  if (preset) return preset.label;

  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return `自定义 (${expr})`;
  const [min, hour, day, month, week] = parts;
  if (month !== '*') return `自定义 (${expr})`;

  const time = (h: string, m: string) => {
    const hh = pad(parseInt(h) || 0);
    const mm = pad(parseInt(m) || 0);
    return `${hh}:${mm}`;
  };

  if (min.startsWith('*/') && hour === '*' && day === '*' && week === '*') {
    return `每 ${min.slice(2)} 分钟执行一次`;
  }
  if (day === '*' && week === '*') {
    return `每天 ${time(hour, min)} 执行`;
  }
  if (day === '*' && week !== '*') {
    const days = week.split(',').map(n => WEEKDAYS.find(w => w.value === Number(n))?.label).filter(Boolean);
    return `${days.join('、')} ${time(hour, min)} 执行`;
  }
  if (day !== '*' && week === '*') {
    return `每月 ${day.split(',').join('、')} 日 ${time(hour, min)} 执行`;
  }
  return `自定义 (${expr})`;
}

interface ParsedState {
  mode: CustomMode;
  hour: number;
  minute: number;
  weekdays: number[];
  monthDays: number[];
  intervalMinutes: number;
}

function parseExpression(expr: string): ParsedState | null {
  const preset = PRESETS.find(p => p.expr === expr);
  if (preset) {
    return {
      mode: preset.mode,
      hour: preset.hour ?? 9,
      minute: preset.minute ?? 0,
      weekdays: preset.weekdays ?? [1],
      monthDays: preset.monthDays ?? [1],
      intervalMinutes: preset.intervalMinutes ?? 30,
    };
  }

  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return null;
  const [minPart, hourPart, dayPart, monthPart, weekPart] = parts;
  if (monthPart !== '*') return null;

  // 每隔 N 分钟
  if (minPart.startsWith('*/') && hourPart === '*' && dayPart === '*' && weekPart === '*') {
    const n = parseInt(minPart.slice(2));
    if (!isNaN(n)) {
      return { mode: 'interval', hour: 9, minute: 0, weekdays: [1], monthDays: [1], intervalMinutes: n };
    }
  }

  // 每天
  if (dayPart === '*' && weekPart === '*') {
    const m = parseInt(minPart);
    const h = parseInt(hourPart);
    if (!isNaN(m) && !isNaN(h)) {
      return { mode: 'daily', hour: h, minute: m, weekdays: [1], monthDays: [1], intervalMinutes: 30 };
    }
  }

  // 每周
  if (dayPart === '*' && weekPart !== '*') {
    const m = parseInt(minPart);
    const h = parseInt(hourPart);
    const days = weekPart.split(',').map(Number).filter(n => !isNaN(n));
    if (!isNaN(m) && !isNaN(h) && days.length) {
      return { mode: 'weekly', hour: h, minute: m, weekdays: days, monthDays: [1], intervalMinutes: 30 };
    }
  }

  // 每月
  if (dayPart !== '*' && weekPart === '*') {
    const m = parseInt(minPart);
    const h = parseInt(hourPart);
    const days = dayPart.split(',').map(Number).filter(n => !isNaN(n));
    if (!isNaN(m) && !isNaN(h) && days.length) {
      return { mode: 'monthly', hour: h, minute: m, weekdays: [1], monthDays: days, intervalMinutes: 30 };
    }
  }

  return null;
}

export default function CronEditor({ value = '', onChange, tz = 'Asia/Shanghai' }: CronEditorProps) {
  const { message } = App.useApp();
  const [editorMode, setEditorMode] = useState<EditorMode>('visual');
  const [mode, setMode] = useState<CustomMode>('daily');
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [weekdays, setWeekdays] = useState<number[]>([1]);
  const [monthDays, setMonthDays] = useState<number[]>([1]);
  const [intervalMinutes, setIntervalMinutes] = useState(30);
  const [rawExpr, setRawExpr] = useState(value || '0 9 * * *');
  const [nextRuns, setNextRuns] = useState<string[]>([]);
  const [validating, setValidating] = useState(false);

  const expr = useMemo(() => {
    if (editorMode === 'advanced') return rawExpr.trim();

    const m = pad(minute);
    const h = pad(hour);
    switch (mode) {
      case 'daily':
        return `${m} ${h} * * *`;
      case 'weekly': {
        if (!weekdays.length) return `${m} ${h} * * 1`;
        const sorted = [...weekdays].sort((a, b) => a - b);
        return `${m} ${h} * * ${sorted.join(',')}`;
      }
      case 'monthly': {
        if (!monthDays.length) return `${m} ${h} 1 * *`;
        const sorted = [...monthDays].sort((a, b) => a - b);
        return `${m} ${h} ${sorted.join(',')} * *`;
      }
      case 'interval': {
        const n = Math.max(1, Math.min(60, intervalMinutes || 1));
        return `*/${n} * * * *`;
      }
      default:
        return value || '0 9 * * *';
    }
  }, [editorMode, rawExpr, mode, hour, minute, weekdays, monthDays, intervalMinutes, value]);

  // 外部 value 变化时同步到 UI
  useEffect(() => {
    if (!value) return;
    const parsed = parseExpression(value);
    if (!parsed) {
      setEditorMode('advanced');
      setRawExpr(value);
      return;
    }
    setEditorMode('visual');
    setMode(parsed.mode);
    setHour(parsed.hour);
    setMinute(parsed.minute);
    setWeekdays(parsed.weekdays);
    setMonthDays(parsed.monthDays);
    setIntervalMinutes(parsed.intervalMinutes);
  }, [value]);

  // expr 变化：上报 + debounce 校验下次执行时间
  useEffect(() => {
    onChange?.(expr);
    const t = setTimeout(async () => {
      setValidating(true);
      const [err, data] = await apiInterceptors(validateCron(expr, tz));
      setValidating(false);
      if (!err && data?.valid) setNextRuns(data.next_runs || []);
      else setNextRuns([]);
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expr, tz]);

  const applyPreset = (preset: typeof PRESETS[number]) => {
    setEditorMode('visual');
    setMode(preset.mode);
    setHour(preset.hour ?? 9);
    setMinute(preset.minute ?? 0);
    setWeekdays(preset.weekdays ?? [1]);
    setMonthDays(preset.monthDays ?? [1]);
    setIntervalMinutes(preset.intervalMinutes ?? 30);
  };

  const isPresetActive = (preset: typeof PRESETS[number]) => preset.expr === expr;

  const toggleWeekday = (day: number) => {
    setWeekdays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day].sort((a, b) => a - b));
  };

  const toggleMonthDay = (day: number) => {
    setMonthDays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day].sort((a, b) => a - b));
  };

  const handleEditorModeChange = useCallback((next: EditorMode) => {
    if (next === 'advanced') {
      setRawExpr(expr);
      setEditorMode('advanced');
      return;
    }
    const parsed = parseExpression(rawExpr.trim() || expr);
    if (!parsed) {
      message.warning('当前表达式较复杂，可视化模式无法展示，请继续使用表达式模式');
      return;
    }
    setMode(parsed.mode);
    setHour(parsed.hour);
    setMinute(parsed.minute);
    setWeekdays(parsed.weekdays);
    setMonthDays(parsed.monthDays);
    setIntervalMinutes(parsed.intervalMinutes);
    setEditorMode('visual');
  }, [expr, rawExpr]);

  return (
    <div className="space-y-5">
      {/* 模式切换 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <CalendarOutlined className="text-[var(--ws-accent)]" />
          <span className="text-sm font-semibold text-[var(--ws-ink)]">定时配置</span>
        </div>
        <Segmented
          value={editorMode}
          onChange={(v) => handleEditorModeChange(v as EditorMode)}
          options={[
            { value: 'visual', label: <span className="flex items-center gap-1"><CalendarOutlined /> 可视化</span> },
            { value: 'advanced', label: <span className="flex items-center gap-1"><CodeOutlined /> 表达式</span> },
          ]}
          size="small"
        />
      </div>

      {editorMode === 'visual' ? (
        <>
          {/* 快捷配置 */}
          <div>
            <div className="text-xs text-[var(--ws-ink-3)] mb-2">快捷配置</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {PRESETS.map(preset => {
                const active = isPresetActive(preset);
                return (
                  <button
                    key={preset.expr}
                    type="button"
                    onClick={() => applyPreset(preset)}
                    className={`relative text-left rounded-xl border px-3 py-3 transition-all duration-200 ${active ? 'bg-[var(--ws-accent-light)] border-[var(--ws-accent)] ring-1 ring-[var(--ws-accent)]/20' : 'bg-[var(--ws-surface)] border-[var(--ws-border)] hover:border-[var(--ws-accent)]/40 hover:shadow-sm'}`}
                  >
                    {active && (
                      <span className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-[var(--ws-accent)] text-white flex items-center justify-center text-[10px]">
                        <CheckOutlined />
                      </span>
                    )}
                    <div className={`text-sm font-medium ${active ? 'text-[var(--ws-accent)]' : 'text-[var(--ws-ink)]'}`}>
                      {preset.label}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 自定义 */}
          <div className="bg-[var(--ws-border-subtle)] rounded-xl p-4 border border-[var(--ws-border)]">
            <div className="text-xs text-[var(--ws-ink-3)] mb-3">自定义</div>
            <Radio.Group
              value={mode}
              onChange={e => setMode(e.target.value as CustomMode)}
              optionType="button"
              buttonStyle="solid"
              size="small"
            >
              <Radio.Button value="daily">每天</Radio.Button>
              <Radio.Button value="weekly">每周</Radio.Button>
              <Radio.Button value="monthly">每月</Radio.Button>
              <Radio.Button value="interval">每隔</Radio.Button>
            </Radio.Group>

            <div className="mt-4">
              {(mode === 'daily' || mode === 'weekly' || mode === 'monthly') && (
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-sm text-[var(--ws-ink-2)]">时间</span>
                  <TimePicker
                    value={dayjs().hour(hour).minute(minute)}
                    format="HH:mm"
                    onChange={time => {
                      if (!time) return;
                      setHour(time.hour());
                      setMinute(time.minute());
                    }}
                  />
                </div>
              )}

              {mode === 'weekly' && (
                <div className="mt-4">
                  <span className="text-sm text-[var(--ws-ink-2)] block mb-2">选择星期</span>
                  <div className="flex flex-wrap gap-2">
                    {WEEKDAYS.map(d => (
                      <button
                        key={d.value}
                        type="button"
                        onClick={() => toggleWeekday(d.value)}
                        className={`min-w-[52px] px-3 py-1.5 rounded-lg text-sm border transition-all ${weekdays.includes(d.value) ? 'bg-[var(--ws-accent)] text-white border-[var(--ws-accent)]' : 'bg-[var(--ws-surface)] text-[var(--ws-ink-2)] border-[var(--ws-border)] hover:border-[var(--ws-accent)]/40'}`}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {mode === 'monthly' && (
                <div className="mt-4">
                  <span className="text-sm text-[var(--ws-ink-2)] block mb-2">选择日期</span>
                  <div className="grid grid-cols-7 gap-2">
                    {Array.from({ length: 31 }, (_, i) => i + 1).map(day => (
                      <button
                        key={day}
                        type="button"
                        onClick={() => toggleMonthDay(day)}
                        className={`h-8 rounded-lg text-sm border transition-all ${monthDays.includes(day) ? 'bg-[var(--ws-accent)] text-white border-[var(--ws-accent)]' : 'bg-[var(--ws-surface)] text-[var(--ws-ink-2)] border-[var(--ws-border)] hover:border-[var(--ws-accent)]/40'}`}
                      >
                        {day}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {mode === 'interval' && (
                <div className="flex items-center gap-3 mt-4">
                  <span className="text-sm text-[var(--ws-ink-2)]">每隔</span>
                  <InputNumber
                    min={1}
                    max={60}
                    value={intervalMinutes}
                    onChange={v => setIntervalMinutes(v ?? 1)}
                    className="w-24"
                  />
                  <span className="text-sm text-[var(--ws-ink-2)]">分钟执行一次</span>
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        /* 表达式模式 */
        <div className="bg-[var(--ws-border-subtle)] rounded-xl p-4 border border-[var(--ws-border)]">
          <div className="text-xs text-[var(--ws-ink-3)] mb-2">Cron 表达式（分 时 日 月 周）</div>
          <Input
            value={rawExpr}
            onChange={e => setRawExpr(e.target.value)}
            placeholder="0 9 * * *"
            className="font-mono"
          />
          <div className="mt-2 text-xs text-[var(--ws-ink-3)] leading-relaxed">
            例如：每天 09:00 为 <code>0 9 * * *</code>；每周一 09:00 为 <code>0 9 * * 1</code>；每 10 分钟为 <code>*/10 * * * *</code>
          </div>
        </div>
      )}

      {/* 执行预览 */}
      <Card
        size="small"
        className="rounded-xl border-[var(--ws-border)]"
        bodyStyle={{ background: 'var(--ws-surface)' }}
        title={
          <span className="flex items-center gap-1.5 text-sm">
            <ReloadOutlined className="text-[var(--ws-accent)]" />
            执行预览
          </span>
        }
      >
        <div className="mb-3">
          <Tag color="blue" className="!mb-0">{describeExpr(expr)}</Tag>
        </div>
        <div className="flex items-center gap-2 mb-2">
          <Text type="secondary" className="text-xs shrink-0 w-12">表达式</Text>
          <code className="text-xs text-[var(--ws-ink)] font-mono bg-[var(--ws-border-subtle)] px-2 py-1 rounded">{expr}</code>
        </div>
        <div className="flex items-start gap-2">
          <Text type="secondary" className="text-xs shrink-0 w-12 mt-0.5">下次执行</Text>
          {validating ? (
            <Spin size="small" />
          ) : nextRuns.length ? (
            <div className="flex flex-wrap gap-1">
              {nextRuns.slice(0, 5).map((r, i) => (
                <Tag key={i} className="text-xs">{r.replace('T', ' ').slice(0, 16)}</Tag>
              ))}
            </div>
          ) : (
            <Text type="secondary" className="text-xs">输入合法表达式后显示</Text>
          )}
        </div>
      </Card>
    </div>
  );
}
