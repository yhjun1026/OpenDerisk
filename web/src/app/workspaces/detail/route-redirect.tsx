'use client';

import { Spin } from 'antd';
import { useSearchParams, useRouter } from 'next/navigation';
import { useEffect } from 'react';

/** 旧路由重定向:页面已并入新的信息架构,保留路由是为了兼容存量链接。 */
export function RouteRedirect({ buildTarget }: { buildTarget: (workspaceCode: string) => string }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const workspaceCode = searchParams?.get('id') || '';

  useEffect(() => {
    router.replace(buildTarget(workspaceCode));
  }, [workspaceCode, router, buildTarget]);

  return (
    <div className="flex justify-center py-20">
      <Spin size="large" />
    </div>
  );
}
