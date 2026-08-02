'use client';

import { apiInterceptors } from '@/client/api';
import { getOrCreateHomeWorkspace } from '@/client/api/workspace';
import { getUserId } from '@/utils/storage';
import { useRequest } from 'ahooks';
import { Spin } from 'antd';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

/**
 * 首页 = 当前用户的默认场景空间。
 * 后端幂等 get-or-create(有 is_home 标记返回之,否则取最早创建的补标记,
 * 没有任何空间则新建"我的工作台"),前端只做薄跳转。
 * 原通用对话首页迁至 /assistant。
 */
export default function Home() {
  const router = useRouter();

  const { data, error } = useRequest(async () => {
    const [err, res] = await apiInterceptors(
      getOrCreateHomeWorkspace({ user_id: Number(getUserId()) || 0 }),
    );
    if (err) throw err;
    return res;
  });

  useEffect(() => {
    const code = (data as any)?.workspace_code;
    if (code) {
      router.replace(`/workspaces/detail?id=${encodeURIComponent(code)}`);
    }
  }, [data, router]);

  useEffect(() => {
    if (error) router.replace('/workspaces');
  }, [error, router]);

  return (
    <div className="flex justify-center items-center h-screen">
      <Spin size="large" />
    </div>
  );
}
