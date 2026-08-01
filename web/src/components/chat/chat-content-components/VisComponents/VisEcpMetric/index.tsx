'use client';

import React, { FC, useMemo, useState } from 'react';
import { Table, Alert } from 'antd';
import { CheckCircleFilled, DownOutlined, RightOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

interface EcpLineage {
  metric_id?: string;
  metric_version?: number;
  entity_id?: string;
  entity_version?: number;
  table?: string;
  datasource_id?: number;
  executed_at?: string;
}

interface EcpMetricData {
  trust: 'verified' | 'inferred' | 'none';
  metric_id: string;
  columns?: string[];
  rows?: Array<Array<any>>;
  row_count?: number;
  sql?: string;
  lineage?: EcpLineage;
  error?: string;
  code?: string;
  cache_hit?: boolean;
}

interface VisEcpMetricProps {
  data: EcpMetricData;
}

const TrustBadge: FC<{ trust: string }> = ({ trust }) => {
  if (trust === 'verified') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#22c55e]">
        <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" />
        ✅ 可信口径 · verified
      </span>
    );
  }
  if (trust === 'inferred') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#d97706]">
        <span className="w-1.5 h-1.5 rounded-full bg-[#d97706]" />
        ⚠️ 未验证口径 · inferred
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#ef4444]">
      <span className="w-1.5 h-1.5 rounded-full bg-[#ef4444]" />
      查询被门禁拒绝
    </span>
  );
};

const VisEcpMetric: FC<VisEcpMetricProps> = ({ data }) => {
  const { trust, metric_id, columns, rows, row_count, sql, lineage, error, code, cache_hit } = data;
  const [showSql, setShowSql] = useState(false);

  const tableData = useMemo(() => {
    if (!rows || rows.length === 0 || !columns) return [];
    return rows.map((row, index) => {
      const record: Record<string, any> = { _key: index };
      columns.forEach((col, i) => {
        record[col] = row[i];
      });
      return record;
    });
  }, [rows, columns]);

  const tableColumns: ColumnsType<any> = useMemo(() => {
    if (!columns) return [];
    return columns.map((col) => ({
      title: col,
      dataIndex: col,
      key: col,
      ellipsis: true,
      render: (value: any) => {
        if (value === null || value === undefined) {
          return <span className="text-gray-400 italic">NULL</span>;
        }
        if (typeof value === 'number' && !Number.isInteger(value)) {
          return <span className="font-mono text-xs">{value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>;
        }
        if (typeof value === 'object') {
          return <code className="text-xs bg-gray-50 px-1 rounded">{JSON.stringify(value)}</code>;
        }
        return <span className="font-mono text-xs">{String(value)}</span>;
      },
    }));
  }, [columns]);

  // 错误态(门禁拒绝)
  if (trust === 'none' || error) {
    return (
      <div className="rounded-xl bg-white overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 bg-[#f8f9fc]">
          <span className="text-sm font-medium text-slate-700">指标查询</span>
          <code className="text-xs text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded">{metric_id}</code>
          <span className="ml-auto"><TrustBadge trust="none" /></span>
        </div>
        <div className="p-4">
          <Alert
            type="warning"
            showIcon
            message={<span className="text-sm">{error}</span>}
            description={code && <span className="text-xs text-slate-400">gate code: {code}</span>}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-white overflow-hidden">
      {/* 头部:指标 + trust 徽章 */}
      <div className="flex items-center gap-2 px-4 py-3 bg-[#f8f9fc]">
        <CheckCircleFilled className={trust === 'verified' ? 'text-[#22c55e]' : 'text-[#d97706]'} />
        <span className="text-sm font-medium text-slate-700">指标查询</span>
        <code className="text-xs text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded">{metric_id}</code>
        <span className="ml-auto inline-flex items-center gap-2">
          {cache_hit && (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#4f46e5]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#4f46e5]" />
              缓存回忆
            </span>
          )}
          <TrustBadge trust={trust} />
        </span>
      </div>

      {/* 结果表 */}
      {tableData.length > 0 && (
        <div className="p-3">
          <Table
            columns={tableColumns}
            dataSource={tableData}
            size="small"
            pagination={tableData.length > 10 ? { pageSize: 10, size: 'small' } : false}
            scroll={{ x: true }}
          />
          <div className="mt-1.5 text-right text-xs text-slate-400">共 {row_count ?? tableData.length} 行</div>
        </div>
      )}

      {/* 血缘页脚 */}
      {(lineage || sql) && (
        <div className="px-4 py-2.5 bg-[#fafbfd] text-xs text-slate-400">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {lineage?.metric_id && (
              <span>指标 <code className="text-slate-500">{lineage.metric_id}@v{lineage.metric_version}</code></span>
            )}
            {lineage?.entity_id && (
              <span>实体 <code className="text-slate-500">{lineage.entity_id}</code></span>
            )}
            {lineage?.table && (
              <span>表 <code className="text-slate-500">{lineage.table}</code></span>
            )}
            {lineage?.datasource_id != null && (
              <span>数据源 <code className="text-slate-500">#{lineage.datasource_id}</code></span>
            )}
            {sql && (
              <button
                onClick={() => setShowSql(!showSql)}
                className="ml-auto inline-flex items-center gap-1 text-[#4f46e5] hover:opacity-80"
              >
                {showSql ? <DownOutlined /> : <RightOutlined />}
                SQL
              </button>
            )}
          </div>
          {showSql && sql && (
            <pre className="mt-2 p-2.5 rounded-lg bg-slate-900 text-slate-100 text-xs overflow-x-auto whitespace-pre-wrap">{sql}</pre>
          )}
        </div>
      )}
    </div>
  );
};

export default VisEcpMetric;
