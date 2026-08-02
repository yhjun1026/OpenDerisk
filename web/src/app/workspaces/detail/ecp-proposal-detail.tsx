'use client';

/** ECP 提案确认 -- 在场景空间中间内容区域展示(非抽屉)。

 * 由 SceneSpace 的 'ecp-proposal' 上下文渲染。点击左侧 rail 的 ECP 提案待办 ->
 * shell handlePreview -> detailContext='ecp-proposal' -> 本组件。
 * source_id 由后端构造为 `{ecp_ws}:{obj.id}@v{version}`,解析后定位到**该具体版本**
 * (待办指向的 proposed 版本),而非 getEcpObject 的"最新 confirmed/最新版本"--
 * 否则可能取到已确认版本,确认时报 "not in proposed"。仅在 status=proposed 时
 * 允许确认/否决;已处理则提示并刷新收件箱消除陈旧待办。
 */
import { apiInterceptors } from '@/client/api';
import {
  confirmEcpObject,
  getEcpObjectVersions,
  rejectEcpObject,
} from '@/client/api/ecp';
import { ObjectDetailContent, StatusTag, TypeChip } from '@/app/ecp/components/common';
import { getUserId } from '@/utils';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Popconfirm, Spin } from 'antd';
import { useEffect } from 'react';

import { parseEcpProposalSource } from './scene-task-rail';

export interface EcpProposalDetailProps {
  sourceId: string;
  /** 确认/否决/发现陈旧待办后回调(shell bump inboxTick -> rail 刷新待办)。 */
  onResolved: () => void;
  /** 返回大厅。 */
  onBack: () => void;
}

export function EcpProposalDetail({ sourceId, onResolved, onBack }: EcpProposalDetailProps) {
  // 用 App.useApp() 取 message,避免静态 message 无法消费 antd 上下文主题的告警
  // (根 layout 已用 <App> 包裹)。
  const { message } = App.useApp();
  const parsed = parseEcpProposalSource(sourceId);

  // 取该提案全部版本,定位到 source_id 指定的具体版本(待办指向的 proposed 版本)。
  const { data: versions, loading } = useRequest(
    async () => {
      if (!parsed) return [];
      const [err, res] = await apiInterceptors(
        getEcpObjectVersions(parsed.objId, parsed.workspaceId),
      );
      if (err) {
        message.error(err.message);
        return [];
      }
      return res ?? [];
    },
    { refreshDeps: [sourceId], ready: !!parsed },
  );
  const obj = parsed
    ? (versions || []).find((v) => v.version === parsed.version) ?? null
    : null;

  // 提案已离开 proposed(已确认/否决/废弃)-> 待办陈旧,刷新收件箱让其消除,不报错。
  useEffect(() => {
    if (obj && obj.status !== 'proposed') {
      onResolved();
    }
  }, [obj?.status]);

  const { run: settle, loading: settling } = useRequest(
    async (action: 'confirm' | 'reject') => {
      if (!obj) return;
      const userId = String(getUserId() ?? 'unknown');
      const api = action === 'confirm' ? confirmEcpObject : rejectEcpObject;
      const [err] = await apiInterceptors(
        api(obj.id, obj.version, { user_id: userId, workspace_id: obj.workspace_id }),
      );
      if (err) {
        message.error(err.message);
        return;
      }
      message.success(
        action === 'confirm' ? `已确认 ${obj.id}，该口径即刻生效` : `已否决 ${obj.id}`,
      );
      onResolved();
      onBack();
    },
    { manual: true },
  );

  if (!parsed) {
    return (
      <div className="ws-scene-space__body">
        <div className="ws-preview">
          <div className="ws-preview__head">
            <span className="ws-preview__title">提案信息无法解析</span>
          </div>
        </div>
      </div>
    );
  }
  if (loading) {
    return (
      <div className="ws-scene-space__body">
        <Spin style={{ display: 'block', margin: '64px auto' }} />
      </div>
    );
  }
  if (!obj) {
    return (
      <div className="ws-scene-space__body">
        <div className="ws-preview">
          <div className="ws-preview__head">
            <span className="ws-preview__title">提案未找到（可能已被删除）</span>
          </div>
        </div>
      </div>
    );
  }

  const header = (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
      <TypeChip type={obj.obj_type} />
      <span style={{ fontWeight: 650 }}>{obj.id}</span>
      <span style={{ color: 'var(--ink-400)', fontSize: 12 }}>v{obj.version}</span>
    </div>
  );

  if (obj.status !== 'proposed') {
    return (
      <div className="ws-scene-space__body">
        {header}
        <div className="ws-preview">
          <div className="ws-preview__head">
            <span className="ws-preview__title">该提案已处理</span>
          </div>
          <div style={{ marginTop: 8 }}>
            当前状态：<StatusTag status={obj.status} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ws-scene-space__body">
      {header}
      <ObjectDetailContent obj={obj} />
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
        <Popconfirm title="否决该提案？" onConfirm={() => settle('reject')}>
          <Button danger icon={<CloseOutlined />} loading={settling}>
            否决
          </Button>
        </Popconfirm>
        <Button
          type="primary"
          icon={<CheckOutlined />}
          loading={settling}
          onClick={() => settle('confirm')}
        >
          确认生效
        </Button>
      </div>
    </div>
  );
}
