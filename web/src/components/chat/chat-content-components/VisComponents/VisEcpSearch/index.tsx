'use client';

import React, { FC } from 'react';
import { Empty } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

interface EcpSearchResult {
  id: string;
  type: string;
  name?: string;
  aliases?: string[];
  one_line?: string;
}

interface EcpSearchData {
  query: string;
  workspace_id?: string;
  total: number;
  results: EcpSearchResult[];
}

interface VisEcpSearchProps {
  data: EcpSearchData;
}

const TYPE_META: Record<string, { label: string; dot: string; text: string }> = {
  metric: { label: '指标', dot: 'bg-[#4f46e5]', text: 'text-[#4f46e5]' },
  entity: { label: '实体', dot: 'bg-[#22c55e]', text: 'text-[#22c55e]' },
  dimension: { label: '维度', dot: 'bg-[#d97706]', text: 'text-[#d97706]' },
  relation: { label: '关系', dot: 'bg-[#7c3aed]', text: 'text-[#7c3aed]' },
};

const TypeBadge: FC<{ type: string }> = ({ type }) => {
  const meta = TYPE_META[type] || { label: type, dot: 'bg-gray-400', text: 'text-gray-500' };
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium ${meta.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
};

const VisEcpSearch: FC<VisEcpSearchProps> = ({ data }) => {
  const { query, total, results } = data || { query: '', total: 0, results: [] };

  return (
    <div className="rounded-xl bg-white overflow-hidden">
      {/* 头部:查询词 + 命中数 */}
      <div className="flex items-center gap-2 px-4 py-3 bg-[#f8f9fc]">
        <SearchOutlined className="text-[#4f46e5]" />
        <span className="text-sm font-medium text-slate-700">语义目录搜索</span>
        <span className="text-xs text-slate-400">「{query}」</span>
        <span className="ml-auto text-xs text-slate-500">{total} 个已确认对象</span>
      </div>

      {/* 结果列表 */}
      {results && results.length > 0 ? (
        <div className="divide-y divide-slate-100">
          {results.map((r) => (
            <div key={r.id} className="px-4 py-2.5 hover:bg-[#fafbfd] transition-colors">
              <div className="flex items-center gap-2.5">
                <TypeBadge type={r.type} />
                <code className="text-xs font-semibold text-slate-800 bg-slate-50 px-1.5 py-0.5 rounded">
                  {r.id}
                </code>
                {r.name && <span className="text-sm text-slate-700">{r.name}</span>}
              </div>
              {(r.one_line || (r.aliases && r.aliases.length > 0)) && (
                <div className="mt-1 ml-0.5 flex items-center gap-2 text-xs text-slate-400">
                  {r.one_line && <span className="truncate">{r.one_line}</span>}
                  {r.aliases && r.aliases.length > 0 && (
                    <span className="shrink-0">别名: {r.aliases.join(' / ')}</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="py-6">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div className="text-xs text-slate-400">
                <div>目录中无匹配的已确认对象</div>
                <div className="mt-1">可用 execute_raw_sql 兜底查询,或 propose_semantic 提案新概念</div>
              </div>
            }
          />
        </div>
      )}
    </div>
  );
};

export default VisEcpSearch;
