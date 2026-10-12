import axios, { AxiosError } from 'axios';

const KEY = 'smp_token';

// Access token: memory + sessionStorage (never localStorage)
let token: string | null = sessionStorage.getItem(KEY);
let onUnauthorized: (() => void) | null = null;

export const tokenStore = {
  get: () => token,
  set(value: string) {
    token = value;
    sessionStorage.setItem(KEY, value);
  },
  clear() {
    token = null;
    sessionStorage.removeItem(KEY);
  },
};

export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api' });

api.interceptors.request.use((config) => {
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// A 401 on these means "wrong password / wrong code", not "session expired"
const NO_LOGOUT = ['/auth/login', '/auth/verify-otp', '/reveal'];

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const url = error.config?.url ?? '';
    if (error.response?.status === 401 && !NO_LOGOUT.some((p) => url.includes(p))) onUnauthorized?.();
    return Promise.reject(error);
  },
);

export function errorStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined;
}

export function errorMessage(err: unknown, fallback = 'Something went wrong — please try again'): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string }) => String(d.msg ?? '').replace(/^Value error, /, ''))
        .filter(Boolean)
        .join('; ');
    }
    if (!err.response) return 'Cannot reach the server — check your connection';
  }
  return fallback;
}

// Drop empty filter values so they are not sent as "?status="
export function clean<T extends Record<string, unknown>>(params: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) if (v !== '' && v !== undefined && v !== null) out[k] = v;
  return out as Partial<T>;
}

export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  return (await api.get<T>(url, { params: params ? clean(params) : undefined })).data;
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  return (await api.post<T>(url, body)).data;
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  return (await api.patch<T>(url, body)).data;
}

export async function put<T>(url: string, body?: unknown): Promise<T> {
  return (await api.put<T>(url, body)).data;
}

export async function del<T>(url: string): Promise<T> {
  return (await api.delete<T>(url)).data;
}

export async function upload<T>(url: string, file: File): Promise<T> {
  const form = new FormData();
  form.append('file', file);
  return (await api.post<T>(url, form)).data;
}
