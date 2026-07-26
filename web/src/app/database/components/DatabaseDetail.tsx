'use client';

import {
  apiInterceptors,
  getDbSpec,
  getDbTables,
  getDbTableDetail,
  getDbLearnStatus,
  getDbTableData,
  postDbLearn,
  cancelDbLearn,
  pauseDbLearn,
  resumeDbLearn,
  getSensitiveColumns,
  addSensitiveColumn,
  toggleSensitiveColumn,
  toggleTableMasking,
  updateSensitiveColumn,
  detectSensitiveColumns,
  refreshTableSampleData,
  updateTableSpec,
  enrichTableDescriptions,
} from '@/client/api';
import {
  IChatDbSchema,
  DbSpecResponse,
  TableSpecSummary,
  TableSpecDetail,
  TableColumnUpdate,
  LearningTaskResponse,
  TableDataPreview,
  SensitiveColumnConfig,
  SENSITIVE_TYPES,
  MASKING_MODES,
  SENSITIVE_TYPE_OPTIONS,
  MASKING_MODE_OPTIONS,
} from '@/types/db';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  PauseOutlined,
  PlayCircleOutlined,
  SyncOutlined,
  TableOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  LockOutlined,
  PlusOutlined,
  SearchOutlined,
  EditOutlined,
  CheckOutlined,
  CloseOutlined,
  ThunderboltOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import {
  App,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Pagination,
  Popover,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import BatchMaskingModal from './BatchMaskingModal';

const { Text } = Typography;

/** Color map for sensitive type tags. */
const SENSITIVE_TYPE_COLORS: Record<string, string> = {
  phone: 'red',
  email: 'orange',
  id_card: 'volcano',
  bank_card: 'magenta',
  address: 'gold',
  name: 'cyan',
  password: 'purple',
  token: 'purple',
  ip_address: 'geekblue',
  custom: 'default',
};

interface DatabaseDetailProps {
  datasource: IChatDbSchema;
  onRefresh?: () => void;
}

export default function DatabaseDetail({
  datasource,
  onRefresh,
}: DatabaseDetailProps) {
  const { message } = App.useApp();
  const datasourceId = String(datasource.id);
  const [tableDetailDrawerOpen, setTableDetailDrawerOpen] = useState(false);
  const [selectedTableName, setSelectedTableName] = useState<string>('');
  const [editMode, setEditMode] = useState(false);
  const [editComment, setEditComment] = useState('');
  const [editGroup, setEditGroup] = useState('');
  const [editColumns, setEditColumns] = useState<TableColumnUpdate[]>([]);
  const [addSensitiveModalOpen, setAddSensitiveModalOpen] = useState(false);
  const [editSensitiveModalOpen, setEditSensitiveModalOpen] = useState(false);
  const [editingColumn, setEditingColumn] = useState<SensitiveColumnConfig | null>(null);
  const [batchMaskingModalOpen, setBatchMaskingModalOpen] = useState(false);
  const [tableSearchKeyword, setTableSearchKeyword] = useState('');
  const [tablePagination, setTablePagination] = useState({ current: 1, pageSize: 20 });
  const [overviewPagination, setOverviewPagination] = useState({ current: 1, pageSize: 20 });
  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();

  // Fetch DB spec
  const {
    data: dbSpec,
    loading: specLoading,
    refresh: refreshSpec,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbSpec(datasourceId));
    if (err) return null;
    return res as DbSpecResponse | null;
  });

  // Reset overview pagination when switching datasource
  useEffect(() => {
    setOverviewPagination((prev) => ({ ...prev, current: 1 }));
  }, [datasourceId]);

  // Fetch table specs (server-side paginated + searchable)
  const {
    data: tableSpecsResult,
    loading: tablesLoading,
    refresh: refreshTables,
  } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(
        getDbTables(datasourceId, {
          page: tablePagination.current,
          page_size: tablePagination.pageSize,
          keyword: tableSearchKeyword || undefined,
        }),
      );
      if (err) return { items: [], total: 0 };
      return res || { items: [], total: 0 };
    },
    {
      refreshDeps: [
        datasourceId,
        tablePagination.current,
        tablePagination.pageSize,
        tableSearchKeyword,
      ],
    },
  );

  // Fetch learning status
  const {
    data: learningStatus,
    refresh: refreshLearning,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbLearnStatus(datasourceId));
    if (err) return null;
    return res as LearningTaskResponse | null;
  });

  // Fetch all sensitive column configs for this datasource
  const {
    data: sensitiveColumns,
    refresh: refreshSensitive,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getSensitiveColumns(datasourceId));
    if (err) return [];
    return (res || []) as SensitiveColumnConfig[];
  });

  // Sensitive column count per table (for Tables tab)
  const sensitiveCountByTable = useMemo(() => {
    const map: Record<string, number> = {};
    for (const sc of sensitiveColumns || []) {
      map[sc.table_name] = (map[sc.table_name] || 0) + 1;
    }
    return map;
  }, [sensitiveColumns]);

  // Sensitive columns for the currently selected table
  const currentTableSensitive = useMemo(() => {
    if (!selectedTableName || !sensitiveColumns) return [];
    return sensitiveColumns.filter((sc) => sc.table_name === selectedTableName);
  }, [selectedTableName, sensitiveColumns]);

  // Map column_name → SensitiveColumnConfig for quick lookup in schema tab
  const sensitiveByColumn = useMemo(() => {
    const map: Record<string, SensitiveColumnConfig> = {};
    for (const sc of currentTableSensitive) {
      map[sc.column_name] = sc;
    }
    return map;
  }, [currentTableSensitive]);

  // Fetch table detail
  const {
    data: tableDetail,
    loading: tableDetailLoading,
    run: fetchTableDetail,
  } = useRequest(
    async (tableName: string) => {
      const [err, res] = await apiInterceptors(
        getDbTableDetail(datasourceId, tableName),
      );
      if (err) return null;
      return res as TableSpecDetail | null;
    },
    { manual: true },
  );

  // Fetch table data preview
  const {
    data: tableData,
    loading: tableDataLoading,
    run: fetchTableData,
  } = useRequest(
    async (tableName: string) => {
      const [err, res] = await apiInterceptors(
        getDbTableData(datasourceId, tableName),
      );
      if (err) return null;
      return res as TableDataPreview | null;
    },
    { manual: true },
  );

  // Trigger learning
  const { run: runLearn, loading: learnLoading } = useRequest(
    async (taskType?: string, tableName?: string) => {
      const [err] = await apiInterceptors(postDbLearn(datasourceId, {
        task_type: taskType as any,
        table_name: tableName,
      }));
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success('Learning task started');
        refreshLearning();
        refreshSpec();
        refreshTables();
        refreshSensitive();
        onRefresh?.();
      },
      onError: () => {
        message.error('Failed to start learning');
      },
    },
  );

  // Trigger incremental learning
  const { run: runIncrementalLearn, loading: incrementalLoading } = useRequest(
    async () => {
      const [err] = await apiInterceptors(postDbLearn(datasourceId, {
        task_type: 'incremental',
      }));
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success('Incremental learning task started');
        refreshLearning();
        refreshSpec();
        refreshTables();
        refreshSensitive();
        onRefresh?.();
      },
      onError: () => {
        message.error('Failed to start incremental learning');
      },
    },
  );

  // Refresh sample data for a single table
  const { run: runRefreshSample, loading: refreshSampleLoading } = useRequest(
    async () => {
      if (!selectedTableName) return;
      const [err] = await apiInterceptors(
        refreshTableSampleData(datasourceId, selectedTableName),
      );
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success('Sample data refreshed');
        fetchTableDetail(selectedTableName);
        fetchTableData(selectedTableName);
      },
      onError: () => {
        message.error('Failed to refresh sample data');
      },
    },
  );

  // Edit table spec (comment / group / columns)
  const enterEdit = useCallback(() => {
    if (!tableDetail) return;
    setEditComment(tableDetail.table_comment || '');
    setEditGroup(tableDetail.group_name || '');
    setEditColumns(
      (tableDetail.columns || []).map((c) => ({
        name: c.name,
        comment: c.comment ?? '',
        type: c.type ?? '',
        nullable: c.nullable,
        default: c.default ?? '',
        pk: c.pk,
      })),
    );
    setEditMode(true);
  }, [tableDetail]);

  const { run: runUpdateSpec, loading: updateSpecLoading } = useRequest(
    async () => {
      if (!selectedTableName) return;
      const [err] = await apiInterceptors(
        updateTableSpec(datasourceId, selectedTableName, {
          table_comment: editComment,
          group_name: editGroup,
          columns: editColumns,
        }),
      );
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success('Table spec updated');
        setEditMode(false);
        if (selectedTableName) {
          fetchTableDetail(selectedTableName);
        }
        refreshSpec();
        refreshTables();
      },
      onError: () => {
        message.error('Failed to update table spec');
      },
    },
  );

  // Regenerate LLM descriptions for a single table (table + column comments)
  const { run: runEnrich, loading: enrichLoading } = useRequest(
    async () => {
      if (!selectedTableName) return;
      const [err] = await apiInterceptors(
        enrichTableDescriptions(datasourceId, selectedTableName, true),
      );
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success('Descriptions regenerated');
        if (selectedTableName) {
          fetchTableDetail(selectedTableName);
        }
        refreshSpec();
        refreshTables();
      },
      onError: () => {
        message.error('Failed to regenerate descriptions');
      },
    },
  );

  // Cancel learning task
  const { run: runCancel, loading: cancelLoading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(cancelDbLearn(datasourceId));
      if (err) throw err;
      return res;
    },
    {
      manual: true,
      onSuccess: (data) => {
        if (data?.cancelled) {
          message.success('Learning task cancelled');
        } else {
          message.warning(data?.reason || 'No active task to cancel');
        }
        refreshLearning();
      },
      onError: () => {
        message.error('Failed to cancel learning task');
      },
    },
  );

  // Pause learning task
  const { run: runPause, loading: pauseLoading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(pauseDbLearn(datasourceId));
      if (err) throw err;
      return res;
    },
    {
      manual: true,
      onSuccess: (data) => {
        if (data?.paused) {
          message.success('Learning task paused');
        } else {
          message.warning(data?.reason || 'No running task to pause');
        }
        refreshLearning();
      },
      onError: () => {
        message.error('Failed to pause learning task');
      },
    },
  );

  // Resume learning task
  const { run: runResume, loading: resumeLoading } = useRequest(
    async () => {
      const [err, res] = await apiInterceptors(resumeDbLearn(datasourceId));
      if (err) throw err;
      return res;
    },
    {
      manual: true,
      onSuccess: (data) => {
        if (data?.resumed) {
          message.success('Learning task resumed');
        } else {
          message.warning(data?.reason || 'No paused task to resume');
        }
        refreshLearning();
      },
      onError: () => {
        message.error('Failed to resume learning task');
      },
    },
  );

  // Auto-poll learning status when task is active
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isActive = learningStatus?.status === 'running' || learningStatus?.status === 'finalizing' || learningStatus?.status === 'pending' || learningStatus?.status === 'paused';

  useEffect(() => {
    if (isActive) {
      pollingRef.current = setInterval(() => {
        refreshLearning();
      }, 3000);
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [isActive, refreshLearning]);

  // When learning completes, refresh spec and tables
  const prevStatusRef = useRef(learningStatus?.status);
  useEffect(() => {
    const prev = prevStatusRef.current;
    const curr = learningStatus?.status;
    prevStatusRef.current = curr;
    if (prev && prev !== curr && (curr === 'completed' || curr === 'failed' || curr === 'cancelled')) {
      refreshSpec();
      refreshTables();
      refreshSensitive();
      onRefresh?.();
    }
  }, [learningStatus?.status, refreshSpec, refreshTables, refreshSensitive, onRefresh]);

  // Auto-detect sensitive columns for a table
  const { run: runDetect, loading: detectLoading } = useRequest(
    async (tableNames?: string[]) => {
      const [err, res] = await apiInterceptors(
        detectSensitiveColumns(datasourceId, tableNames),
      );
      if (err) throw err;
      return res;
    },
    {
      manual: true,
      onSuccess: (data) => {
        const count = data?.length || 0;
        message.success(`Detected ${count} sensitive column(s)`);
        refreshSensitive();
        refreshTables();
      },
      onError: () => {
        message.error('Detection failed');
      },
    },
  );

  // Regenerate masking rules across the whole database (full-library detect).
  const confirmRegenerateAll = useCallback(() => {
    Modal.confirm({
      title: 'Regenerate Masking (All Tables)',
      content:
        '将对全库所有已学习表重新自动检测敏感字段。被检测到的列(含已手动配置的列)会被覆盖为自动结果(source=auto),不可撤销;未被识别的列不受影响。确认继续?',
      okText: 'Regenerate',
      okButtonProps: { danger: true },
      cancelText: 'Cancel',
      onOk: () => runDetect(undefined),
    });
  }, [runDetect]);

  // Toggle sensitive column enabled
  const handleToggleSensitive = useCallback(
    async (tableName: string, columnName: string, enabled: boolean) => {
      const [err] = await apiInterceptors(
        toggleSensitiveColumn(datasourceId, tableName, columnName, enabled),
      );
      if (err) {
        message.error('Failed to update masking status');
        return;
      }
      refreshSensitive();
    },
    [datasourceId, message, refreshSensitive],
  );

  // Enable/disable masking for ALL sensitive columns of the current table
  const handleToggleTable = useCallback(
    async (enabled: boolean) => {
      if (!selectedTableName) return;
      const [err] = await apiInterceptors(
        toggleTableMasking(datasourceId, selectedTableName, enabled),
      );
      if (err) {
        message.error('Failed to update table masking status');
        return;
      }
      message.success(
        enabled ? 'Masking enabled for all columns' : 'Masking disabled for all columns',
      );
      refreshSensitive();
    },
    [datasourceId, selectedTableName, message, refreshSensitive],
  );

  // Add sensitive column manually
  const handleAddSensitive = useCallback(async () => {
    try {
      const values = await addForm.validateFields();
      const [err] = await apiInterceptors(
        addSensitiveColumn(datasourceId, {
          table_name: selectedTableName,
          column_name: values.column_name,
          sensitive_type: values.sensitive_type,
          masking_mode: values.masking_mode,
        }),
      );
      if (err) throw err;
      message.success('Sensitive column added');
      setAddSensitiveModalOpen(false);
      addForm.resetFields();
      refreshSensitive();
    } catch {
      message.error('Failed to add sensitive column');
    }
  }, [datasourceId, selectedTableName, addForm, message, refreshSensitive]);

  // Edit sensitive column
  const handleEditSensitive = useCallback(async () => {
    if (!editingColumn) return;
    try {
      const values = await editForm.validateFields();
      const [err] = await apiInterceptors(
        updateSensitiveColumn(
          datasourceId,
          editingColumn.table_name,
          editingColumn.column_name,
          {
            sensitive_type: values.sensitive_type,
            masking_mode: values.masking_mode,
          },
        ),
      );
      if (err) throw err;
      message.success('Sensitive column updated');
      setEditSensitiveModalOpen(false);
      setEditingColumn(null);
      refreshSensitive();
    } catch {
      message.error('Failed to update');
    }
  }, [datasourceId, editingColumn, editForm, message, refreshSensitive]);

  const handleViewTable = useCallback(
    (tableName: string) => {
      setSelectedTableName(tableName);
      setTableDetailDrawerOpen(true);
      fetchTableDetail(tableName);
      fetchTableData(tableName);
    },
    [fetchTableDetail, fetchTableData],
  );

  const refreshAll = useCallback(() => {
    refreshSpec();
    refreshTables();
    refreshLearning();
    refreshSensitive();
  }, [refreshSpec, refreshTables, refreshLearning, refreshSensitive]);

  // Table columns for table spec list (Tables tab)
  const tableColumns = [
    {
      title: 'Table Name',
      dataIndex: 'table_name',
      key: 'table_name',
      render: (name: string) => (
        <a
          onClick={() => handleViewTable(name)}
          className="text-blue-500 hover:text-blue-700"
        >
          <TableOutlined className="mr-1" />
          {name}
        </a>
      ),
    },
    {
      title: 'Comment',
      dataIndex: 'table_comment',
      key: 'table_comment',
      ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: 'Row Count',
      dataIndex: 'row_count',
      key: 'row_count',
      render: (v: number | null) =>
        v !== null && v !== undefined ? v.toLocaleString() : '-',
    },
    {
      title: 'Columns',
      dataIndex: 'column_count',
      key: 'column_count',
    },
    {
      title: 'Sensitive',
      key: 'sensitive_count',
      render: (_: any, record: TableSpecSummary) => {
        const count = sensitiveCountByTable[record.table_name] || 0;
        return count > 0 ? (
          <Tag color="red" icon={<LockOutlined />}>
            {count}
          </Tag>
        ) : (
          '-'
        );
      },
    },
    {
      title: 'Group',
      dataIndex: 'group_name',
      key: 'group_name',
      render: (v: string | null) => (v ? <Tag>{v}</Tag> : '-'),
    },
  ];

  const renderSpecOverview = () => {
    if (specLoading) return <Empty description="Loading..." />;
    if (!dbSpec) return <Empty description="No spec generated yet. Click 'Learn Schema' to start." />;

    return (
      <div>
        <Descriptions bordered column={2} size="small" className="mb-4">
          <Descriptions.Item label="Database Type">
            <Tag color="blue">{dbSpec.db_type}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            {dbSpec.status === 'ready' ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>
                Ready
              </Tag>
            ) : dbSpec.status === 'generating' ? (
              <Tag color="processing" icon={<SyncOutlined spin />}>
                Generating
              </Tag>
            ) : (
              <Tag color="error" icon={<CloseCircleOutlined />}>
                Failed
              </Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Table Count">
            {dbSpec.table_count ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="Last Updated">
            {dbSpec.gmt_modified || '-'}
          </Descriptions.Item>
        </Descriptions>

        {dbSpec.spec_content && dbSpec.spec_content.length > 0 && (
          <Card title={`Table Index (${dbSpec.spec_content.length})`} size="small">
            {(() => {
              const total = dbSpec.spec_content.length;
              const pageSize = overviewPagination.pageSize;
              const current = Math.min(
                overviewPagination.current,
                Math.max(1, Math.ceil(total / pageSize)),
              );
              const start = (current - 1) * pageSize;
              const pageItems = dbSpec.spec_content.slice(
                start,
                start + pageSize,
              );
              return (
                <>
                  {pageItems.map((entry) => (
                    <div
                      key={entry.table_name}
                      className="py-1 border-b border-gray-100 last:border-0"
                    >
                      <a
                        onClick={() => handleViewTable(entry.table_name)}
                        className="text-blue-500 hover:text-blue-700 cursor-pointer"
                      >
                        {entry.table_name}
                      </a>
                      <Text type="secondary" className="ml-2">
                        {entry.row_count !== null
                          ? `${entry.row_count?.toLocaleString()} rows`
                          : ''}
                      </Text>
                      {entry.group && entry.group !== 'default' && (
                        <Tag className="ml-2" color="default">
                          {entry.group}
                        </Tag>
                      )}
                      <br />
                      <Text type="secondary" className="text-xs">
                        {entry.summary}
                      </Text>
                    </div>
                  ))}
                  <div className="mt-4 flex justify-end">
                    <Pagination
                      current={current}
                      pageSize={pageSize}
                      total={total}
                      showSizeChanger
                      showTotal={(t) => `Total ${t} tables`}
                      onChange={(page, ps) =>
                        setOverviewPagination({ current: page, pageSize: ps })
                      }
                    />
                  </div>
                </>
              );
            })()}
          </Card>
        )}
      </div>
    );
  };

  const renderLearningStatus = () => {
    const canCancel = learningStatus?.status === 'running' || learningStatus?.status === 'finalizing';
    const canLearn = !canCancel && learningStatus?.status !== 'paused' && dbSpec?.status !== 'generating';
    const canIncremental = canLearn && dbSpec?.status === 'ready';

    const statusColorMap: Record<string, string> = {
      completed: 'success',
      running: 'processing',
      finalizing: 'processing',
      pending: 'default',
      paused: 'warning',
      failed: 'error',
      cancelled: 'warning',
    };

    const progressStatusMap: Record<string, 'active' | 'success' | 'exception' | 'normal'> = {
      completed: 'success',
      failed: 'exception',
      cancelled: 'exception',
      running: 'active',
      finalizing: 'active',
      pending: 'normal',
    };

    return (
      <div>
        <Space direction="vertical" className="w-full">
          <Space wrap>
            <Button
              type="primary"
              icon={<SyncOutlined />}
              loading={learnLoading}
              onClick={() => runLearn('full_learn')}
              disabled={canCancel}
            >
              Full Learn
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={incrementalLoading}
              onClick={runIncrementalLearn}
              disabled={!canIncremental}
            >
              Incremental Learn
            </Button>
            {canCancel && (
              <Button
                danger
                icon={<StopOutlined />}
                loading={cancelLoading}
                onClick={() => {
                  Modal.confirm({
                    title: 'Cancel Learning Task',
                    content: 'Are you sure you want to cancel the running learning task? Tables already processed will be kept.',
                    okText: 'Cancel Task',
                    okButtonProps: { danger: true },
                    onOk: runCancel,
                  });
                }}
              >
                Cancel Task
              </Button>
            )}
            {learningStatus?.status === 'running' && (
              <Button
                icon={<PauseOutlined />}
                loading={pauseLoading}
                onClick={() => {
                  Modal.confirm({
                    title: 'Pause Learning Task',
                    content: 'The task will be paused. You can resume it later.',
                    okText: 'Pause',
                    onOk: runPause,
                  });
                }}
              >
                Pause
              </Button>
            )}
            {learningStatus?.status === 'paused' && (
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={resumeLoading}
                onClick={() => {
                  Modal.confirm({
                    title: 'Resume Learning Task',
                    content: 'Resume the paused learning task.',
                    okText: 'Resume',
                    onOk: runResume,
                  });
                }}
              >
                Resume
              </Button>
            )}
          </Space>

          {!canLearn && !canCancel && (
            <Text type="secondary">
              Learning is already in progress. Wait for completion or cancel to start new task.
            </Text>
          )}
          {!canIncremental && dbSpec?.status !== 'ready' && (
            <Text type="secondary">
              Incremental learning requires existing spec. Run full learn first.
            </Text>
          )}

          {learningStatus && (
            <Card title="Latest Learning Task" size="small">
              <Descriptions column={2} size="small">
                <Descriptions.Item label="Status">
                  <Tag
                    color={statusColorMap[learningStatus.status] || 'default'}
                    icon={
                      learningStatus.status === 'running' || learningStatus.status === 'finalizing'
                        ? <SyncOutlined spin />
                        : learningStatus.status === 'cancelled'
                          ? <StopOutlined />
                          : learningStatus.status === 'paused'
                            ? <PauseOutlined />
                            : undefined
                    }
                  >
                    {learningStatus.status}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Type">
                  {learningStatus.task_type}
                </Descriptions.Item>
                <Descriptions.Item label="Progress">
                  <Progress
                    percent={learningStatus.progress}
                    size="small"
                    status={progressStatusMap[learningStatus.status] || 'normal'}
                  />
                </Descriptions.Item>
                <Descriptions.Item label="Tables">
                  {learningStatus.processed_tables}/{learningStatus.total_tables ?? '?'}
                </Descriptions.Item>
                <Descriptions.Item label="Trigger">
                  {learningStatus.trigger_type}
                </Descriptions.Item>
                <Descriptions.Item label="Started">
                  {learningStatus.gmt_created || '-'}
                </Descriptions.Item>
              </Descriptions>
              {learningStatus.error_message && (
                <div className="mt-2">
                  <Text type="danger">{learningStatus.error_message}</Text>
                </div>
              )}
            </Card>
          )}
        </Space>
      </div>
    );
  };

  /** Render the Sensitive Columns tab inside the table detail drawer. */
  const renderSensitiveColumnsTab = () => {
    const configuredNames = new Set(currentTableSensitive.map((sc) => sc.column_name));
    const availableColumns = (tableDetail?.columns || [])
      .map((c) => c.name)
      .filter((name) => !configuredNames.has(name));

    return (
      <div>
        <Space className="mb-4">
          <Button
            icon={<SearchOutlined />}
            loading={detectLoading}
            onClick={() => runDetect([selectedTableName])}
          >
            Auto Detect
          </Button>
          <Button
            icon={<PlusOutlined />}
            onClick={() => {
              addForm.resetFields();
              setAddSensitiveModalOpen(true);
            }}
          >
            Add Manual
          </Button>
          {currentTableSensitive.length > 0 && (
            <>
              <Button size="small" onClick={() => handleToggleTable(true)}>
                Enable All
              </Button>
              <Button size="small" onClick={() => handleToggleTable(false)}>
                Disable All
              </Button>
            </>
          )}
        </Space>

        <Table
          dataSource={currentTableSensitive.map((sc, idx) => ({
            key: idx,
            ...sc,
          }))}
          pagination={false}
          size="small"
          locale={{
            emptyText: (
              <Empty description="No sensitive columns configured. Click 'Auto Detect' to scan." />
            ),
          }}
          columns={[
            {
              title: 'Column',
              dataIndex: 'column_name',
              key: 'column_name',
            },
            {
              title: 'Type',
              dataIndex: 'sensitive_type',
              key: 'sensitive_type',
              render: (v: string) => (
                <Tag color={SENSITIVE_TYPE_COLORS[v] || 'default'}>{v}</Tag>
              ),
            },
            {
              title: 'Mode',
              dataIndex: 'masking_mode',
              key: 'masking_mode',
              render: (v: string) => {
                const label = v === 'mask' ? 'Partial Mask' : v === 'token' ? 'Tokenize' : 'None';
                return <Tag>{label}</Tag>;
              },
            },
            {
              title: 'Confidence',
              dataIndex: 'confidence',
              key: 'confidence',
              render: (v: number | null) =>
                v !== null && v !== undefined
                  ? `${(v * 100).toFixed(0)}%`
                  : '-',
            },
            {
              title: 'Source',
              dataIndex: 'source',
              key: 'source',
              render: (v: string) => (
                <Tag color={v === 'auto' ? 'blue' : 'green'}>{v}</Tag>
              ),
            },
            {
              title: 'Enabled',
              dataIndex: 'enabled',
              key: 'enabled',
              render: (v: boolean, record: SensitiveColumnConfig) => (
                <Switch
                  size="small"
                  checked={v}
                  onChange={(checked) =>
                    handleToggleSensitive(
                      record.table_name,
                      record.column_name,
                      checked,
                    )
                  }
                />
              ),
            },
            {
              title: 'Action',
              key: 'action',
              render: (_: any, record: SensitiveColumnConfig) => (
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => {
                    setEditingColumn(record);
                    editForm.setFieldsValue({
                      sensitive_type: record.sensitive_type,
                      masking_mode: record.masking_mode,
                    });
                    setEditSensitiveModalOpen(true);
                  }}
                >
                  Edit
                </Button>
              ),
            },
          ]}
        />

        {/* Add Sensitive Column Modal */}
        <Modal
          title="Add Sensitive Column"
          open={addSensitiveModalOpen}
          onOk={handleAddSensitive}
          onCancel={() => setAddSensitiveModalOpen(false)}
          destroyOnHidden
        >
          <Form form={addForm} layout="vertical">
            <Form.Item
              name="column_name"
              label="Column"
              rules={[{ required: true, message: 'Select a column' }]}
            >
              <Select placeholder="Select column">
                {availableColumns.map((name) => (
                  <Select.Option key={name} value={name}>
                    {name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item
              name="sensitive_type"
              label="Sensitive Type"
              rules={[{ required: true, message: 'Select sensitive type' }]}
            >
              <Select placeholder="Select type">
                {SENSITIVE_TYPES.map((t) => (
                  <Select.Option key={t} value={t}>
                    {t}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item
              name="masking_mode"
              label="Masking Mode"
              initialValue="mask"
              rules={[{ required: true }]}
            >
              <Select>
                {MASKING_MODES.map((m) => (
                  <Select.Option key={m} value={m}>
                    {m === 'mask' ? 'Partial Mask' : m === 'token' ? 'Tokenize' : 'None'}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Form>
        </Modal>

        {/* Edit Sensitive Column Modal */}
        <Modal
          title={`Edit: ${editingColumn?.column_name || ''}`}
          open={editSensitiveModalOpen}
          onOk={handleEditSensitive}
          onCancel={() => {
            setEditSensitiveModalOpen(false);
            setEditingColumn(null);
          }}
          destroyOnHidden
        >
          <Form form={editForm} layout="vertical">
            <Form.Item
              name="sensitive_type"
              label="Sensitive Type"
              rules={[{ required: true }]}
            >
              <Select>
                {SENSITIVE_TYPES.map((t) => (
                  <Select.Option key={t} value={t}>
                    {t}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item
              name="masking_mode"
              label="Masking Mode"
              rules={[{ required: true }]}
            >
              <Select>
                {MASKING_MODES.map((m) => (
                  <Select.Option key={m} value={m}>
                    {m === 'mask' ? 'Partial Mask' : m === 'token' ? 'Tokenize' : 'None'}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Form>
        </Modal>
      </div>
    );
  };

  const renderTableDetail = () => {
    if (tableDetailLoading) return <Empty description="Loading..." />;
    if (!tableDetail) return <Empty description="No data" />;

    const columnTableData = (tableDetail.columns || []).map(
      (col, idx) => ({
        key: idx,
        ...col,
      }),
    );

    const indexTableData = (tableDetail.indexes || []).map(
      (idx, i) => ({
        key: i,
        ...idx,
        columns_str: (idx.columns || []).join(', '),
      }),
    );

    const updateEditColumn = (
      idx: number,
      field: keyof TableColumnUpdate,
      value: string | boolean,
    ) => {
      setEditColumns((prev) =>
        prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)),
      );
    };

    const editColumnRows = editColumns.map((c, i) => ({ ...c, key: i }));

    return (
      <Tabs
        defaultActiveKey="schema"
        items={[
          {
            key: 'schema',
            label: 'Schema',
            children: (
              <div>
                {/* Table actions */}
                <Space className="mb-4">
                  <Button
                    icon={<SyncOutlined />}
                    loading={learnLoading}
                    onClick={() => runLearn('single_table', selectedTableName)}
                    size="small"
                    disabled={editMode}
                  >
                    Refresh Schema
                  </Button>
                  <Button
                    icon={<ReloadOutlined />}
                    loading={refreshSampleLoading}
                    onClick={runRefreshSample}
                    size="small"
                    disabled={editMode}
                  >
                    Refresh Sample Data
                  </Button>
                  {editMode ? (
                    <>
                      <Button
                        type="primary"
                        icon={<CheckOutlined />}
                        loading={updateSpecLoading}
                        onClick={runUpdateSpec}
                        size="small"
                      >
                        Save
                      </Button>
                      <Button
                        icon={<CloseOutlined />}
                        onClick={() => setEditMode(false)}
                        size="small"
                      >
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button
                        icon={<EditOutlined />}
                        onClick={enterEdit}
                        size="small"
                      >
                        Edit
                      </Button>
                      <Button
                        icon={<ThunderboltOutlined />}
                        loading={enrichLoading}
                        onClick={runEnrich}
                        size="small"
                      >
                        Regenerate Descriptions
                      </Button>
                    </>
                  )}
                </Space>

                <Descriptions bordered column={2} size="small" className="mb-4">
                  <Descriptions.Item label="Table">{tableDetail.table_name}</Descriptions.Item>
                  <Descriptions.Item label="Comment">
                    {editMode ? (
                      <Input.TextArea
                        value={editComment}
                        onChange={(e) => setEditComment(e.target.value)}
                        autoSize={{ minRows: 1, maxRows: 4 }}
                      />
                    ) : (
                      tableDetail.table_comment || '-'
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="Row Count">
                    {(tableData?.total ?? tableDetail.row_count)?.toLocaleString() ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Group">
                    {editMode ? (
                      <Input
                        value={editGroup}
                        onChange={(e) => setEditGroup(e.target.value)}
                        size="small"
                      />
                    ) : (
                      tableDetail.group_name || '-'
                    )}
                  </Descriptions.Item>
                </Descriptions>

                <h4 className="font-semibold mb-2">
                  Columns ({editMode ? editColumns.length : columnTableData.length})
                </h4>
                <Table
                  dataSource={editMode ? editColumnRows : columnTableData}
                  pagination={false}
                  size="small"
                  columns={editMode ? [
                    { title: 'Name', dataIndex: 'name', key: 'name' },
                    {
                      title: 'Type',
                      dataIndex: 'type',
                      key: 'type',
                      render: (v: string, _r: any, idx: number) => (
                        <Input
                          size="small"
                          value={v ?? ''}
                          onChange={(e) => updateEditColumn(idx, 'type', e.target.value)}
                        />
                      ),
                    },
                    {
                      title: 'Nullable',
                      dataIndex: 'nullable',
                      key: 'nullable',
                      render: (v: boolean, _r: any, idx: number) => (
                        <Switch
                          size="small"
                          checked={!!v}
                          onChange={(c) => updateEditColumn(idx, 'nullable', c)}
                        />
                      ),
                    },
                    {
                      title: 'PK',
                      dataIndex: 'pk',
                      key: 'pk',
                      render: (v: boolean, _r: any, idx: number) => (
                        <Switch
                          size="small"
                          checked={!!v}
                          onChange={(c) => updateEditColumn(idx, 'pk', c)}
                        />
                      ),
                    },
                    {
                      title: 'Comment',
                      dataIndex: 'comment',
                      key: 'comment',
                      render: (v: string, _r: any, idx: number) => (
                        <Input
                          size="small"
                          value={v ?? ''}
                          onChange={(e) => updateEditColumn(idx, 'comment', e.target.value)}
                        />
                      ),
                    },
                  ] : [
                    { title: 'Name', dataIndex: 'name', key: 'name' },
                    { title: 'Type', dataIndex: 'type', key: 'type' },
                    {
                      title: 'Nullable',
                      dataIndex: 'nullable',
                      key: 'nullable',
                      render: (v: boolean) => (v ? 'YES' : 'NO'),
                    },
                    {
                      title: 'PK',
                      dataIndex: 'pk',
                      key: 'pk',
                      render: (v: boolean) =>
                        v ? <Tag color="gold">PK</Tag> : '-',
                    },
                    {
                      title: 'Comment',
                      dataIndex: 'comment',
                      key: 'comment',
                      ellipsis: true,
                      render: (v: string | null) => v || '-',
                    },
                    {
                      title: 'Sensitive',
                      key: 'sensitive',
                      render: (_: any, record: any) => {
                        const sc = sensitiveByColumn[record.name];
                        return (
                          <InlineMaskingConfig
                            datasourceId={datasourceId}
                            tableName={selectedTableName}
                            columnName={record.name}
                            existing={sc || null}
                            onSaved={refreshSensitive}
                          />
                        );
                      },
                    },
                    {
                      title: 'Masking',
                      key: 'masking',
                      render: (_: any, record: any) => {
                        const sc = sensitiveByColumn[record.name];
                        if (!sc) return '-';
                        return (
                          <Switch
                            size="small"
                            checked={sc.enabled}
                            onChange={(checked) =>
                              handleToggleSensitive(
                                selectedTableName,
                                record.name,
                                checked,
                              )
                            }
                          />
                        );
                      },
                    },
                  ]}
                />

                {indexTableData.length > 0 && (
                  <>
                    <h4 className="font-semibold mb-2 mt-4">
                      Indexes ({indexTableData.length})
                    </h4>
                    <Table
                      dataSource={indexTableData}
                      pagination={false}
                      size="small"
                      columns={[
                        { title: 'Name', dataIndex: 'name', key: 'name' },
                        {
                          title: 'Columns',
                          dataIndex: 'columns_str',
                          key: 'columns_str',
                        },
                        {
                          title: 'Unique',
                          dataIndex: 'unique',
                          key: 'unique',
                          render: (v: boolean) => (v ? 'YES' : 'NO'),
                        },
                      ]}
                    />
                  </>
                )}

                {tableDetail.foreign_keys && tableDetail.foreign_keys.length > 0 && (
                  <>
                    <h4 className="font-semibold mb-2 mt-4">
                      Foreign Keys ({tableDetail.foreign_keys.length})
                    </h4>
                    <Table
                      dataSource={tableDetail.foreign_keys.map((fk, i) => ({
                        key: i,
                        columns: fk.constrained_columns.join(', '),
                        referred_table: fk.referred_table,
                        referred_columns: fk.referred_columns.join(', '),
                      }))}
                      pagination={false}
                      size="small"
                      columns={[
                        {
                          title: 'Columns',
                          dataIndex: 'columns',
                          key: 'columns',
                        },
                        {
                          title: 'References Table',
                          dataIndex: 'referred_table',
                          key: 'referred_table',
                          render: (v: string) => (
                            <a
                              onClick={() => {
                                setSelectedTableName(v);
                                fetchTableDetail(v);
                                fetchTableData(v);
                              }}
                              className="text-blue-500 hover:text-blue-700 cursor-pointer"
                            >
                              {v}
                            </a>
                          ),
                        },
                        {
                          title: 'Referenced Columns',
                          dataIndex: 'referred_columns',
                          key: 'referred_columns',
                        },
                      ]}
                    />
                  </>
                )}
              </div>
            ),
          },
          {
            key: 'sensitive',
            label: (
              <span>
                <LockOutlined /> Sensitive Columns
                {currentTableSensitive.length > 0 && (
                  <Tag color="red" className="ml-1" style={{ marginRight: 0 }}>
                    {currentTableSensitive.length}
                  </Tag>
                )}
              </span>
            ),
            children: renderSensitiveColumnsTab(),
          },
          {
            key: 'ddl',
            label: 'DDL',
            children: tableDetail.create_ddl ? (
              <pre className="bg-gray-50 p-4 rounded text-sm overflow-auto max-h-96">
                {tableDetail.create_ddl}
              </pre>
            ) : (
              <Empty description="No DDL available" />
            ),
          },
          {
            key: 'data',
            label: 'Data Preview',
            children: (
              <div>
                {/* Refresh sample data button */}
                <Button
                  icon={<ReloadOutlined />}
                  loading={refreshSampleLoading}
                  onClick={runRefreshSample}
                  size="small"
                  className="mb-3"
                >
                  Refresh Sample Data
                </Button>

                {tableDataLoading && <Empty description="Loading..." />}
                {tableData && (() => {
                  const maskedSet = new Set(tableData.masked_columns || []);
                  const buildColumns = () =>
                    tableData.columns.map((col) => ({
                      title: maskedSet.has(col) ? (
                        <Tooltip title="This column is masked by privacy rules / 该列已按隐私规则脱敏">
                          <span>
                            <LockOutlined style={{ marginRight: 4, color: '#faad14' }} />
                            {col}
                          </span>
                        </Tooltip>
                      ) : (
                        col
                      ),
                      dataIndex: col,
                      key: col,
                      ellipsis: true,
                    }));
                  return (
                  <>
                    <Text type="secondary" className="mb-3 block">
                      Total: {tableData.total.toLocaleString()} rows
                      {maskedSet.size > 0 && (
                        <Tag color="warning" className="ml-2">
                          <LockOutlined /> {maskedSet.size} masked column(s)
                        </Tag>
                      )}
                    </Text>
                    {tableData.first_rows.length > 0 && (
                      <>
                        {tableData.last_rows.length > 0 && (
                          <h4 className="font-semibold mb-2">First 5 Rows</h4>
                        )}
                        <Table
                          dataSource={tableData.first_rows.map((row, idx) => {
                            const obj: any = { key: `first-${idx}` };
                            tableData.columns.forEach((col, ci) => {
                              obj[col] = row[ci];
                            });
                            return obj;
                          })}
                          columns={buildColumns()}
                          pagination={false}
                          size="small"
                          scroll={{ x: 'max-content' }}
                        />
                      </>
                    )}
                    {tableData.last_rows.length > 0 && (
                      <>
                        <h4 className="font-semibold mb-2 mt-4">Last 5 Rows</h4>
                        <Table
                          dataSource={tableData.last_rows.map((row, idx) => {
                            const obj: any = { key: `last-${idx}` };
                            tableData.columns.forEach((col, ci) => {
                              obj[col] = row[ci];
                            });
                            return obj;
                          })}
                          columns={buildColumns()}
                          pagination={false}
                          size="small"
                          scroll={{ x: 'max-content' }}
                        />
                      </>
                    )}
                  </>
                  );
                })()}
                {!tableData && !tableDataLoading && (
                  <Empty description="No data" />
                )}
              </div>
            ),
          },
        ]}
      />
    );
  };

  return (
    <div>
      <div className="mb-4">
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refreshAll} size="small">
            Refresh All
          </Button>
          <Button
            icon={<SafetyCertificateOutlined />}
            onClick={confirmRegenerateAll}
            size="small"
          >
            Regenerate Masking (All Tables)
          </Button>
        </Space>
      </div>

      <Tabs
        defaultActiveKey="overview"
        items={[
          {
            key: 'overview',
            label: (
              <span>
                <DatabaseOutlined /> Overview
              </span>
            ),
            children: renderSpecOverview(),
          },
          {
            key: 'tables',
            label: (
              <span>
                <TableOutlined /> Tables
              </span>
            ),
            children: (
              <div>
                <Space className="mb-4" wrap>
                  <Button
                    icon={<SafetyCertificateOutlined />}
                    onClick={() => setBatchMaskingModalOpen(true)}
                    size="small"
                  >
                    Batch Masking
                  </Button>
                  <Input
                    placeholder="Search by name or comment..."
                    prefix={<SearchOutlined />}
                    allowClear
                    value={tableSearchKeyword}
                    onChange={(e) => {
                      setTableSearchKeyword(e.target.value);
                      setTablePagination((prev) => ({ ...prev, current: 1 }));
                    }}
                    style={{ width: 280 }}
                    size="small"
                  />
                </Space>
                <Table
                  columns={tableColumns}
                  dataSource={tableSpecsResult?.items || []}
                  rowKey="table_name"
                  loading={tablesLoading}
                  size="small"
                  pagination={{
                    current: tablePagination.current,
                    pageSize: tablePagination.pageSize,
                    total: tableSpecsResult?.total || 0,
                    showSizeChanger: true,
                    pageSizeOptions: [10, 20, 50, 100],
                    showTotal: (total) => `Total ${total} tables`,
                    onChange: (current, pageSize) =>
                      setTablePagination({
                        current:
                          pageSize !== tablePagination.pageSize ? 1 : current,
                        pageSize: pageSize || 20,
                      }),
                  }}
                  locale={{
                    emptyText: tableSearchKeyword ? (
                      <Empty description="No tables match your search." />
                    ) : (
                      <Empty description="No table specs. Run schema learning first." />
                    ),
                  }}
                />
              </div>
            ),
          },
          {
            key: 'learning',
            label: (
              <span>
                <SyncOutlined /> Learning
              </span>
            ),
            children: renderLearningStatus(),
          },
        ]}
      />

      {/* Table Detail Drawer */}
      <Drawer
        title={
          <span>
            <TableOutlined className="mr-2" />
            {selectedTableName}
          </span>
        }
        placement="right"
        width={700}
        open={tableDetailDrawerOpen}
        onClose={() => setTableDetailDrawerOpen(false)}
        destroyOnHidden
      >
        {renderTableDetail()}
      </Drawer>

      {/* Batch Masking Modal */}
      <BatchMaskingModal
        open={batchMaskingModalOpen}
        datasourceId={Number(datasourceId)}
        onCancel={() => setBatchMaskingModalOpen(false)}
        onSuccess={() => {
          refreshSensitive();
          refreshTables();
        }}
      />
    </div>
  );
}

/** Inline masking config popover for a single column cell in the Schema tab. */
function InlineMaskingConfig({
  datasourceId,
  tableName,
  columnName,
  existing,
  onSaved,
}: {
  datasourceId: string;
  tableName: string;
  columnName: string;
  existing: SensitiveColumnConfig | null;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleOpen = (next: boolean) => {
    if (next) {
      form.setFieldsValue({
        sensitive_type: existing?.sensitive_type || 'phone',
        masking_mode: existing?.masking_mode || 'mask',
      });
    }
    setOpen(next);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (existing) {
        const [err] = await apiInterceptors(
          updateSensitiveColumn(datasourceId, tableName, columnName, {
            sensitive_type: values.sensitive_type,
            masking_mode: values.masking_mode,
          }),
        );
        if (err) throw err;
      } else {
        const [err] = await apiInterceptors(
          addSensitiveColumn(datasourceId, {
            table_name: tableName,
            column_name: columnName,
            sensitive_type: values.sensitive_type,
            masking_mode: values.masking_mode,
          }),
        );
        if (err) throw err;
      }
      message.success(existing ? 'Masking updated' : 'Masking configured');
      setOpen(false);
      onSaved();
    } catch {
      message.error('Failed to save masking config');
    } finally {
      setSaving(false);
    }
  };

  const content = (
    <Form form={form} layout="vertical" size="small" style={{ width: 220 }}>
      <Form.Item
        name="sensitive_type"
        label="Sensitive Type"
        rules={[{ required: true }]}
      >
        <Select
          options={SENSITIVE_TYPE_OPTIONS.map((o) => ({
            value: o.value,
            label: `${o.label} (${o.labelEn})`,
          }))}
        />
      </Form.Item>
      <Form.Item
        name="masking_mode"
        label="Masking Mode"
        rules={[{ required: true }]}
      >
        <Select
          options={MASKING_MODE_OPTIONS.map((o) => ({
            value: o.value,
            label: `${o.label} (${o.labelEn})`,
          }))}
        />
      </Form.Item>
      <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
        <Button size="small" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button size="small" type="primary" loading={saving} onClick={handleSave}>
          Save
        </Button>
      </Space>
    </Form>
  );

  if (!existing) {
    return (
      <Popover
        content={content}
        trigger="click"
        open={open}
        onOpenChange={handleOpen}
        placement="right"
      >
        <Button type="link" size="small" icon={<PlusOutlined />}>
          配置
        </Button>
      </Popover>
    );
  }

  return (
    <Popover
      content={content}
      trigger="click"
      open={open}
      onOpenChange={handleOpen}
      placement="right"
    >
      <Space size={4}>
        <Tooltip title={`Mode: ${existing.masking_mode}`}>
          <Tag color={SENSITIVE_TYPE_COLORS[existing.sensitive_type] || 'default'}>
            <LockOutlined className="mr-1" />
            {existing.sensitive_type}
          </Tag>
        </Tooltip>
        <Button type="text" size="small" icon={<EditOutlined />} />
      </Space>
    </Popover>
  );
}
