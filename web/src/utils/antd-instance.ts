import type { MessageInstance } from 'antd/es/message/interface';

/**
 * 全局 message 实例 holder。
 *
 * antd v5 静态 `message` 在本应用 (React 19 + Next 15) 下会静默失效，
 * 而组件外代码 (axios 拦截器、请求工具函数) 无法调用 `App.useApp()` hook。
 * 因此由 `<App>` 内的 `StaticInstanceBridge` 组件挂载实例，组件外通过
 * `getMessage()` 取用。App 挂载前调用返回 undefined，静默跳过 (优于静态空转)。
 *
 * 组件内仍应直接使用 `const { message } = App.useApp()`，不要用本 holder。
 */
let messageInstance: MessageInstance | undefined;

export const setMessageInstance = (m?: MessageInstance): void => {
  messageInstance = m;
};

export const getMessage = (): MessageInstance | undefined => messageInstance;
