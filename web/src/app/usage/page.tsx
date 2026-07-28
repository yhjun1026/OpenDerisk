'use client';

import {
  getUsageOverview,
  getUsageByAgent,
  getUsageByModel,
  getUsageByConversation,
  getUsageTimeSeries,
  listUsageCalls,
  deleteUsageRecords,
  getDistinctAgents,
  UsageOverview,
  AgentUsage,
  ModelUsage,
  ConversationUsage,
  TimeSeriesPoint,
  UsageCall,
} from '@/client/api/usage';
import { apiInterceptors } from '@/client/api';
import {
  BarChartOutlined,
  ReloadOutlined,
  DeleteOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { Chart } from '@berryv/g2-react';
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import moment from 'moment';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

const { Title, Text } = Typography;

type RangeKey = '1h' | '24h' | '7d' | '30d';

const RANGE_MS: Record<RangeKey, number> = {
  '1h': 3600_000,
  '24h': 86400_000,
  '7d': 7 * 86400_000,
  '30d': 30 * 86400_000,
};
const RANGE_BUCKET_SEC: Record<RangeKey, number> = {
  '1h': 60,
  '24h': 300,
  '7d': 3600,
  '30d': 21600,
};

const fmtTokens = (n: number) => (n ?? 0).toLocaleString();
const fmtMs = (ts: number) => (ts ? moment(ts).format('MM-DD HH:mm:ss') : '-');
const fmtCost = (n: number) => `$${(n ?? 0).toFixed(4)}`;

export default function UsagePage() {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const searchParams = useSearchParams();
  const convIdParam = searchParams?.get('conv_id') || undefined;

  const [convId, setConvId] = useState<string | undefined>(convIdParam);
  const [agentId, setAgentId] = useState<string | undefined>(undefined);
  const [modelName, setModelName] = useState<string | undefined>(undefined);
  // When drilled in from a conversation, default to a wider window so older
  // conversations still show data.
  const [rangeKey, setRangeKey] = useState<RangeKey>(convIdParam ? '30d' : '24h');
  const [callsPage, setCallsPage] = useState(1);

  const endMs = Date.now();
  const startMs = endMs - RANGE_MS[rangeKey];

  const filters = {
    conv_id: convId,
    agent_id: agentId,
    model_name: modelName,
    start_ms: startMs,
    end_ms: endMs,
  };

  // agent list for filter (from actual usage data)
  const { data: agents } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getDistinctAgents({
          start_ms: startMs,
          end_ms: endMs,
        })
      );
      if (err) return [] as string[];
      return res || [];
    },
    { refreshDeps: [rangeKey] }
  );

  // overview
  const {
    data: overview,
    loading: overviewLoading,
    refresh: refreshOverview,
  } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getUsageOverview(filters));
      if (err) return null;
      return res;
    },
    { refreshDeps: [convId, agentId, modelName, rangeKey] }
  );

  // by-agent
  const { data: byAgent } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getUsageByAgent(filters));
      if (err) return [] as AgentUsage[];
      return res || [];
    },
    { refreshDeps: [convId, agentId, modelName, rangeKey] }
  );

  // by-model
  const { data: byModel } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(getUsageByModel(filters));
      if (err) return [] as ModelUsage[];
      return res || [];
    },
    { refreshDeps: [convId, agentId, modelName, rangeKey] }
  );

  // by-conversation (only meaningful in overview mode, not single-conv)
  const { data: byConv } = useRequest(
    async () => {
      if (convId) return [] as ConversationUsage[];
      const [err, res] = await apiInterceptors(getUsageByConversation(filters));
      if (err) return [] as ConversationUsage[];
      return res || [];
    },
    { refreshDeps: [convId, agentId, modelName, rangeKey] }
  );

  // time series
  const { data: ts } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getUsageTimeSeries({
          start_ms: startMs,
          end_ms: endMs,
          bucket_sec: RANGE_BUCKET_SEC[rangeKey],
          conv_id: convId,
          agent_id: agentId,
          model_name: modelName,
        })
      );
      if (err) return [] as TimeSeriesPoint[];
      return res || [];
    },
    { refreshDeps: [convId, agentId, modelName, rangeKey] }
  );

  // call details (filtered by the active conversation)
  const { data: callsData, loading: callsLoading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        listUsageCalls({
          ...filters,
          page: callsPage,
          page_size: 10,
        })
      );
      if (err) return { items: [] as UsageCall[], total_count: 0, page: 1, page_size: 10 };
      return res;
    },
    { refreshDeps: [convId, agentId, modelName, rangeKey, callsPage] }
  );

  const refreshAll = () => {
    refreshOverview();
  };

  const handleClear = () => {
    modal.confirm({
      title: t('usage_clear'),
      content: t('usage_clear_confirm'),
      onOk: async () => {
        const [err, res] = await apiInterceptors(
          deleteUsageRecords({ before_ms: endMs })
        );
        if (err) {
          message.error(String(err));
          return;
        }
        message.success(t('usage_clear_success', { count: res?.deleted ?? 0 }));
        refreshAll();
      },
    });
  };

  // chart data transforms
  const tokensSeries = useMemo(() => {
    if (!ts) return [];
    const rows: { x: string; kind: string; tokens: number }[] = [];
    for (const p of ts) {
      const x = moment(p.bucket_ms).format(
        rangeKey === '1h' || rangeKey === '24h' ? 'HH:mm' : 'MM-DD'
      );
      rows.push({ x, kind: t('usage_prompt_tokens'), tokens: p.prompt_tokens });
      rows.push({ x, kind: t('usage_completion_tokens'), tokens: p.completion_tokens });
    }
    return rows;
  }, [ts, rangeKey, t]);

  const callsSeries = useMemo(
    () =>
      (ts || []).map(p => ({
        x: moment(p.bucket_ms).format(
          rangeKey === '30d' || rangeKey === '7d' ? 'MM-DD' : 'HH:mm'
        ),
        calls: p.calls,
      })),
    [ts, rangeKey]
  );

  const ov: UsageOverview = overview || {
    total_calls: 0,
    error_calls: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    cost_usd: 0,
    avg_latency_ms: null,
    avg_tokens_per_sec: null,
  };

  const convColumns = [
    {
      title: t('usage_conversation'),
      dataIndex: 'conv_id',
      key: 'conv_id',
      render: (id: string) => (
        <Tooltip title={id}>
          <Text code className="cursor-pointer">
            {id ? `${id.slice(0, 12)}…` : '-'}
          </Text>
        </Tooltip>
      ),
    },
    { title: t('usage_agent'), dataIndex: 'agent_id', key: 'agent_id', width: 140 },
    { title: t('usage_total_calls'), dataIndex: 'calls', key: 'calls', width: 90 },
    {
      title: t('usage_prompt_tokens'),
      dataIndex: 'prompt_tokens',
      key: 'prompt_tokens',
      width: 110,
      render: fmtTokens,
    },
    {
      title: t('usage_completion_tokens'),
      dataIndex: 'completion_tokens',
      key: 'completion_tokens',
      width: 110,
      render: fmtTokens,
    },
    {
      title: t('usage_total_tokens'),
      dataIndex: 'total_tokens',
      key: 'total_tokens',
      width: 110,
      render: fmtTokens,
    },
    {
      title: t('usage_cost'),
      dataIndex: 'cost_usd',
      key: 'cost_usd',
      width: 100,
      render: fmtCost,
    },
    {
      title: t('usage_avg_latency'),
      dataIndex: 'avg_latency_ms',
      key: 'avg_latency_ms',
      width: 130,
      render: (v: number | null) => (v != null ? Math.round(v) : '-'),
    },
    {
      title: t('usage_error_calls'),
      dataIndex: 'error_calls',
      key: 'error_calls',
      width: 90,
      render: (v: number) => (v ? <Tag color="error">{v}</Tag> : <Tag>0</Tag>),
    },
  ];

  const callColumns = [
    {
      title: t('usage_time'),
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: fmtMs,
    },
    { title: t('usage_model'), dataIndex: 'model_name', key: 'model_name', width: 140 },
    {
      title: t('usage_prompt_tokens'),
      dataIndex: 'prompt_tokens',
      key: 'prompt_tokens',
      width: 110,
      render: fmtTokens,
    },
    {
      title: t('usage_completion_tokens'),
      dataIndex: 'completion_tokens',
      key: 'completion_tokens',
      width: 110,
      render: fmtTokens,
    },
    {
      title: t('usage_latency'),
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 100,
      render: (v: number) => fmtTokens(v),
    },
    {
      title: t('usage_first_token'),
      dataIndex: 'first_token_ms',
      key: 'first_token_ms',
      width: 120,
      render: (v: number | null) => (v != null ? fmtTokens(v) : '-'),
    },
    {
      title: t('usage_speed'),
      dataIndex: 'tokens_per_sec',
      key: 'tokens_per_sec',
      width: 110,
      render: (v: number | null) => (v != null ? v.toFixed(1) : '-'),
    },
    {
      title: t('usage_stream'),
      dataIndex: 'stream',
      key: 'stream',
      width: 70,
      render: (v: number) => (v ? <Tag color="processing">stream</Tag> : <Tag>non-stream</Tag>),
    },
    {
      title: t('usage_status'),
      dataIndex: 'error_code',
      key: 'error_code',
      width: 80,
      render: (v: number) =>
        v ? <Tag color="error">err</Tag> : <Tag color="success">ok</Tag>,
    },
  ];

  const hasData = ov.total_calls > 0;
  const singleConv = !!convId;

  return (
    <div className="p-6 h-full overflow-auto">
      <Row justify="space-between" align="middle" className="mb-4">
        <Title level={3} className="m-0">
          <BarChartOutlined className="mr-2" />
          {t('usage_page_title')}
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refreshAll}>
            {t('refresh', 'Refresh')}
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={handleClear} disabled={!hasData}>
            {t('usage_clear')}
          </Button>
        </Space>
      </Row>

      {/* Active conversation filter banner */}
      {singleConv && (
        <Card size="small" className="mb-4 shadow-sm" bodyStyle={{ padding: '8px 12px' }}>
          <Space>
            <BarChartOutlined />
            <span className="text-sm">{t('usage_conversation')}:</span>
            <Text code>{convId}</Text>
            <Tooltip title={t('usage_view_all', 'View all')}>
              <Button
                size="small"
                type="text"
                icon={<CloseOutlined />}
                onClick={() => {
                  setConvId(undefined);
                  setCallsPage(1);
                }}
              />
            </Tooltip>
          </Space>
        </Card>
      )}

      {/* Filters */}
      <Card size="small" className="mb-4 shadow-sm">
        <Space wrap size="middle">
          <span>{t('usage_agent')}:</span>
          <Select
            allowClear
            placeholder={t('usage_agent')}
            style={{ width: 200 }}
            value={agentId}
            onChange={v => setAgentId(v)}
            options={(agents || []).map(a => ({ label: a, value: a }))}
          />
          <span>{t('usage_model')}:</span>
          <Input
            allowClear
            placeholder={t('usage_model')}
            style={{ width: 200 }}
            value={modelName}
            onChange={e => setModelName(e.target.value || undefined)}
          />
          <span>{t('usage_time_range')}:</span>
          <Select
            style={{ width: 120 }}
            value={rangeKey}
            onChange={v => setRangeKey(v)}
            options={[
              { label: '1h', value: '1h' },
              { label: '24h', value: '24h' },
              { label: '7d', value: '7d' },
              { label: '30d', value: '30d' },
            ]}
          />
        </Space>
      </Card>

      {/* Overview stats */}
      <Row gutter={[12, 12]} className="mb-4">
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic title={t('usage_total_calls')} value={ov.total_calls} loading={overviewLoading} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic title={t('usage_prompt_tokens')} value={ov.prompt_tokens} loading={overviewLoading} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic title={t('usage_completion_tokens')} value={ov.completion_tokens} loading={overviewLoading} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic title={t('usage_total_tokens')} value={ov.total_tokens} loading={overviewLoading} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic
              title={t('usage_cost')}
              value={ov.cost_usd}
              precision={4}
              prefix="$"
              loading={overviewLoading}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic
              title={t('usage_avg_latency')}
              value={ov.avg_latency_ms != null ? Math.round(ov.avg_latency_ms) : 0}
              suffix="ms"
              loading={overviewLoading}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic
              title={t('usage_avg_speed')}
              value={ov.avg_tokens_per_sec != null ? Number(ov.avg_tokens_per_sec.toFixed(1)) : 0}
              suffix="tok/s"
              loading={overviewLoading}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6} lg={3}>
          <Card size="small" className="shadow-sm">
            <Statistic
              title={t('usage_error_calls')}
              value={ov.error_calls}
              valueStyle={{ color: ov.error_calls ? '#ef4444' : undefined }}
              loading={overviewLoading}
            />
          </Card>
        </Col>
      </Row>

      {!hasData ? (
        <Card className="shadow-sm">
          <Empty description={t('usage_no_data')} />
        </Card>
      ) : (
        <>
          {/* Charts */}
          <Row gutter={[12, 12]} className="mb-4">
            <Col xs={24} lg={12}>
              <Card size="small" title={t('usage_tokens_over_time')} className="shadow-sm">
                <div style={{ height: 280 }}>
                  {tokensSeries.length > 0 && (
                    <Chart
                      options={{
                        type: 'line',
                        data: tokensSeries,
                        encode: { x: 'x', y: 'tokens', color: 'kind' },
                        scale: { color: { range: ['#4f46e5', '#22c55e'] } },
                        axis: { x: { labelSpacing: 4 } },
                        legend: { color: true },
                        autoFit: true,
                        height: 280,
                      } as any}
                    />
                  )}
                </div>
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card size="small" title={t('usage_calls_over_time')} className="shadow-sm">
                <div style={{ height: 280 }}>
                  {callsSeries.length > 0 && (
                    <Chart
                      options={{
                        type: 'interval',
                        data: callsSeries,
                        encode: { x: 'x', y: 'calls' },
                        scale: { y: { nice: true } },
                        style: { fill: '#4f46e5' },
                        autoFit: true,
                        height: 280,
                      } as any}
                    />
                  )}
                </div>
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card size="small" title={t('usage_by_agent')} className="shadow-sm">
                <div style={{ height: 280 }}>
                  {(byAgent || []).length > 0 && (
                    <Chart
                      options={{
                        type: 'interval',
                        data: (byAgent || []).map(a => ({
                          agent: a.agent_id || 'unknown',
                          tokens: a.total_tokens,
                        })),
                        encode: { x: 'agent', y: 'tokens', color: 'agent' },
                        scale: { y: { nice: true } },
                        legend: false,
                        autoFit: true,
                        height: 280,
                      } as any}
                    />
                  )}
                </div>
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card size="small" title={t('usage_by_model')} className="shadow-sm">
                <div style={{ height: 280 }}>
                  {(byModel || []).length > 0 && (
                    <Chart
                      options={{
                        type: 'interval',
                        data: (byModel || []).map(m => ({
                          model: m.model_name,
                          tokens: m.total_tokens,
                        })),
                        encode: { y: 'tokens', color: 'model' },
                        transform: [{ type: 'stackY' }],
                        coordinate: { type: 'theta' },
                        legend: { color: true },
                        autoFit: true,
                        height: 280,
                      } as any}
                    />
                  )}
                </div>
              </Card>
            </Col>
          </Row>

          {/* By conversation (hidden in single-conv mode) */}
          {!singleConv && (
            <Card
              size="small"
              title={t('usage_by_conversation')}
              className="mb-4 shadow-sm"
            >
              <Table
                size="small"
                rowKey="conv_id"
                columns={convColumns}
                dataSource={byConv || []}
                pagination={{ pageSize: 10 }}
                onRow={r => ({
                  onClick: () => {
                    setConvId(r.conv_id);
                    setCallsPage(1);
                  },
                  style: { cursor: 'pointer' },
                })}
              />
            </Card>
          )}

          {/* Call details */}
          <Card
            size="small"
            title={
              <Space>
                <span>{t('usage_calls_detail')}</span>
                {singleConv && <Tag color="processing">{t('usage_conversation')}</Tag>}
              </Space>
            }
            className="shadow-sm"
          >
            <Table
              size="small"
              rowKey="id"
              columns={callColumns}
              dataSource={callsData?.items || []}
              loading={callsLoading}
              pagination={{
                current: callsPage,
                pageSize: 10,
                total: callsData?.total_count || 0,
                onChange: p => setCallsPage(p),
                showSizeChanger: false,
              }}
            />
          </Card>
        </>
      )}
    </div>
  );
}
