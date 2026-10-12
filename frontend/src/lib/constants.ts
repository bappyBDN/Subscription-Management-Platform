export type Tone = 'amber' | 'grey' | 'blue' | 'red' | 'indigo' | 'green' | 'slate';

// Status badge colours (FRONTEND.md §5)
export const STATUS_TONE: Record<string, Tone> = {
  pending_manager: 'amber',
  pending_dmd: 'amber',
  pending_payment: 'amber',
  revoke_pending: 'amber',
  on_hold: 'grey',
  paused: 'grey',
  info_needed: 'blue',
  rejected: 'red',
  withdrawn: 'red',
  cancelled: 'red',
  revoked: 'red',
  approved: 'indigo',
  handover_pending: 'indigo',
  active: 'green',
  ended: 'slate',
  expired: 'slate',
  inactive: 'slate',
};

export const STATUS_LABEL: Record<string, string> = {
  pending_manager: 'Pending manager',
  pending_dmd: 'Pending DMD Sir',
  on_hold: 'On hold',
  info_needed: 'Info needed',
  handover_pending: 'Handover pending',
  pending_payment: 'Pending payment',
  revoke_pending: 'Under review',
};

export const REQUEST_STATUSES = [
  'pending_manager', 'pending_dmd', 'on_hold', 'info_needed', 'rejected', 'withdrawn', 'approved',
  'handover_pending', 'active', 'ended',
];
export const OPEN_REQUEST_STATUSES = [
  'pending_manager', 'pending_dmd', 'on_hold', 'info_needed', 'approved', 'handover_pending',
];
export const REQUEST_TYPES = ['new', 'renewal', 'upgrade', 'cancel'];
export const SUBSCRIPTION_STATUSES = ['active', 'pending_payment', 'paused', 'cancelled', 'expired'];
export const SUBSCRIPTION_TYPES = ['individual', 'team', 'api_credit', 'one_time'];
export const BILLING_CYCLES = ['monthly', 'yearly', 'usage', 'one_time'];
export const VENDOR_CATEGORIES = ['ai', 'design', 'productivity', 'dev', 'other'];
export const UNITS = ['BMD', 'AES'];
export const CURRENCIES = ['USD', 'BDT', 'EUR', 'GBP'];
export const ROLES = ['dmd', 'delegate', 'employee'];
export const DURATIONS: { value: string; label: string }[] = [
  { value: '1', label: '1 month' },
  { value: '3', label: '3 months' },
  { value: '6', label: '6 months' },
  { value: '12', label: '12 months' },
  { value: 'open', label: 'Open-ended' },
];

export const METHOD_LABEL: Record<string, string> = {
  vault: 'Secure vault',
  appointment: 'Come to DMD Sir',
  colleague: 'Via colleague',
};

export const DECISION_LABEL: Record<string, string> = {
  recommend: 'Recommended',
  approve: 'Approved',
  reject: 'Rejected',
  hold: 'Put on hold',
  info: 'Asked for information',
  resume: 'Resumed',
  override: 'Approved (urgent override)',
  resubmit: 'Resubmitted',
  withdraw: 'Withdrawn',
  set_handover: 'Handover set up',
  receive: 'Access received',
  end: 'Ended',
};

export const DEFAULT_SLA_DAYS = 2;
