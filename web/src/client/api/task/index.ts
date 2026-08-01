import { POST, GET } from '..';

export const createTask = (data: any) => POST('/api/v1/serve_task_service/tasks/create', data);
export const listTasks = (data: any) => POST('/api/v1/serve_task_service/tasks/list', data);
export const getTaskInfo = (task_id: number) => GET(`/api/v1/serve_task_service/tasks/info?task_id=${task_id}`);
export const updateTask = (data: any) => POST('/api/v1/serve_task_service/tasks/update', data);
export const startTask = (task_id: number) => POST(`/api/v1/serve_task_service/tasks/${task_id}/start`, {});
export const terminateTask = (task_id: number) => POST(`/api/v1/serve_task_service/tasks/${task_id}/terminate`, {});
export const deleteTask = (task_id: number) => POST(`/api/v1/serve_task_service/tasks/${task_id}/delete`, {});
export const closeTask = (data: any) => POST('/api/v1/serve_task_service/tasks/close', data);
export const archiveTask = (task_id: number) => POST(`/api/v1/serve_task_service/tasks/${task_id}/archive`, {});
export const spawnTask = (data: any) => POST('/api/v1/serve_task_service/tasks/spawn', data);
export const reassignTask = (task_id: number, assignee_user_id: number) =>
  POST(`/api/v1/serve_task_service/tasks/${task_id}/reassign`, { assignee_user_id });
