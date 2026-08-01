'use client';

import { RouteRedirect } from '../route-redirect';

/** 介入中心已降级为收件箱(工作台左栏「待办」)的来源视图。 */
export default function InterventionsRedirect() {
  return <RouteRedirect buildTarget={(code) => `/workspaces/detail?id=${code}`} />;
}
