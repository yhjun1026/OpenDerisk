'use client';

import { RouteRedirect } from '../route-redirect';

/** 交付空间已并入 资产 → 交付沉淀 tab。 */
export default function DeliveriesRedirect() {
  return <RouteRedirect buildTarget={(code) => `/workspaces/detail/assets?id=${code}&tab=delivery`} />;
}
