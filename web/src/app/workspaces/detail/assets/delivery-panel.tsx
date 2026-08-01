'use client';

import {
  apiInterceptors,
  listArtifacts,
  listDeliveries,
  listAssets,
  sendDelivery,
} from '@/client/api';
import {
  Button, Empty, Modal, Descriptions, Spin, Tag, message,
} from 'antd';
import {
  FileTextOutlined,
  SendOutlined,
  HistoryOutlined,
  EyeOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { useMemo, useState } from 'react';
import dayjs from 'dayjs';
import { GPTVis } from '@antv/gpt-vis';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import './assets.css';

const PAGE_SIZE = 20;

type FeedKind = 'artifact' | 'delivery' | 'asset';

interface FeedItem {
  key: string;
  kind: FeedKind;
  title: string;
  sub?: string;
  tagLabel: string;
  tagColor: string;
  time: string;
  raw: any;
}

const KIND_META: Record<FeedKind, { label: string; icon: React.ReactNode; color: string }> = {
  artifact: { label: '产出物', icon: <FileTextOutlined />, color: 'var(--ws-brand, #4f46e5)' },
  delivery: { label: '交付', icon: <SendOutlined />, color: '#9333ea' },
  asset: { label: '沉淀', icon: <HistoryOutlined />, color: '#16a34a' },
};

function isHtmlContent(text: string): boolean {
  const head = text.trimStart().slice(0, 200).toLowerCase();
  return head.startsWith('<!doctype') || head.startsWith('<html');
}

/** 交付物内容渲染:html → 沙箱 iframe;markdown → GPTVis;空 → 占位提示。 */
function ArtifactContent({ text }: { text: string }) {
  if (!text.trim()) {
    return <Empty description="(no content stored; see content_ref for reference)" />;
  }
  if (isHtmlContent(text)) {
    return (
      <iframe
        sandbox="allow-same-origin"
        srcDoc={text}
        title="artifact preview"
        style={{ width: '100%', minHeight: 480, border: '1px solid #f0f0f0', borderRadius: 8 }}
      />
    );
  }
  return (
    <div style={{ maxHeight: 480, overflowY: 'auto' }}>
      {/* @ts-ignore rehypePlugins type mismatch is pre-existing repo-wide */}
      <GPTVis components={markdownComponents} {...markdownPlugins}>
        {preprocessLaTeX(text)}
      </GPTVis>
    </div>
  );
}

function deliveryStatusColor(s: string) {
  if (s === 'sent' || s === 'delivered') return 'success';
  if (s === 'failed') return 'error';
  if (s === 'pending') return 'warning';
  return 'default';
}

/** 交付沉淀:这个空间干出来了什么 —— 产出物 / 交付记录 / 沉淀资产,统一时间线。 */
export function DeliveryPanel({ workspaceId }: { workspaceId: number }) {
  const [kindFilter, setKindFilter] = useState<'all' | FeedKind>('all');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [activeArtifact, setActiveArtifact] = useState<any | null>(null);

  const { data: artifacts, loading: l1 } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listArtifacts({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: deliveries, loading: l2, refresh: refreshDeliveries } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listDeliveries({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: assets, loading: l3 } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listAssets({ workspace_id: workspaceId, limit: 200 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const loading = l1 || l2 || l3;

  const feed = useMemo<FeedItem[]>(() => {
    const items: FeedItem[] = [];
    (artifacts || []).forEach((a: any) => {
      items.push({
        key: `a-${a.id}`,
        kind: 'artifact',
        title: a.title || `artifact_${a.id}`,
        sub: a.type,
        tagLabel: a.type || '产出物',
        tagColor: 'blue',
        time: a.gmt_created || '',
        raw: a,
      });
    });
    (deliveries || []).forEach((d: any) => {
      items.push({
        key: `d-${d.id}`,
        kind: 'delivery',
        title: `${d.channel} → ${d.target || ''}`,
        sub: d.status,
        tagLabel: d.status || '交付',
        tagColor: deliveryStatusColor(d.status),
        time: d.sent_at || d.gmt_created || '',
        raw: d,
      });
    });
    (assets || []).forEach((s: any) => {
      items.push({
        key: `s-${s.id}`,
        kind: 'asset',
        title: s.name || `asset_${s.id}`,
        sub: s.type,
        tagLabel: '沉淀',
        tagColor: 'green',
        time: s.gmt_created || '',
        raw: s,
      });
    });
    // 时间倒序:最近干出来的排前面
    return items.sort((a, b) => dayjs(b.time || 0).valueOf() - dayjs(a.time || 0).valueOf());
  }, [artifacts, deliveries, assets]);

  const counts = useMemo(() => {
    const c: Record<FeedKind, number> = { artifact: 0, delivery: 0, asset: 0 };
    feed.forEach((i) => { c[i.kind] += 1; });
    return c;
  }, [feed]);

  const visible = useMemo(
    () => feed.filter((i) => kindFilter === 'all' || i.kind === kindFilter),
    [feed, kindFilter],
  );

  const handleResend = async (deliveryId: number) => {
    const [err] = await apiInterceptors(sendDelivery(deliveryId));
    if (err) { message.error('投递失败,请稍后重试'); return; }
    message.success('已重新投递');
    refreshDeliveries();
  };

  return (
    <div>
      <div className="ws-feed-chips">
        <span
          className={`ws-feed-chip${kindFilter === 'all' ? ' ws-feed-chip--on' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => { setKindFilter('all'); setVisibleCount(PAGE_SIZE); }}
          onKeyDown={(e) => { if (e.key === 'Enter') { setKindFilter('all'); setVisibleCount(PAGE_SIZE); } }}
        >
          全部 {feed.length}
        </span>
        {(Object.keys(KIND_META) as FeedKind[])
          .filter((k) => counts[k] > 0)
          .map((k) => (
            <span
              key={k}
              className={`ws-feed-chip${kindFilter === k ? ' ws-feed-chip--on' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => { setKindFilter(k); setVisibleCount(PAGE_SIZE); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { setKindFilter(k); setVisibleCount(PAGE_SIZE); } }}
            >
              {KIND_META[k].label} {counts[k]}
            </span>
          ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><Spin /></div>
      ) : visible.length === 0 ? (
        <Empty description="还没有交付沉淀 —— 任务跑完后,产出、交付与沉淀会出现在这里" style={{ padding: '32px 0' }} />
      ) : (
        <>
          <div className="ws-feed">
            {visible.slice(0, visibleCount).map((item) => {
              const meta = KIND_META[item.kind];
              return (
                <div key={item.key} className="ws-feed-item">
                  <span className="ws-feed-item__icon" style={{ color: meta.color }}>{meta.icon}</span>
                  <span className="ws-feed-item__main">
                    <span className="ws-feed-item__title" title={item.title}>{item.title}</span>
                    <Tag color={item.tagColor} style={{ marginInlineEnd: 0 }}>{item.tagLabel}</Tag>
                  </span>
                  <span className="ws-feed-item__time">
                    {item.time ? dayjs(item.time).format('MM-DD HH:mm') : ''}
                  </span>
                  <span className="ws-feed-item__ops">
                    {item.kind === 'artifact' && (
                      <Button size="small" type="text" icon={<EyeOutlined />} onClick={() => setActiveArtifact(item.raw)} />
                    )}
                    {item.kind === 'artifact' && item.raw.content_ref && (
                      <Button size="small" type="text" icon={<LinkOutlined />} onClick={() => window.open(item.raw.content_ref, '_blank')} />
                    )}
                    {item.kind === 'delivery' && (
                      <Button size="small" type="text" icon={<SendOutlined />} onClick={() => handleResend(item.raw.id)} />
                    )}
                  </span>
                </div>
              );
            })}
          </div>
          {visible.length > visibleCount && (
            <div
              className="ws-feed-more"
              role="button"
              tabIndex={0}
              onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
              onKeyDown={(e) => { if (e.key === 'Enter') setVisibleCount((n) => n + PAGE_SIZE); }}
            >
              加载更多(还有 {visible.length - visibleCount} 条)
            </div>
          )}
        </>
      )}

      <Modal
        open={!!activeArtifact}
        onCancel={() => setActiveArtifact(null)}
        footer={null}
        width={900}
        title={activeArtifact?.title}
      >
        {activeArtifact && (
          <div>
            <p className="text-sm text-gray-600 mb-2">
              <Tag color="blue">{activeArtifact.type}</Tag>
              {' '}v{activeArtifact.current_version} · Task #{activeArtifact.task_id}
            </p>
            <Descriptions column={1} size="small" bordered className="mb-4">
              <Descriptions.Item label="ID">{activeArtifact.id}</Descriptions.Item>
              <Descriptions.Item label="Shared">{activeArtifact.is_shared ? 'Yes' : 'No'}</Descriptions.Item>
              <Descriptions.Item label="Created">{activeArtifact.gmt_created}</Descriptions.Item>
            </Descriptions>
            <h3 className="text-sm font-medium mt-4">Content</h3>
            {activeArtifact.content_text ? (
              <ArtifactContent text={activeArtifact.content_text} />
            ) : activeArtifact.content_ref ? (
              <div>
                {activeArtifact.provenance?.description && (
                  <p className="text-sm text-gray-600 mb-2">{activeArtifact.provenance.description}</p>
                )}
                <Button
                  type="primary"
                  icon={<LinkOutlined />}
                  onClick={() => window.open(activeArtifact.content_ref, '_blank')}
                >
                  打开 / 下载文件
                </Button>
              </div>
            ) : (
              <ArtifactContent text="" />
            )}
            <h3 className="text-sm font-medium mt-4">Provenance</h3>
            <pre className="text-xs bg-gray-50 p-3 max-h-40 overflow-auto rounded">
              {JSON.stringify(activeArtifact.provenance || {}, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
}
