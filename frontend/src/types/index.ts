// API types mirrored from the backend schemas. Decimal values arrive as strings or numbers.
export type Num = number | string;

export type RoleName = 'dmd' | 'delegate' | 'employee';

export interface ManagerBrief {
  id: number;
  emp_code: string;
  name: string;
  designation: string | null;
}

export interface Me {
  user_id: number;
  employee_id: number;
  emp_code: string;
  name: string;
  designation: string | null;
  unit_id: number;
  unit: string;
  department_id: number | null;
  department: string | null;
  function_id: number | null;
  team: string | null;
  email: string | null;
  phone: string | null;
  roles: string[];
  is_manager: boolean;
  heads_unit_ids: number[];
  heads_department_ids: number[];
  heads_function_ids: number[];
  leads_team_ids: number[];
  can_propose: boolean;
  can_reveal_vault: boolean;
  manager: ManagerBrief | null;
  last_login_at: string | null;
}

export interface LoginOut {
  access_token: string | null;
  token_type: string;
  otp_required: boolean;
  otp_token: string | null;
}

export interface Plan {
  id: number;
  plan_name: string;
  default_cost: Num;
  currency: string;
  billing_cycle: string;
}

export interface Vendor {
  id: number;
  name: string;
  category: string;
  website: string | null;
  active: boolean;
  plans: Plan[];
}

export interface Employee {
  id: number;
  emp_code: string;
  name: string;
  designation: string | null;
  unit_id: number;
  unit_code: string;
  department_id: number | null;
  department_name: string | null;
  function_id: number | null;
  function_name: string | null;
  team: string | null;
  manager_id: number | null;
  email: string | null;
  phone: string | null;
  status: string;
}

export interface UserRow {
  id: number;
  employee_id: number;
  roles: string[];
  can_reveal_vault: boolean;
  is_active: boolean;
}

export interface CardRow {
  id: number;
  label: string;
  holder_name: string;
  last4: string;
  active: boolean;
}

export type OwnerScope = 'unit' | 'department' | 'function' | 'shared';

/** One department (function_id null) or function that shares a subscription */
export interface SubscriptionShare {
  department_id: number;
  department_name: string | null;
  function_id: number | null;
  function_name: string | null;
  unit_code: string | null;
}

export interface Subscription {
  id: number;
  vendor_id: number;
  vendor_name: string;
  plan_name: string;
  type: string;
  seats_total: number;
  seats_used: number;
  seats_unnamed: number;
  cost_per_cycle: Num;
  currency: string;
  billing_cycle: string;
  start_date: string;
  next_renewal_date: string | null;
  card_id: number | null;
  card_last4: string | null;
  account_email: string | null;
  owner_scope: OwnerScope;
  unit_id: number;
  unit_code: string;
  department_id: number | null;
  department_name: string | null;
  function_id: number | null;
  function_name: string | null;
  shares: SubscriptionShare[];
  team_id: number | null;
  team_name: string | null;
  usage_provider: string | null;
  owner_label: string;
  status: string;
  cancelled_on: string | null;
  notes: string | null;
}

export interface Assignment {
  id: number;
  subscription_id: number;
  employee_id: number;
  employee_name: string | null;
  emp_code: string | null;
  request_id: number | null;
  start_date: string;
  end_date: string | null;
  status: string;
}

export interface SubscriptionDetail extends Subscription {
  assignments: Assignment[];
}

/** A subscription the employee may request a seat on (owned by their unit or department) */
export interface AvailableSubscription {
  subscription_id: number;
  vendor_id: number;
  vendor_name: string;
  plan_name: string;
  owner_scope: string;
  owner_label: string;
  seats_total: number;
  seats_free: number;
  billing_cycle: string;
  cost_per_seat: Num;
  currency: string;
  monthly_bdt_per_seat: Num;
  already_holding: boolean;
}

export interface Department {
  id: number;
  unit_id: number;
  name: string;
  code: string | null;
  head_employee_id: number | null;
  monthly_budget_bdt: Num;
  cost_center: string | null;
  active: boolean;
  functions?: OrgFunction[];
}

export interface OrgFunction {
  id: number;
  department_id: number;
  department_name: string | null;
  unit_id: number;
  unit_code: string;
  name: string;
  head_employee_id: number | null;
  head_name: string | null;
  monthly_budget_bdt: Num;
  active: boolean;
  members: number;
}

export interface Team {
  id: number;
  unit_id: number;
  unit_code: string;
  name: string;
  department_id: number | null;
  department_name: string | null;
  function_id: number | null;
  function_name: string | null;
  lead_employee_id: number | null;
  lead_name: string | null;
  active: boolean;
  members: number;
}

export interface TeamCost {
  team_id: number;
  name: string;
  unit_id: number;
  unit_code: string;
  department_id: number | null;
  department_name: string | null;
  lead_employee_id: number | null;
  lead_name: string | null;
  members: number;
  amount_bdt: Num;
  amount_usd: Num;
  estimated: boolean;
  today_bdt: Num;
  month_to_date_bdt: Num;
  subscriptions: {
    subscription_id: number;
    name: string;
    metered: boolean;
    status: string;
    seats_total: number;
    seats_used: number;
    seats_free: number;
    amount_bdt: Num;
  }[];
}

export interface TeamCosts {
  from: string;
  to: string;
  rows: TeamCost[];
  total_bdt: Num;
}

export interface TeamCostDetail extends TeamCost {
  from: string;
  to: string;
  series: SeriesPoint[];
  member_list: { employee_id: number; emp_code: string; name: string; designation: string | null }[];
}

