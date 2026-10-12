import type { AuditRow, Notifications } from '@/types';
import { get, post } from './client';

export const notificationsApi = {
  list: () => get<Notifications>('/notifications', { limit: 30 }),
  markRead: (id: number) => post<void>(`/notifications/${id}/read`),
  markAllRead: () => post<void>('/notifications/read-all'),
};

export const auditApi = {
  list: (filters: Record<string, unknown> = {}) => get<AuditRow[]>('/audit-logs', filters),
};
