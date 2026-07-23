'use client';

import { useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

/**
 * 触发器创建入口已统一到「新建任务」页(剧本+指令+触发方式)。
 * 此路由保留以兼容旧链接,直接重定向到统一创建页。
 */
export default function TriggerCreateRedirect() {
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const id = searchParams?.get('id') || '';
    const triggerId = searchParams?.get('trigger_id');
    const type = searchParams?.get('type') || 'timer';
    const qs = triggerId
      ? `id=${id}&trigger_id=${triggerId}&type=${type}`
      : `id=${id}&type=${type}`;
    router.replace(`/workspaces/detail/tasks/create?${qs}`);
  }, [router, searchParams]);

  return null;
}
