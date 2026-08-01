'use client';

import { apiInterceptors } from '@/client/api';
import { getOrCreateEcpSpace } from '@/client/api/ecp';
import { lintSpace } from '@/client/api/knowledge-vault';
import type { LintIssue } from '@/types/knowledge-vault';
import { PlayCircleOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Button } from 'antd';
import { useState } from 'react';

import { Dot, EcpEmpty } from './common';

const SEVERITY_DOT: Record<string, string> = {
  info: 'ecp-dot--success',
  warning: 'ecp-dot--warning',
  error: 'ecp-dot--danger',
};

/**
 * Lint view. Soft-layer structural lint (knowledge doc_lint, incl. index_drift)
 * runs against the ECP space; hard-layer checks arrive with the P3 cron lint.
 */
export default function LintTab({ workspaceId }: { workspaceId: string }) {
  const [issues, setIssues] = useState<LintIssue[] | null>(null);

  const { data: space } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getOrCreateEcpSpace(workspaceId));
      return err ? null : res;
    },
    { refreshDeps: [workspaceId] },
  );

  const { run, loading } = useRequest(
    async () => {
      if (!space?.slug) return;
      const [err, res] = await apiInterceptors(lintSpace(space.slug));
      if (err) throw err;
      setIssues(res?.issues ?? []);
    },
    { manual: true },
  );

  const grouped = (issues ?? []).reduce<Record<string, LintIssue[]>>((acc, i) => {
    (acc[i.rule] ??= []).push(i);
    return acc;
  }, {});

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
        <span style={{ fontSize: 13, color: 'var(--ink-500)', maxWidth: 640 }}>
          软层结构巡检：孤儿页 / 断链 / 缺引用 / 陈旧边 / frontmatter / index 失步。
          硬层巡检（绑定漂移、语义矛盾、未命中聚类）随 P3 定时巡检上线。
        </span>
        <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={() => run()}>
          运行巡检
        </Button>
      </div>

      {issues === null ? (
        <EcpEmpty title="点击「运行巡检」检查软知识层健康度" />
      ) : issues.length === 0 ? (
        <div className="ecp-card" style={{ textAlign: 'center', padding: 48 }}>
          <span className="ecp-status" style={{ fontSize: 14 }}>
            <Dot kind="ecp-dot--success" />
            未发现问题，软知识层结构健康
          </span>
        </div>
      ) : (
        Object.entries(grouped).map(([rule, list]) => (
          <div key={rule} className="ecp-card">
            <div className="ecp-card__title">
              <span>
                {rule}
                <span style={{ color: 'var(--ink-400)', fontWeight: 400, marginLeft: 8 }}>
                  {list.length} 项
                </span>
              </span>
            </div>
            {list.map((i, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  gap: 10,
                  alignItems: 'center',
                  padding: '8px 0',
                  borderBottom:
                    idx < list.length - 1 ? '1px solid var(--line-soft)' : 'none',
                  fontSize: 13,
                }}
              >
                <Dot kind={SEVERITY_DOT[i.severity] ?? 'ecp-dot--neutral'} />
                <span style={{ color: 'var(--ink-700)' }}>{i.message}</span>
                {i.path && (
                  <code style={{ fontSize: 11, color: 'var(--ink-400)' }}>{i.path}</code>
                )}
              </div>
            ))}
          </div>
        ))
      )}
    </>
  );
}
