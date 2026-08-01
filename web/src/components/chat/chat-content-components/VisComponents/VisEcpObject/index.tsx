'use client';

import React, { FC, useState } from 'react';
import { Alert } from 'antd';
import { DownOutlined, RightOutlined, FileSearchOutlined } from '@ant-design/icons';

interface EcpObjectData {
  id: string;
  version?: number;
  type: string;
  status?: string;
  payload?: Record<string, any>;
  error?: string;
}

interface VisEcpObjectProps {
  data: EcpObjectData;
}

const TYPE_META: Record<string, { label: string; dot: string; text: string }> = {
  metric: { label: '指标', dot: 'bg-[#4f46e5]', text: 'text-[#4f46e5]' },
  entity: { label: '实体', dot: 'bg-[#22c55e]', text: 'text-[#22c55e]' },
  dimension: { label: '维度', dot: 'bg-[#d97706]', text: 'text-[#d97706]' },
  relation: { label: '关系', dot: 'bg-[#7c3aed]', text: 'text-[#7c3aed]' },
};

// 各类型的关键展示字段(其余进折叠 JSON)
const KEY_FIELDS: Record<string, string[]> = {
  metric: ['name', 'entity', 'expression', 'grain', 'unit', 'aggregation', 'description'],
  entity: ['name', 'binding', 'identifying_columns', 'description'],
  dimension: ['name', 'column', 'entity', 'values', 'description'],
  relation: ['from', 'to', 'path', 'cardinality', 'description'],
};

const FIELD_LABELS: Record<string, string> = {
  name: '名称', entity: '所属实体', expression: '表达式', grain: '粒度', unit: '单位',
  aggregation: '聚合', description: '描述', binding: '绑定', identifying_columns: '标识列',
  column: '列', values: '值字典', from: '起点', to: '终点', path: '关联路径',
  cardinality: '基数', aliases: '别名',
};

const VisEcpObject: FC<VisEcpObjectProps> = ({ data }) => {
  const [showRaw, setShowRaw] = useState(false);
  const { id, version, type, status, payload, error } = data || ({} as EcpObjectData);

  if (error) {
    return (
      <div className="rounded-xl bg-white p-4">
        <Alert type="warning" showIcon message={error} />
      </div>
    );
  }

  const meta = TYPE_META[type] || { label: type, dot: 'bg-gray-400', text: 'text-gray-500' };
  const p = payload || {};
  const keyFields = KEY_FIELDS[type] || [];
  // 关键字段 + aliases 优先展示,其余字段进折叠区
  const displayKeys = [...keyFields, 'aliases'].filter((k) => p[k] !== undefined);
  const shownSet = new Set(displayKeys);
  const restEntries = Object.entries(p).filter(([k]) => !shownSet.has(k));

  const renderValue = (v: any): React.ReactNode => {
    if (v === null || v === undefined) return <span className="text-gray-400 italic">null</span>;
    if (typeof v === 'object') {
      return (
        <code className="text-xs bg-slate-50 px-1.5 py-0.5 rounded text-slate-600 break-all">
          {JSON.stringify(v, null, 0)}
        </code>
      );
    }
    return <span className="text-sm text-slate-700">{String(v)}</span>;
  };

  return (
    <div className="rounded-xl bg-white overflow-hidden">
      {/* 头部:类型徽章 + id + 版本 + 状态 */}
      <div className="flex items-center gap-2.5 px-4 py-3 bg-[#f8f9fc]">
        <FileSearchOutlined className="text-[#4f46e5]" />
        <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium ${meta.text}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
        </span>
        <code className="text-xs font-semibold text-slate-800 bg-slate-50 px-1.5 py-0.5 rounded">
          {id}
        </code>
        {version != null && <span className="text-xs text-slate-400">v{version}</span>}
        {status && (
          <span className="ml-auto inline-flex items-center gap-1.5 text-[11px] font-medium text-[#22c55e]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" />
            {status}
          </span>
        )}
      </div>

      {/* 关键字段 */}
      <div className="px-4 py-2 divide-y divide-slate-50">
        {displayKeys.map((k) => (
          <div key={k} className="flex items-start gap-3 py-2">
            <span className="w-16 shrink-0 text-xs text-slate-400 pt-0.5">
              {FIELD_LABELS[k] || k}
            </span>
            <div className="min-w-0">{renderValue(p[k])}</div>
          </div>
        ))}
      </div>

      {/* 完整 payload 折叠 */}
      <div className="px-4 py-2.5 bg-[#fafbfd]">
        <button
          onClick={() => setShowRaw(!showRaw)}
          className="inline-flex items-center gap-1 text-xs text-[#4f46e5] hover:opacity-80"
        >
          {showRaw ? <DownOutlined /> : <RightOutlined />}
          完整定义{restEntries.length > 0 ? `（含 ${restEntries.length} 个其他字段）` : ''}
        </button>
        {showRaw && (
          <pre className="mt-2 p-2.5 rounded-lg bg-slate-900 text-slate-100 text-xs overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(p, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};

export default VisEcpObject;
