import { format, parseISO } from 'date-fns';

import type { Num } from '@/types';

export const TZ = 'Asia/Dhaka';

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const HAS_ZONE = /([zZ]|[+-]\d{2}:?\d{2})$/;

const dateFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' });
const timeFmt = new Intl.DateTimeFormat('en-US', { timeZone: TZ, hour: 'numeric', minute: '2-digit', hour12: true });
const isoDayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });

// The API sends datetimes as UTC without a zone suffix
function toInstant(value: string): Date {
  return new Date(HAS_ZONE.test(value) ? value : `${value}Z`);
}

/** 12 Oct 2026 */
export function fmtDate(value?: string | null): string {
  if (!value) return '—';
  if (DATE_ONLY.test(value)) return format(parseISO(value), 'd MMM yyyy');
  return dateFmt.format(toInstant(value));
}

/** 12 Oct 2026, 3:30 PM (Asia/Dhaka) */
export function fmtDateTime(value?: string | null): string {
  if (!value) return '—';
  const d = toInstant(value);
  return `${dateFmt.format(d)}, ${timeFmt.format(d)}`;
}

/** Today in Dhaka as YYYY-MM-DD */
export function todayIso(): string {
  return isoDayFmt.format(new Date());
}

export function monthStartIso(): string {
  return `${todayIso().slice(0, 8)}01`;
}

/** Value for a datetime-local input, in Dhaka wall time */
export function toLocalInput(value?: string | null): string {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(toInstant(value));
  const p = Object.fromEntries(parts.map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour === '24' ? '00' : p.hour}:${p.minute}`;
}

/** A datetime-local value is Dhaka wall time; send it with the Dhaka offset so the API stores the right instant. */
export function fromLocalInput(value: string): string {
  return `${value.length === 16 ? `${value}:00` : value}+06:00`;
}

export function num(value: Num | null | undefined): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/** ৳ 12,345.00 · $ 20.00 */
export function money(value: Num | null | undefined, currency = 'BDT'): string {
  if (value === null || value === undefined || value === '') return '—';
  const symbol = currency === 'BDT' ? '৳' : currency === 'USD' ? '$' : currency;
  return `${symbol} ${num(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function compactMoney(value: number, currency = 'BDT'): string {
  const symbol = currency === 'BDT' ? '৳' : currency === 'USD' ? '$' : '';
  return `${symbol}${new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)}`;
}

/** pending_manager -> Pending manager */
export function label(value?: string | null): string {
  if (!value) return '—';
  const text = value.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function durationLabel(months: number | null | undefined): string {
  if (!months) return 'Open-ended';
  return months === 1 ? '1 month' : `${months} months`;
}
