'use client';

import { RouteRedirect } from '../route-redirect';

/** 资源页已并入 资产 → 数据资产 tab。 */
export default function ResourcesRedirect() {
  return <RouteRedirect buildTarget={(code) => `/workspaces/detail/assets?id=${code}&tab=data`} />;
}
