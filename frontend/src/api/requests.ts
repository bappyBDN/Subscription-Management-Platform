import type { Estimate, Handover, HandoverTask, RequestDetail, RequestRow, RequesterTool, Reveal } from '@/types';
import { get, patch, post } from './client';

export type Scope = 'mine' | 'team' | 'pending' | 'handover' | 'all';

export const requestsApi = {
  estimate: (body: Record<string, unknown>) => post<Estimate>('/requests/estimate', body),
  create: (body: Record<string, unknown>) => post<RequestDetail>('/requests', body),
  list: (scope: Scope, status?: string) => get<RequestRow[]>('/requests', { scope, status }),
  get: (id: number) => get<RequestDetail>(`/requests/${id}`),
  requesterTools: (id: number) => get<RequesterTool[]>(`/requests/${id}/requester-tools`),
  update: (id: number, body: Record<string, unknown>) => patch<RequestDetail>(`/requests/${id}`, body),
  resubmit: (id: number) => post<RequestDetail>(`/requests/${id}/resubmit`),
  withdraw: (id: number) => post<RequestDetail>(`/requests/${id}/withdraw`),
  decide: (id: number, body: Record<string, unknown>) => post<RequestDetail>(`/requests/${id}/decision`, body),
  bulkApprove: (request_ids: number[], comment?: string) =>
    post<{ approved: number[]; failed: { id: number; error: string }[] }>('/requests/bulk-approve', {
      request_ids,
      comment: comment || null,
    }),
  setHandover: (id: number, body: Record<string, unknown>) => post<RequestDetail>(`/requests/${id}/handover`, body),
};

export const handoverApi = {
  tasks: () => get<HandoverTask[]>('/my/handover-tasks'),
  proposeSlot: (id: number, at: string) => post<Handover>(`/handovers/${id}/propose-slot`, { at }),
  confirmSlot: (id: number, at: string, location?: string) =>
    post<Handover>(`/handovers/${id}/confirm-slot`, { at, location: location || null }),
  handedOver: (id: number) => post<Handover>(`/handovers/${id}/handed-over`),
  revealOtp: (id: number) => post<void>(`/handovers/${id}/reveal-otp`),
  reveal: (id: number, code: string) => post<Reveal>(`/handovers/${id}/reveal`, { code }),
  received: (id: number) => post<RequestDetail>(`/handovers/${id}/received`),
};
