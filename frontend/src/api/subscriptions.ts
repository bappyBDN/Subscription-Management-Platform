import type {
  Assignment,
  Charge,
  ImportResult,
  MySubscriptions,
  SharedSeat,
  Subscription,
  SubscriptionDetail,
} from '@/types';
import { del, get, patch, post, upload } from './client';

export const subscriptionsApi = {
  list: (filters: Record<string, unknown> = {}) => get<Subscription[]>('/subscriptions', filters),
  get: (id: number) => get<SubscriptionDetail>(`/subscriptions/${id}`),
  create: (body: Record<string, unknown>) => post<Subscription>('/subscriptions', body),
  update: (id: number, body: Record<string, unknown>) => patch<Subscription>(`/subscriptions/${id}`, body),
  cancel: (id: number, body: Record<string, unknown>) => post<Subscription>(`/subscriptions/${id}/cancel`, body),
  assign: (id: number, body: Record<string, unknown>) => post<Assignment>(`/subscriptions/${id}/assignments`, body),
  revoke: (id: number, assignmentId: number) => del<Assignment>(`/subscriptions/${id}/assignments/${assignmentId}`),
  sharedSeats: (vendor_id: number) => get<SharedSeat[]>('/subscriptions/shared-seats', { vendor_id }),
  importFile: (file: File) => upload<ImportResult>('/subscriptions/import', file),
  mine: () => get<MySubscriptions>('/my/subscriptions'),
};

export const chargesApi = {
  list: (filters: Record<string, unknown> = {}) => get<Charge[]>('/charges', filters),
  create: (body: Record<string, unknown>) => post<Charge>('/charges', body),
  update: (id: number, body: Record<string, unknown>) => patch<Charge>(`/charges/${id}`, body),
  remove: (id: number) => del<void>(`/charges/${id}`),
};
