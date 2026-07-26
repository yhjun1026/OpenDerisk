'use client';

import React, { FC, useMemo, useState } from 'react';
import { Table, Pagination, Tooltip, Button } from 'antd';
import { CopyOutlined, CheckOutlined, DownloadOutlined, DatabaseOutlined, LockOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ManusExecutionOutput } from '@/types/manus';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface SqlQueryData {
  sql: string;
  db_name: string;
  db_type: string;
  dialect?: string;
  columns: string[];
  rows: Array<Array<any>>;
  total_rows: number;
  page: number;
  total_pages: number;
  page_size: number;
  has_more: boolean;
  csv_file?: string;
  csv_export_reason?: string;
  raw_result?: string;
}

interface IProps {
  outputs: ManusExecutionOutput[];
}

const SqlQueryRenderer: FC<IProps> = ({ outputs }) => {
  const sqlData = useMemo<SqlQueryData | null>(() => {
    const sqlOutput = outputs.find((o) => o.output_type === 'sql_query');
    if (sqlOutput?.content && typeof sqlOutput.content === 'object') {
      return sqlOutput.content as SqlQueryData;
    }
    // Try parsing from string
    if (sqlOutput?.content && typeof sqlOutput.content === 'string') {
      try {
        return JSON.parse(sqlOutput.content);
      } catch {
        return null;
      }
    }
    return null;
  }, [outputs]);

  const [currentPage, setCurrentPage] = useState(sqlData?.page || 1);
  const [copied, setCopied] = useState(false);

  // Build table columns — must be called before any early return to satisfy React hooks rules
  const tableColumns: ColumnsType<any> = useMemo(() => {
    const cols = sqlData?.columns;
    if (!cols || cols.length === 0) return [];
    const firstRow = sqlData?.rows?.[0];
    return cols.map((col, colIndex) => {
      const numeric = typeof firstRow?.[colIndex] === 'number';
      return {
        title: col,
        dataIndex: col,
        key: col,
        ellipsis: true,
        ...(numeric ? { align: 'right' as const } : {}),
        render: (value: any) => {
          if (value === null || value === undefined) {
            return <span className="text-gray-400 italic text-xs">NULL</span>;
          }
          if (typeof value === 'object') {
            return <code className="text-xs bg-gray-50 px-1 rounded">{JSON.stringify(value)}</code>;
          }
          return <span className="text-xs">{String(value)}</span>;
        },
      };
    });
  }, [sqlData?.columns, sqlData?.rows]);

  // Build table data
  const tableData = useMemo(() => {
    const rows = sqlData?.rows;
    const cols = sqlData?.columns;
    if (!rows || rows.length === 0) return [];
    return rows.map((row, index) => {
      const record: Record<string, any> = { _key: index };
      cols?.forEach((col, colIndex) => {
        record[col] = row[colIndex];
      });
      return record;
    });
  }, [sqlData?.rows, sqlData?.columns]);

  if (!sqlData) {
    // Fallback: show raw output as text
    const text = outputs.map((o) => String(o.content || '')).join('\n');
    return (
      <div className="p-4 text-sm text-gray-600 whitespace-pre-wrap font-mono">
        {text || 'No SQL result data'}
      </div>
    );
  }

  const {
    sql,
    db_name,
    db_type,
    dialect,
    columns,
    total_rows,
    total_pages,
    page_size,
    csv_file,
    csv_export_reason,
    raw_result,
  } = sqlData;

  const handleCopySql = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy SQL:', err);
    }
  };

  // No tabular data — show raw result
  if (!columns || columns.length === 0) {
    return (
      <div className="flex flex-col h-full">
        {/* Header */}
        <SqlHeader
          dbType={db_type}
          dbName={db_name}
          dialect={dialect}
          sql={sql}
          copied={copied}
          onCopy={handleCopySql}
        />
        <div className="p-4">
          {raw_result ? (
            <pre className="text-sm text-gray-600 whitespace-pre-wrap">{raw_result}</pre>
          ) : (
            <div className="text-gray-400 text-sm">查询执行成功，无结果返回。</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <SqlHeader
        dbType={db_type}
        dbName={db_name}
        dialect={dialect}
        sql={sql}
        copied={copied}
        onCopy={handleCopySql}
      />

      {/* Results */}
      <div className="flex-1 overflow-auto px-4 pb-4 pt-3">
        {/* Table */}
        <Table
          dataSource={tableData}
          columns={tableColumns}
          rowKey="_key"
          pagination={false}
          size="small"
          scroll={{ x: 'max-content' }}
          className="tabular-nums text-sm [&_.ant-table-thead>tr>th]:bg-gray-50 [&_.ant-table-thead>tr>th]:text-xs [&_.ant-table-thead>tr>th]:font-semibold [&_.ant-table-thead>tr>th]:text-gray-600 [&_.ant-table-tbody>tr>td]:border-gray-100 [&_.ant-table-tbody>tr:nth-child(even)>td]:bg-gray-50/40 [&_.ant-table-tbody>tr:hover>td]:!bg-blue-50/40"
        />

        {/* Footer: row count + CSV link */}
        <div className="flex items-center justify-between pt-2 border-t border-gray-100 mt-1">
          <span className="text-[11px] text-gray-400 tabular-nums">
            共 {total_rows} 行
            {total_pages > 1 && ` · 第 ${currentPage}/${total_pages} 页`}
          </span>
          {csv_file && (
            <Tooltip title={csv_export_reason}>
              <a
                href={csv_file}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-[#4f46e5] hover:text-[#6366f1] flex items-center gap-1"
              >
                <DownloadOutlined className="text-[10px]" />
                下载完整 CSV
              </a>
            </Tooltip>
          )}
        </div>

        {/* Pagination */}
        {total_pages > 1 && (
          <div className="mt-3 flex justify-center">
            <Pagination
              current={currentPage}
              total={total_rows}
              pageSize={page_size}
              onChange={(p) => setCurrentPage(p)}
              showSizeChanger={false}
              showTotal={(total) => `共 ${total} 行`}
              size="small"
            />
          </div>
        )}
      </div>
    </div>
  );
};

/** SQL Header bar — badges follow a single neutral scale; only the copy action is interactive */
const SqlHeader: FC<{
  dbType: string;
  dbName: string;
  dialect?: string;
  sql: string;
  copied: boolean;
  onCopy: () => void;
}> = ({ dbType, dbName, dialect, sql, copied, onCopy }) => (
  <div className="border-b border-gray-100">
    {/* Top bar: SQL Query label + badges + Copy */}
    <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50/80">
      <div className="flex items-center gap-2 min-w-0">
        <DatabaseOutlined className="text-gray-400 text-sm flex-shrink-0" />
        <span className="text-[13px] font-medium text-gray-700 flex-shrink-0">SQL Query</span>
        <span className="text-[11px] text-gray-400 flex-shrink-0">
          {(dialect || dbType)?.toUpperCase()}
        </span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200 truncate max-w-[220px]">
          {dbName}
        </span>
        <Tooltip title="只读查询，不会修改数据">
          <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-gray-50 text-gray-400 border border-gray-200 flex-shrink-0">
            <LockOutlined className="text-[9px]" />
            READ ONLY
          </span>
        </Tooltip>
      </div>
      <Tooltip title={copied ? '已复制' : '复制 SQL'}>
        <Button
          type="text"
          size="small"
          className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          icon={copied ? <CheckOutlined className="text-green-500" /> : <CopyOutlined />}
          onClick={onCopy}
        >
          <span className="text-xs ml-0.5">Copy</span>
        </Button>
      </Tooltip>
    </div>

    {/* SQL code area — syntax highlighted; className keeps VisCard's pre reset away */}
    <div className="overflow-hidden rounded-lg">
      {/* @ts-expect-error react-syntax-highlighter 类型与 React 18 不完全匹配 */}
      <SyntaxHighlighter
        language="sql"
        style={oneDark}
        className="manus-sql-code"
        customStyle={{ margin: 0, padding: '14px 16px', fontSize: 12.5, lineHeight: 1.7, maxHeight: 200, overflow: 'auto', borderRadius: 10 }}
      >
        {sql}
      </SyntaxHighlighter>
    </div>
  </div>
);

export default SqlQueryRenderer;
