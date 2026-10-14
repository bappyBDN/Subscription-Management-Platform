import type { CardRow, Department, Employee, ImportResult, OrgFunction, Plan, SettingsValues, Team, Unit, UserRow, Vendor } from '@/types';
import { api, clean, del, get, patch, post, put, upload } from './client';

export const employeesApi = {
  // The backend shows active employees unless status is sent empty, so "all" sends "status=" explicitly.
  async list(filters: { q?: string; status?: string; unit_id?: string } = {}) {
    const { status = 'active', ...rest } = filters;
    const params = { ...clean(rest), status: status === 'all' ? '' : status };
    return (await api.get<Employee[]>('/employees', { params })).data;
  },
  directory: (q: string) => get<Employee[]>('/employees/directory', { q }),
  create: (body: Record<string, unknown>) => post<Employee>('/employees', body),
  update: (id: number, body: Record<string, unknown>) => patch<Employee>(`/employees/${id}`, body),
  remove: (id: number) => del<void>(`/employees/${id}`),
  importFile: (file: File) => upload<ImportResult>('/employees/import', file),
};

export const unitsApi = {
  list: (include_inactive = false) => get<Unit[]>('/units', { include_inactive }),
  create: (body: Record<string, unknown>) => post<Unit>('/units', body),
  update: (id: number, body: Record<string, unknown>) => patch<Unit>(`/units/${id}`, body),
  createDepartment: (body: Record<string, unknown>) => post<Department>('/departments', body),
  updateDepartment: (id: number, body: Record<string, unknown>) => patch<Department>(`/departments/${id}`, body),
  remove: (id: number) => del<void>(`/units/${id}`),
  removeDepartment: (id: number) => del<void>(`/departments/${id}`),
};

export const functionsApi = {
  list: (filters: { unit_id?: number; department_id?: number; include_inactive?: boolean } = {}) =>
    get<OrgFunction[]>('/functions', filters),
  create: (body: Record<string, unknown>) => post<OrgFunction>('/functions', body),
  update: (id: number, body: Record<string, unknown>) => patch<OrgFunction>(`/functions/${id}`, body),
  remove: (id: number) => del<void>(`/functions/${id}`),
};

export const teamsApi = {
  list: (include_inactive = false) => get<Team[]>('/teams', { include_inactive }),
  create: (body: Record<string, unknown>) => post<Team>('/teams', body),
  update: (id: number, body: Record<string, unknown>) => patch<Team>(`/teams/${id}`, body),
  remove: (id: number) => del<void>(`/teams/${id}`),
};

export const usersApi = {
  list: () => get<UserRow[]>('/users'),
  create: (body: Record<string, unknown>) => post<UserRow>('/users', body),
  update: (id: number, body: Record<string, unknown>) => patch<UserRow>(`/users/${id}`, body),
  remove: (id: number) => del<void>(`/users/${id}`),
};

export const vendorsApi = {
  list: (include_inactive = false) => get<Vendor[]>('/vendors', { include_inactive }),
  create: (body: Record<string, unknown>) => post<Vendor>('/vendors', body),
  update: (id: number, body: Record<string, unknown>) => patch<Vendor>(`/vendors/${id}`, body),
  remove: (id: number) => del<void>(`/vendors/${id}`),
  addPlan: (id: number, body: Record<string, unknown>) => post<Plan>(`/vendors/${id}/plans`, body),
  deletePlan: (id: number, planId: number) => del<void>(`/vendors/${id}/plans/${planId}`),
};

export const cardsApi = {
  list: () => get<CardRow[]>('/cards'),
  create: (body: Record<string, unknown>) => post<CardRow>('/cards', body),
  update: (id: number, body: Record<string, unknown>) => patch<CardRow>(`/cards/${id}`, body),
  remove: (id: number) => del<void>(`/cards/${id}`),
};

export const settingsApi = {
  get: () => get<SettingsValues>('/settings'),
  save: (body: Record<string, unknown>) => put<SettingsValues>('/settings', body),
};
