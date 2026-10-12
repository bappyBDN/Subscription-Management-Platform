import type { CardRow, Employee, ImportResult, Plan, SettingsValues, UserRow, Vendor } from '@/types';
import { api, clean, del, get, patch, post, put, upload } from './client';

export const employeesApi = {
  // The backend shows active employees unless status is sent empty, so "all" sends "status=" explicitly.
  async list(filters: { q?: string; status?: string; unit?: string } = {}) {
    const { status = 'active', ...rest } = filters;
    const params = { ...clean(rest), status: status === 'all' ? '' : status };
    return (await api.get<Employee[]>('/employees', { params })).data;
  },
  directory: (q: string) => get<Employee[]>('/employees/directory', { q }),
  create: (body: Record<string, unknown>) => post<Employee>('/employees', body),
  update: (id: number, body: Record<string, unknown>) => patch<Employee>(`/employees/${id}`, body),
  importFile: (file: File) => upload<ImportResult>('/employees/import', file),
};

export const usersApi = {
  list: () => get<UserRow[]>('/users'),
  create: (body: Record<string, unknown>) => post<UserRow>('/users', body),
  update: (id: number, body: Record<string, unknown>) => patch<UserRow>(`/users/${id}`, body),
};

export const vendorsApi = {
  list: (include_inactive = false) => get<Vendor[]>('/vendors', { include_inactive }),
  create: (body: Record<string, unknown>) => post<Vendor>('/vendors', body),
  update: (id: number, body: Record<string, unknown>) => patch<Vendor>(`/vendors/${id}`, body),
  addPlan: (id: number, body: Record<string, unknown>) => post<Plan>(`/vendors/${id}/plans`, body),
  deletePlan: (id: number, planId: number) => del<void>(`/vendors/${id}/plans/${planId}`),
};

export const cardsApi = {
  list: () => get<CardRow[]>('/cards'),
  create: (body: Record<string, unknown>) => post<CardRow>('/cards', body),
  update: (id: number, body: Record<string, unknown>) => patch<CardRow>(`/cards/${id}`, body),
};

export const settingsApi = {
  get: () => get<SettingsValues>('/settings'),
  save: (body: Record<string, unknown>) => put<SettingsValues>('/settings', body),
};
