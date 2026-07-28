'use client';

import { useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

/**
 * 触发源列表已并入「任务」页的「触发规则」Tab。
 * 此路由保留以兼容旧链接,直接重定向到任务页对应 Tab。
 */
export default function TriggerListRedirect() {
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const id = searchParams?.get('id') || '';
    router.replace(`/workspaces/detail/tasks?id=${id}&tab=triggers`);
  }, [router, searchParams]);

  return null;
}
