import type { ReportOut } from '@/types';
import { api, get } from './client';

export const reportsApi = {
  run: (kind: string, from: string, to: string) => get<ReportOut>(`/reports/${kind}`, { from, to }),
  async download(kind: string, from: string, to: string) {
    const res = await api.get<Blob>(`/reports/${kind}`, { params: { from, to, format: 'xlsx' }, responseType: 'blob' });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `smp-${kind}-${from}-${to}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