export interface UsageReading {
  usage_date: string;
  amount_original: Num;
  currency: string;
  fx_rate: Num;
  amount_bdt: Num;
  balance: Num;
  topped_up: Num;
  synced_at: string;
}

export interface UsageStatus {
  provider: string;
  key_configured: boolean;
  subscription_id: number | null;
  subscription_name: string | null;
  team_name: string | null;
  last: UsageReading | null;
}

export interface Unit {
  id: number;
  code: string;
  name: string;
  head_employee_id: number | null;
  monthly_budget_bdt: Num;
  active: boolean;
  departments: Department[];
}

export interface Charge {
  id: number;
  subscription_id: number;
  card_id: number | null;
  charge_date: string;
  amount_original: Num;
  currency: string;
  fx_rate: Num;
  bank_fee_bdt: Num;
  amount_bdt: Num;
  reference: string | null;
  is_expected: boolean;
  reconciled: boolean;
  unit_id: number | null;
  department_id: number | null;
  anomaly: boolean;
  anomaly_note: string | null;
}

export interface ImportResult {
  created: number;
  errors: { row: number; error: string }[];
}

export interface Handover {
  id: number;
  method: 'vault' | 'appointment' | 'colleague';
  has_secret: boolean;
  login_email: string | null;
  login_url: string | null;
  notes: string | null;
  proposed_at: string | null;
  confirmed_at: string | null;
  location: string | null;
  collector_id: number | null;
  collector_name: string | null;
  collector_note: string | null;
  due_date: string | null;
  handed_over_at: string | null;
  received_at: string | null;
}

export interface Snapshot {
  name?: string;
  emp_code?: string;
  designation?: string | null;
  unit_id?: number | null;
  unit?: string | null;
  department_id?: number | null;
  department?: string | null;
  function_id?: number | null;
  function?: string | null;
  team?: string | null;
  email?: string | null;
  phone?: string | null;
  manager_name?: string | null;
  manager_code?: string | null;
}

export interface RequestRow {
  id: number;
  req_no: string;
  employee_id: number;
  snapshot: Snapshot;
  type: string;
  vendor_id: number | null;
  tool_name: string;
  other_tool_url: string | null;
  plan_name: string;
  seats: number;
  duration_months: number | null;
  needed_from: string;
  reason: string;
  expected_use: string | null;
  est_cost_bdt: Num | null;
  est_cost_original: Num | null;
  est_currency: string | null;
  est_billing_cycle: string | null;
  owner_scope: string | null;
  unit_id: number | null;
  department_id: number | null;
  status: string;
  subscription_id: number | null;
  submitted_at: string;
  status_changed_at: string;
  waiting_days: number;
}

export interface Approval {
  id: number;
  step: string;
  approver_id: number;
  approver_name: string | null;
  decision: string;
  comment: string | null;
  from_status: string;
  to_status: string;
  created_at: string;
}

export interface RequestDetail extends RequestRow {
  approvals: Approval[];
  handover: Handover | null;
  allowed_actions: string[];
}

export interface Estimate {
  currency: string;
  monthly_original: Num;
  yearly_original: Num;
  monthly_bdt: Num;
  yearly_bdt: Num;
  fx_rate: Num;
  billing_cycle: string | null;
  source: 'catalogue' | 'provided' | 'subscription' | 'unknown';
}

export interface RequesterTool {
  subscription_id: number;
  vendor_name: string;
  plan_name: string;
  status: string;
  end_date: string | null;
}

export interface Reveal {
  secret: string;
  login_email: string | null;
  login_url: string | null;
  notes: string | null;
  visible_seconds: number;
}

export interface MySubscription {
  assignment_id: number;
  subscription_id: number;
  vendor_name: string;
  plan_name: string;
  status: string;
  start_date: string;
  end_date: string | null;
  next_renewal_date: string | null;
  request_id: number | null;
  req_no: string | null;
  handover: Handover | null;
}

export interface PendingHandover {
  request_id: number;
  req_no: string;
  tool_name: string;
  plan_name: string;
  status: string;
  handover: Handover | null;
}

export interface MySubscriptions {
  active: MySubscription[];
  pending_handover: PendingHandover[];
}

export interface HandoverTask {
  handover_id: number;
  request_id: number;
  req_no: string;
  requester_name: string;
  requester_code: string;
  tool_name: string;
  plan_name: string;
  note: string | null;
  due_date: string | null;
  handed_over_at: string | null;
}

export interface Total {
  amount: Num;
  estimated: boolean;
}

export interface Summary {
  view: string;
  currency: 'BDT' | 'USD';
  today: Total;
  week: Total;
  month: Total;
  year: Total;
  projected_month: Num;
  run_rate_year: Num;
  monthly_budget: Num | null;
  budget_used_pct: number | null;
  counts: Record<string, number | string>;
}

export interface SeriesPoint {
  date: string;
  amount: Num;
}

export interface MonthPoint {
  month: string;
  amount: Num;
}

export interface GroupPoint {
  name: string;
  amount: Num;
}

export interface Renewal {
  subscription_id: number;
  vendor_name: string;
  plan_name: string;
  next_renewal_date: string;
  overdue: boolean;
  amount: Num;
  currency: string;
  holders: string[];
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface Notifications {
  unread: number;
  items: NotificationItem[];
}

export interface AuditRow {
  id: number;
  user_id: number | null;
  action: string;
  entity: string | null;
  entity_id: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

export interface ReportOut {
  report: string;
  from: string;
  to: string;
  rows: Record<string, unknown>[];
}

export type SettingsValues = Record<string, string>;
