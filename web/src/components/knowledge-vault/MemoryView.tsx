'use client';

import { apiInterceptors } from '@/client/api';
import { getCurateReport, listDocs, listVerbats } from '@/client/api/knowledge-vault';
import type { CurateReport, DocMeta, VerbatOut } from '@/types/knowledge-vault';
import { Empty, Spin, Tag, Tooltip, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useSpace } from './SpaceContext';

/** L1 doc types that count as refined memory (tier2/tier3 output). */
const MEMORY_DOC_TYPES = new Set(['memory', 'insight', 'preference']);

const DOC_TYPE_COLOR: Record<string, string> = {
  memory: 'blue',
  insight: 'purple',
  preference: 'green',
};

function fmtDate(s?: string | null) {
  if (!s) return '-';
  // backend returns "YYYY-MM-DDTHH:MM:SS"
  return s.replace('T', ' ').slice(0, 19);
}

function metaStr(v: VerbatOut, key: string): string {
  const val = v.metadata?.[key];
  return val == null ? '' : String(val);
}

/**
 * Memory-space view: L0 conversation timeline (grouped by conv_id),
 * refined L1 memory docs, and the latest tier3 curate REPORT.md.
 */
export default function MemoryView({ slug }: { slug: string }) {
  const { refreshKey, openDoc } = useSpace();
  const [verbats, setVerbats] = useState<VerbatOut[]>([]);
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [report, setReport] = useState<CurateReport | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [, v] = await apiInterceptors(listVerbats(slug, 200));
      const [, d] = await apiInterceptors(listDocs(slug, 200));
      const [, r] = await apiInterceptors(getCurateReport(slug));
      setVerbats(v?.items || []);
      setDocs(d || []);
      setReport(r || null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      message.error(`加载失败: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // Timeline: verbats are already newest-first; group by conv_id.
  const timeline = useMemo(() => {
    const active = verbats.filter((v) => !v.deprecated);
    const groups: { convId: string; items: VerbatOut[]; latest?: string | null }[] = [];
    const index = new Map<string, { convId: string; items: VerbatOut[]; latest?: string | null }>();
    for (const v of active) {
      const convId = metaStr(v, 'conv_id') || '(未关联会话)';
      let g = index.get(convId);
      if (!g) {
        g = { convId, items: [], latest: v.filed_at };
        index.set(convId, g);
        groups.push(g);
      }
      g.items.push(v);
    }
    return groups;
  }, [verbats]);

  const memoryDocs = useMemo(
    () => docs.filter((d) => MEMORY_DOC_TYPES.has(d.type)),
    [docs],
  );

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4 custom-scrollbar">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-medium text-gray-700 m-0">记忆空间</h3>
          <Tag color="blue">{verbats.filter((v) => !v.deprecated).length} 条原文</Tag>
          <Tag>{memoryDocs.length} 条提炼记忆</Tag>
        </div>
        <Tooltip title="刷新">
          <button
            onClick={load}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all"
          >
            <ReloadOutlined className={`text-xs ${loading ? 'animate-spin' : ''}`} />
          </button>
        </Tooltip>
      </div>

      <Spin spinning={loading}>
        <div className="flex flex-col gap-4">
          {/* L0 timeline grouped by conversation */}
          <div className="rounded-lg border border-gray-100 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 text-[12px] font-medium text-gray-700">
              对话时间线（L0 verbats）
            </div>
            {timeline.length === 0 && !loading ? (
              <Empty description="暂无对话原文" imageStyle={{ height: 40 }} className="py-6" />
            ) : (
              <div className="flex flex-col">
                {timeline.map((g) => (
                  <div key={g.convId} className="border-b border-gray-50 last:border-b-0">
                    <div className="px-4 py-2 bg-gray-50/60 flex items-center gap-2">
                      <span className="text-[12px] font-medium text-gray-700 truncate">
                        {g.convId}
                      </span>
                      <Tag className="!text-[10px] !px-1 !py-0 !m-0">{g.items.length} 轮</Tag>
                      <span className="text-[10px] text-gray-400 ml-auto">{fmtDate(g.latest)}</span>
                    </div>
                    <div className="flex flex-col">
                      {g.items.map((v) => (
                        <div key={v.id} className="px-4 py-2 border-t border-gray-50">
                          <div className="flex items-center gap-2 mb-0.5">
                            {metaStr(v, 'author') && (
                              <span className="text-[11px] font-medium text-gray-600">
                                {metaStr(v, 'author')}
                              </span>
                            )}
                            {metaStr(v, 'turn_round') && (
                              <Tag className="!text-[10px] !px-1 !py-0 !m-0" color="default">
                                R{metaStr(v, 'turn_round')}
                              </Tag>
                            )}
                            <span className="text-[10px] text-gray-400 ml-auto">
                              {fmtDate(v.filed_at)}
                            </span>
                          </div>
                          <div className="text-[12px] text-gray-500 whitespace-pre-wrap break-words">
                            {v.content_preview || '(空)'}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* L1 refined memory docs */}
          <div className="rounded-lg border border-gray-100 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 text-[12px] font-medium text-gray-700">
              提炼记忆（L1 documents）
            </div>
            {memoryDocs.length === 0 && !loading ? (
              <Empty description="暂无提炼记忆" imageStyle={{ height: 40 }} className="py-6" />
            ) : (
              <div className="flex flex-col">
                {memoryDocs.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => openDoc(d.path)}
                    className="px-4 py-2.5 border-b border-gray-50 last:border-b-0 flex items-center gap-2 text-left hover:bg-gray-50/40 transition-colors"
                  >
                    <Tag color={DOC_TYPE_COLOR[d.type] || 'default'} className="!m-0">
                      {d.type}
                    </Tag>
                    <span className="text-[12px] text-gray-700 truncate flex-1" title={d.path}>
                      {d.title || d.path}
                    </span>
                    <span className="text-[10px] text-gray-400">{d.status}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* tier3 curate report */}
          <div className="rounded-lg border border-gray-100 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 text-[12px] font-medium text-gray-700 flex items-center gap-2">
              策展报告（REPORT.md）
              {report?.timestamp && (
                <span className="text-[10px] text-gray-400 font-normal">{report.timestamp}</span>
              )}
            </div>
            {!report?.content ? (
              <Empty description="暂无策展报告" imageStyle={{ height: 40 }} className="py-6" />
            ) : (
              <div className="px-4 py-3 text-[13px] text-gray-800">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.content}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      </Spin>
    </div>
  );
}
