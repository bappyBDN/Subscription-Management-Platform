import type {
  GroupPoint,
  MonthPoint,
  Renewal,
  SeriesPoint,
  Summary,
  TeamCostDetail,
  TeamCosts,
  UsageReading,
  UsageStatus,
} from '@/types';
import { get, post } from './client';

export type View = 'accrued' | 'paid';
export type Currency = 'BDT' | 'USD';
export type Period = '30d' | 'month' | 'year';

export const dashboardApi = {
  summary: (view: View, currency: Currency) => get<Summary>('/dashboard/summary', { view, currency }),
  series: (view: View, currency: Currency, days = 30) =>
    get<SeriesPoint[]>('/dashboard/series', { days, view, currency }),
  monthly: (view: View, currency: Currency, months = 12) =>
    get<MonthPoint[]>('/dashboard/monthly', { months, view, currency }),
  byTool: (view: View, currency: Currency, period: Period) =>
    get<GroupPoint[]>('/dashboard/by-tool', { period, view, currency }),
  byDepartment: (view: View, currency: Currency, period: Period, group: 'department' | 'unit') =>
    get<GroupPoint[]>('/dashboard/by-department', { period, group, view, currency }),
  renewals: (days = 30) => get<Renewal[]>('/dashboard/renewals', { days }),
};

export const teamCostApi = {
  list: () => get<TeamCosts>('/costs/teams'),
  detail: (teamId: number, days = 30) => get<TeamCostDetail>(`/costs/teams/${teamId}`, { days }),
  usageStatus: () => get<UsageStatus>('/usage/status'),
  syncUsage: () => post<UsageReading>('/usage/sync'),
};
