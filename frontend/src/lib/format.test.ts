import { describe, expect, it } from 'vitest';

import { durationLabel, fmtDate, fmtDateTime, fromLocalInput, label, money, toLocalInput } from './format';

describe('money', () => {
  it('formats BDT and USD as in the UI rules', () => {
    expect(money(12345, 'BDT')).toBe('৳ 12,345.00');
    expect(money('20', 'USD')).toBe('$ 20.00');
  });
  it('shows a dash for missing values', () => {
    expect(money(null)).toBe('—');
  });
});

describe('dates', () => {
  it('formats a plain date', () => {
    expect(fmtDate('2026-10-12')).toBe('12 Oct 2026');
  });
  it('treats API datetimes as UTC and shows them in Dhaka time', () => {
    expect(fmtDateTime('2026-10-12T09:30:00')).toBe('12 Oct 2026, 3:30 PM');
    expect(fmtDate('2026-10-12T20:00:00')).toBe('13 Oct 2026');
  });
  it('round-trips a datetime-local value through Dhaka time', () => {
    expect(toLocalInput('2026-10-12T09:30:00')).toBe('2026-10-12T15:30');
    expect(fromLocalInput('2026-10-12T15:30')).toBe('2026-10-12T15:30:00+06:00');
  });
});

describe('labels', () => {
  it('humanises enum values', () => {
    expect(label('pending_manager')).toBe('Pending manager');
    expect(durationLabel(null)).toBe('Open-ended');
    expect(durationLabel(3)).toBe('3 months');
  });
});
