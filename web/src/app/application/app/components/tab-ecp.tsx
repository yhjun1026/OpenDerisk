'use client';
import { apiInterceptors } from '@/client/api';
import { getEcpLinkedResources, type EcpLinkedResource } from '@/client/api/ecp';
import { listWorkspaces } from '@/client/api/workspace';
import { AppContext } from '@/contexts';
import { getUserId } from '@/utils/storage';
import { CheckCircleFilled, DatabaseOutlined, SafetyCertificateOutlined, ReloadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Spin, Tag, Tooltip, App } from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function TabEcp() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const { message } = App.useApp();
  const [linkedResources, setLinkedResources] = useState<EcpLinkedResource[]>([]);

  // 可绑定的 ECP workspace 全集:全局共享库(default) + 各场景空间派生(ecp_<code>)
  const { data: ecpWorkspaces } = useRequest(async () => {
    const [err, res] = await apiInterceptors(
      listWorkspaces({ user_id: Number(getUserId()) || 0 }),
    );
    const list: Array<{ workspace_code: string; name: string }> = err
      ? []
      : ((res as any) ?? []);
    return [
      { workspace_id: 'default', label: '全局共享库 (default)' },
      ...list.map(ws => ({
        workspace_id: `ecp_${ws.workspace_code}`,
        label: `场景空间：${ws.name}`,
      })),
    ];
  });

  // Check if ECP resource is already bound
  const boundEcpWorkspace = useMemo(() => {
    const resourceTool = appInfo?.resource_tool || [];
    for (const item of resourceTool) {
      if (item.type === 'ecp') {
        try {
          const parsed = JSON.parse(item.value || '{}');
          return parsed.workspace_id || 'default';
        } catch {
          return 'default';
        }
      }
    }
    return null;
  }, [appInfo?.resource_tool]);

  // Get currently bound datasource ids (for showing auto-linked status)
  const boundDatasourceIds = useMemo(() => {
    const resourceTool = appInfo?.resource_tool || [];
    return resourceTool
      .filter((item: any) => item.type === 'datasource')
      .map((item: any) => {
        try {
          const parsed = JSON.parse(item.value || '{}');
          return parsed.id;
        } catch {
          return null;
        }
      })
      .filter(Boolean);
  }, [appInfo?.resource_tool]);

  // Fetch linked resources when workspace is bound
  const { loading: linkedLoading, refresh: refreshLinked } = useRequest(
    async () => {
      if (!boundEcpWorkspace) return [] as EcpLinkedResource[];
      const [, res] = await apiInterceptors(getEcpLinkedResources(boundEcpWorkspace));
      const data = res ?? [];
      setLinkedResources(data);
      return data;
    },
    {
      ready: !!boundEcpWorkspace,
      refreshDeps: [boundEcpWorkspace],
    },
  );

  // Bind ECP resource + auto-link datasources
  const handleBind = async (workspace_id: string) => {
    const currentResourceTool = appInfo?.resource_tool || [];

    // 1. Add ECP resource
    const ecpEntry = {
      type: 'ecp',
      name: 'ecp',
      value: JSON.stringify({ workspace_id }),
    };

    let updatedTool = [...currentResourceTool, ecpEntry];

    // 2. Fetch linked datasources and auto-add them
    try {
      const [, linked] = await apiInterceptors(getEcpLinkedResources(workspace_id));
      if (linked && linked.length > 0) {
        const existingIds = new Set(
          currentResourceTool
            .filter((item: any) => item.type === 'datasource')
            .map((item: any) => {
              try {
                return JSON.parse(item.value || '{}').id;
              } catch {
                return null;
              }
            })
            .filter(Boolean),
        );

        for (const ds of linked) {
          if (!existingIds.has(ds.datasource_id)) {
            updatedTool.push({
              type: 'datasource',
              name: ds.db_name,
              value: JSON.stringify({
                db_name: ds.db_name,
                db_type: ds.db_type,
                id: ds.datasource_id,
              }),
            });
          }
        }
        setLinkedResources(linked);
        message.success(`已绑定 ECP 资源，自动关联 ${linked.length} 个数据源`);
      } else {
        message.success('已绑定 ECP 资源（无关联数据源）');
      }
    } catch {
      message.success('已绑定 ECP 资源');
    }

    await fetchUpdateApp({ ...appInfo, resource_tool: updatedTool });
  };

  // Unbind ECP resource (keep datasources, just warn)
  const handleUnbind = async () => {
    const currentResourceTool = appInfo?.resource_tool || [];
    const updatedTool = currentResourceTool.filter((item: any) => item.type !== 'ecp');
    setLinkedResources([]);
    message.info('已解绑 ECP 资源（关联的数据源保留，可手动移除）');
    await fetchUpdateApp({ ...appInfo, resource_tool: updatedTool });
  };

  // Remove a specific auto-linked datasource
  const handleRemoveDatasource = async (ds_id: number) => {
    const currentResourceTool = appInfo?.resource_tool || [];
    const updatedTool = currentResourceTool.filter((item: any) => {
      if (item.type !== 'datasource') return true;
      try {
        const parsed = JSON.parse(item.value || '{}');
        return parsed.id !== ds_id;
      } catch {
        return true;
      }
    });
    await fetchUpdateApp({ ...appInfo, resource_tool: updatedTool });
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col h-full">
      {/* ECP workspace list */}
      <div className="px-5 py-3 border-b border-gray-100/40 flex items-center justify-between">
        <span className="text-[13px] font-medium text-gray-600">ECP 语义资产工作空间</span>
        {boundEcpWorkspace && (
          <Tooltip title="刷新关联资源">
            <button
              onClick={refreshLinked}
              className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all"
            >
              <ReloadOutlined className={`text-xs ${linkedLoading ? 'animate-spin' : ''}`} />
            </button>
          </Tooltip>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-3 custom-scrollbar">
        <Spin spinning={linkedLoading}>
          {/* Workspace cards */}
          <div className="grid grid-cols-1 gap-2 mb-4">
            {(ecpWorkspaces ?? []).map((ws) => {
              const isBound = boundEcpWorkspace === ws.workspace_id;
              return (
                <div
                  key={ws.workspace_id}
                  className={`group flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                    isBound
                      ? 'border-indigo-200/80 bg-indigo-50/30 shadow-sm'
                      : 'border-gray-100/80 bg-gray-50/20 hover:border-gray-200/80 hover:bg-gray-50/40'
                  }`}
                  onClick={() => (isBound ? handleUnbind() : handleBind(ws.workspace_id))}
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isBound ? 'bg-indigo-100' : 'bg-gray-100'
                      }`}
                    >
                      <SafetyCertificateOutlined
                        className={`text-sm ${isBound ? 'text-indigo-500' : 'text-gray-400'}`}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-medium text-gray-700 truncate">
                          {ws.label}
                        </span>
                        {isBound && (
                          <Tag className="text-[10px] border-0 bg-indigo-100 text-indigo-600 rounded px-1.5 py-0 leading-5">
                            已绑定
                          </Tag>
                        )}
                      </div>
                      <div className="text-[11px] text-gray-400 truncate mt-0.5">
                        {isBound
                          ? '点击解绑（关联数据源保留）'
                          : '点击绑定，自动关联工作空间登记的数据源'}
                      </div>
                    </div>
                  </div>
                  {isBound && (
                    <CheckCircleFilled className="text-indigo-500 text-base ml-2 flex-shrink-0" />
                  )}
                </div>
              );
            })}
          </div>

          {/* Auto-linked datasources */}
          {boundEcpWorkspace && linkedResources.length > 0 && (
            <div>
              <div className="text-[12px] font-medium text-gray-500 mb-2 px-1">
                自动关联的数据源（提案基于这些数据源生成，可移除不需要的）
              </div>
              <div className="grid grid-cols-1 gap-2">
                {linkedResources.map((ds, idx) => {
                  const isBound = boundDatasourceIds.includes(ds.datasource_id);
                  return (
                    <div
                      key={`${ds.datasource_id}-${idx}`}
                      className="group flex items-center justify-between p-2.5 rounded-lg border border-gray-100/80 bg-gray-50/20 hover:bg-gray-50/40 transition-all"
                    >
                      <div className="flex items-center gap-2.5 flex-1 min-w-0">
                        <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 bg-green-50">
                          <DatabaseOutlined className="text-xs text-green-500" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[12px] font-medium text-gray-600 truncate">
                              {ds.db_name}
                            </span>
                            {ds.db_type && (
                              <Tag className="text-[10px] border-0 bg-gray-100 text-gray-500 rounded px-1 py-0 leading-4">
                                {ds.db_type}
                              </Tag>
                            )}
                            {isBound && (
                              <Tag className="text-[10px] border-0 bg-green-100 text-green-600 rounded px-1 py-0 leading-4">
                                已绑定
                              </Tag>
                            )}
                          </div>
                          <div className="text-[10px] text-gray-400 truncate mt-0.5">
                            datasource_id: {ds.datasource_id}
                          </div>
                        </div>
                      </div>
                      {isBound && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveDatasource(ds.datasource_id);
                          }}
                          className="opacity-0 group-hover:opacity-100 text-[11px] text-red-400 hover:text-red-500 transition-all px-2 py-1 rounded hover:bg-red-50 flex-shrink-0"
                        >
                          移除
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {boundEcpWorkspace && linkedResources.length === 0 && !linkedLoading && (
            <div className="text-center py-8 text-gray-300 text-xs">
              该工作空间暂无关联数据源
            </div>
          )}

          {!boundEcpWorkspace && (
            <div className="text-center py-8 text-gray-300 text-xs">
              绑定 ECP 工作空间后，将自动注入已确认语义目录 + 6 个查询工具，并关联工作空间登记的数据源
            </div>
          )}
        </Spin>
      </div>
    </div>
  );
}
