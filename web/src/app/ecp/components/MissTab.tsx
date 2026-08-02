'use client';

import { apiInterceptors } from '@/client/api';
import { EcpMissCluster, getEcpMissReport, learnEcpFromMisses } from '@/client/api/ecp';
import { PlayCircleOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Button, App, Table, Tag } from 'antd';
import React, { useState } from 'react';

import { Dot, EcpEmpty } from './common';

/**
 * Miss view — 未覆盖问题聚类(execute_raw_sql 兜底记录)。
 * "大家在裸查什么"的可见化;高频 miss 可一键喂给提案 agent 学习,
 * 生成的提案进收件箱走人工 confirm(召回飞轮学习侧)。
 */
export default function MissTab({ workspaceId }: { workspaceId: string }) {
  const [learnResult, setLearnResult] = useState<string | null>(null);
  const { message } = App.useApp();

  const { data, loading, refresh } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getEcpMissReport({ limit: 50, workspace_id: workspaceId }),
      );
      if (err) throw err;
      return res;
    },
    { refreshDeps: [workspaceId] },
  );

  const { run: learn, loading: learning } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        learnEcpFromMisses({ top: 10, workspace_id: workspaceId }),
      );
      if (err) throw err;
      return res;
    },
    {
      manual: true,
      onSuccess: res => {
        if (!res) return;
        if (res.errors?.length) {
          setLearnResult(`学习完成但有错误: ${res.errors[0]}`);
        } else {
          setLearnResult(
            `已生成 ${res.proposals_created} 个提案进收件箱,请前往「收件箱」确认`,
          );
        }
      },
      onError: () => message.error('学习触发失败(需工作空间已配置提案 Agent)'),
    },
  );

  const columns = [
    {
      title: '类型',
      dataIndex: 'kind',
      key: 'kind',
      width: 70,
      render: (kind: string) =>
        kind === 'doc' ? <Tag color="purple">doc</Tag> : <Tag color="blue">db</Tag>,
    },
    {
      title: '频次',
      dataIndex: 'count',
      key: 'count',
      width: 90,
      sorter: (a: EcpMissCluster, b: EcpMissCluster) => b.count - a.count,
      defaultSortOrder: 'descend' as const,
      render: (count: number) => (
        <span className="ecp-status">
          <Dot kind={count >= 5 ? 'ecp-dot--danger' : count >= 2 ? 'ecp-dot--warning' : 'ecp-dot--neutral'} />
          {count} 次
        </span>
      ),
    },
    {
      title: '示例',
      dataIndex: 'example_sql',
      key: 'example_sql',
      render: (sql: string, record: EcpMissCluster) => (
        <pre
          style={{
            margin: 0,
            fontSize: 12,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            maxWidth: 520,
            color: 'var(--ink-700)',
          }}
        >
          {record.kind === 'doc' ? `问题: ${sql}` : sql}
        </pre>
      ),
    },
    {
      title: '未命中原因',
      dataIndex: 'reasonings',
      key: 'reasonings',
      width: 260,
      render: (reasonings: string[]) => (
        <>
          {(reasonings ?? []).slice(0, 3).map((r, i) => (
            <div key={i} style={{ fontSize: 12, color: 'var(--ink-500)', marginBottom: 4 }}>
              · {r}
            </div>
          ))}
        </>
      ),
    },
    {
      title: '数据源',
      dataIndex: 'datasource_id',
      key: 'datasource_id',
      width: 90,
      render: (id: number) => <Tag>#{id}</Tag>,
    },
  ];

  return (
    <>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <span style={{ fontSize: 13, color: 'var(--ink-500)', maxWidth: 680 }}>
          未覆盖问题聚类：用户真实问过、但语义目录无法回答而走 ⚠️ 兜底 SQL 的查询，
          按 SQL 模式归一聚类、按频次排序。高频 miss 是最值得沉淀的语义资产——
          一键学习后提案进收件箱，确认即完成飞轮闭环。
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => refresh()}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={learning}
            disabled={!data?.clusters?.length}
            onClick={() => learn()}
          >
            从 miss 学习
          </Button>
        </div>
      </div>

      {learnResult && (
        <div className="ecp-card" style={{ marginBottom: 16 }}>
          <span className="ecp-status">
            <Dot kind="ecp-dot--success" />
            {learnResult}
          </span>
        </div>
      )}

      {!loading && !data?.clusters?.length ? (
        <EcpEmpty
          title={
            data?.total_fallbacks
              ? '有兜底记录但暂未达到聚类频次'
              : '暂无 miss 记录——目录覆盖良好,或还没有探索发生'
          }
        />
      ) : (
        <div className="ecp-card">
          <div className="ecp-card__title">
            <span>
              <PlayCircleOutlined style={{ marginRight: 8 }} />
              miss 聚类（共 {data?.total_fallbacks ?? 0} 次兜底 / {data?.cluster_count ?? 0} 类）
            </span>
          </div>
          <Table
            rowKey={r => `${r.datasource_id}-${r.pattern}`}
            columns={columns}
            dataSource={data?.clusters ?? []}
            loading={loading}
            size="small"
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
          />
        </div>
      )}
    </>
  );
}
