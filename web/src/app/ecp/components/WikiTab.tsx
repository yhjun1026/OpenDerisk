'use client';

import { apiInterceptors } from '@/client/api';
import { getOrCreateEcpSpace } from '@/client/api/ecp';
import { getWikiTree, readDoc } from '@/client/api/knowledge-vault';
import type { TreeNode } from '@/types/knowledge-vault';
import { FileMarkdownOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Spin, Tree } from 'antd';
import { useMemo, useState } from 'react';

import { EcpEmpty } from './common';

function toTreeData(nodes: TreeNode[]): any[] {
  return (nodes ?? []).map(n => ({
    key: n.path,
    title: n.name,
    isLeaf: !n.is_dir,
    children: n.children ? toTreeData(n.children) : undefined,
    icon: n.is_dir ? undefined : <FileMarkdownOutlined />,
  }));
}

/**
 * Soft knowledge layer: the ECP space (ecp-<workspace>) wiki tree + reader.
 * Business-facing view of a standard knowledge space.
 */
export default function WikiTab({ workspaceId }: { workspaceId: string }) {
  const [selected, setSelected] = useState<string>();

  const { data: space, loading: spaceLoading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getOrCreateEcpSpace(workspaceId));
      if (err) throw err;
      return res;
    },
    { refreshDeps: [workspaceId] },
  );

  const { data: tree, loading: treeLoading } = useRequest(
    async () => {
      if (!space?.slug) return [];
      const [err, res] = await apiInterceptors(getWikiTree(space.slug));
      return err ? [] : res ?? [];
    },
    { ready: !!space?.slug, refreshDeps: [space?.slug] },
  );

  const { data: doc, loading: docLoading } = useRequest(
    async () => {
      if (!space?.slug || !selected) return null;
      const [err, res] = await apiInterceptors(readDoc(space.slug, selected));
      return err ? null : res;
    },
    { ready: !!space?.slug && !!selected, refreshDeps: [selected, space?.slug] },
  );

  const treeData = useMemo(() => toTreeData(tree ?? []), [tree]);

  if (spaceLoading) return <Spin style={{ display: 'block', margin: '64px auto' }} />;

  return (
    <div className="ecp-wiki">
      <div className="ecp-wiki__side">
        <div className="ecp-wiki__side-title">
          <span>软知识层</span>
          <code style={{ fontSize: 11 }}>{space?.slug}</code>
        </div>
        {treeLoading ? (
          <Spin style={{ display: 'block', margin: '32px auto' }} />
        ) : treeData.length ? (
          <Tree
            showIcon
            treeData={treeData}
            selectedKeys={selected ? [selected] : []}
            onSelect={keys => {
              const k = keys[0] as string | undefined;
              if (k && k.endsWith('.md')) setSelected(k);
            }}
          />
        ) : (
          <EcpEmpty
            title="软知识层为空"
            desc="文档资产 ingest 后，这里会出现业务词条与分析模式"
          />
        )}
      </div>

      <div className="ecp-wiki__reader">
        {!selected ? (
          <EcpEmpty title="从左侧选择一篇词条" />
        ) : docLoading ? (
          <Spin style={{ display: 'block', margin: '64px auto' }} />
        ) : doc ? (
          <>
            <div className="ecp-wiki__doc-title">{doc.title}</div>
            {!!doc.frontmatter?.ref && (
              <div className="ecp-wiki__doc-ref">ref → {String(doc.frontmatter.ref)}</div>
            )}
            <div className="ecp-wiki__doc-body">{doc.content}</div>
          </>
        ) : (
          <EcpEmpty title="读取失败" />
        )}
      </div>
    </div>
  );
}
