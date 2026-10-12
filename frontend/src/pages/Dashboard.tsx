import { useQuery } from '@tanstack/react-query';
import { format, parseISO } from 'date-fns';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { dashboardApi, type Currency, type Period, type View } from '@/api/dashboard';
import { requestsApi } from '@/api/requests';
import { useAuth, useMe } from '@/auth/AuthProvider';
import { CostCard, EmptyState, ErrorState, LoadingRows, MoneyText, QueryState, StatCard, StatusBadge } from '@/components/shared';
import { Badge, Button, Card, PageHeader, Select, cn } from '@/components/ui';
import { useMySubscriptions } from '@/hooks';
import { METHOD_LABEL, OPEN_REQUEST_STATUSES } from '@/lib/constants';
import { compactMoney, fmtDate, money, num } from '@/lib/format';

function Toggle<T extends string>({ value, options, onChange, label }: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-slate-300 bg-white p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={value === o.id}
          onClick={() => onChange(o.id)}
          className={cn('rounded px-2.5 py-1 text-xs font-medium', value === o.id ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100')}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ChartCard({ title, query, actions, height = 260, children }: {
  title: string;
  query: { isLoading: boolean; error: unknown; data: unknown[] | undefined; refetch: () => unknown };
  actions?: ReactNode;
  height?: number;
  children: ReactNode;
}) {
  return (
    <Card title={title} actions={actions}>
      {query.isLoading ? (
        <LoadingRows rows={5} />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !query.data?.length || query.data.every((d) => num((d as { amount: number }).amount) === 0) ? (
        <EmptyState title="No spend in this period" />
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            {children as React.ReactElement}
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

const PERIODS: { id: Period; label: string }[] = [
  { id: 'month', label: 'This month' },
  { id: '30d', label: 'Last 30 days' },
  { id: 'year', label: 'This year' },
];

function CostCards({ view, currency }: { view: View; currency: Currency }) {
  const q = useQuery({ queryKey: ['dashboard', 'summary', view, currency], queryFn: () => dashboardApi.summary(view, currency) });
  const s = q.data;
  if (q.error) return <Card><ErrorState error={q.error} onRetry={() => q.refetch()} /></Card>;
  const pct = s?.budget_used_pct ?? null;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <CostCard title="Today" amount={s?.today.amount} estimated={s?.today.estimated} currency={currency} loading={q.isLoading} />
      <CostCard title="This week" amount={s?.week.amount} estimated={s?.week.estimated} currency={currency} loading={q.isLoading} />
      <CostCard title="This month" amount={s?.month.amount} estimated={s?.month.estimated} currency={currency} loading={q.isLoading}>
        {s && pct !== null ? (
          <>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
              <div className={cn('h-full', pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-emerald-500')} style={{ width: `${Math.min(pct, 100)}%` }} />
            </div>
            <p className="mt-1">
              {pct.toFixed(0)}% of {money(s.monthly_budget, currency)} budget · projected {money(s.projected_month, currency)}
            </p>
          </>
        ) : s ? (
          <p>Projected {money(s.projected_month, currency)} · no budget set</p>
        ) : null}
      </CostCard>
      <CostCard title="This year" amount={s?.year.amount} estimated={s?.year.estimated} currency={currency} loading={q.isLoading}>
        {s && <p>Run-rate {money(s.run_rate_year, currency)} / year</p>}
      </CostCard>
    </div>
  );
}

function SpendCharts({ view, currency }: { view: View; currency: Currency }) {
  const series = useQuery({ queryKey: ['dashboard', 'series', view, currency], queryFn: () => dashboardApi.series(view, currency) });
  const monthly = useQuery({ queryKey: ['dashboard', 'monthly', view, currency], queryFn: () => dashboardApi.monthly(view, currency) });
  const tick = (v: number) => compactMoney(v, currency);
  const tip = (v: number | string) => money(v, currency);
  return (
    <>
      <ChartCard title="Daily spend · last 30 days" query={series}>
        <LineChart data={series.data?.map((d) => ({ ...d, amount: num(d.amount) }))} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="date" tickFormatter={(d: string) => format(parseISO(d), 'd MMM')} fontSize={11} minTickGap={24} />
          <YAxis tickFormatter={tick} fontSize={11} width={52} />
          <Tooltip formatter={tip} labelFormatter={(d: string) => fmtDate(d)} />
          <Line type="monotone" dataKey="amount" name="Spend" stroke="#4f46e5" strokeWidth={2} dot={false} />
        </LineChart>
      </ChartCard>
      <ChartCard title="Monthly spend · last 12 months" query={monthly}>
        <BarChart data={monthly.data?.map((d) => ({ ...d, amount: num(d.amount) }))} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="month" tickFormatter={(m: string) => format(parseISO(`${m}-01`), 'MMM yy')} fontSize={11} />
          <YAxis tickFormatter={tick} fontSize={11} width={52} />
          <Tooltip formatter={tip} labelFormatter={(m: string) => format(parseISO(`${m}-01`), 'MMMM yyyy')} />
          <Bar dataKey="amount" name="Spend" fill="#6366f1" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ChartCard>
    </>
  );
}

function AdminDashboard({ view, currency }: { view: View; currency: Currency }) {
  const [period, setPeriod] = useState<Period>('month');
  const [group, setGroup] = useState<'department' | 'unit'>('department');
  const summary = useQuery({ queryKey: ['dashboard', 'summary', view, currency], queryFn: () => dashboardApi.summary(view, currency) });
  const byTool = useQuery({ queryKey: ['dashboard', 'by-tool', view, currency, period], queryFn: () => dashboardApi.byTool(view, currency, period) });
  const byDept = useQuery({
    queryKey: ['dashboard', 'by-department', view, currency, period, group],
    queryFn: () => dashboardApi.byDepartment(view, currency, period, group),
  });
  const renewals = useQuery({ queryKey: ['dashboard', 'renewals'], queryFn: () => dashboardApi.renewals(30) });
  const c = summary.data?.counts ?? {};
  const loading = summary.isLoading;
  const tick = (v: number) => compactMoney(v, currency);
  const tip = (v: number | string) => money(v, currency);
  const periodSelect = (
    <Select aria-label="Period" value={period} onChange={(e) => setPeriod(e.target.value as Period)} className="!w-auto !py-1 text-xs">
      {PERIODS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
    </Select>
  );

  return (
    <div className="space-y-4">
      <CostCards view={view} currency={currency} />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard title="Active subscriptions" value={c.active_subscriptions ?? 0} loading={loading}>
          {c.seats_used ?? 0} of {c.seats_total ?? 0} seats used
          {num(c.revoke_pending) > 0 && <> · <span className="text-amber-700">{c.revoke_pending} under review</span></>}
        </StatCard>
        <StatCard title="Pending approvals" value={c.pending_approvals ?? 0} loading={loading}>
          {num(c.pending_approvals) > 0 && <>Oldest waiting {c.oldest_pending_days} day(s) · </>}
          <Link to="/approvals" className="font-medium text-indigo-600 hover:underline">Open inbox</Link>
        </StatCard>
        <StatCard title="Renewals in 7 days" value={c.renewals_7_days ?? 0} loading={loading}>
          <Link to="/subscriptions" className="font-medium text-indigo-600 hover:underline">View register</Link>
        </StatCard>
        <StatCard title="Pending handovers" value={c.pending_handovers ?? 0} loading={loading}>
          <Link to="/requests?scope=handover" className="font-medium text-indigo-600 hover:underline">Set up handovers</Link>
        </StatCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SpendCharts view={view} currency={currency} />
        <ChartCard title="Spend by tool" query={byTool} actions={periodSelect} height={Math.max(200, (byTool.data?.length ?? 0) * 34)}>
          <BarChart layout="vertical" data={byTool.data?.map((d) => ({ ...d, amount: num(d.amount) }))} margin={{ left: 8, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
            <XAxis type="number" tickFormatter={tick} fontSize={11} />
            <YAxis type="category" dataKey="name" width={96} fontSize={11} />
            <Tooltip formatter={tip} />
            <Bar dataKey="amount" name="Spend" fill="#4f46e5" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ChartCard>
        <ChartCard
          title={`Spend by ${group}`}
          query={byDept}
          actions={
            <div className="flex items-center gap-2">
              <Toggle label="Group by" value={group} onChange={setGroup} options={[{ id: 'department', label: 'Department' }, { id: 'unit', label: 'Unit' }]} />
              {periodSelect}
            </div>
          }
        >
          <BarChart data={byDept.data?.map((d) => ({ ...d, amount: num(d.amount) }))} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="name" fontSize={11} interval={0} />
            <YAxis tickFormatter={tick} fontSize={11} width={52} />
            <Tooltip formatter={tip} />
            <Bar dataKey="amount" name="Spend" fill="#0ea5e9" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartCard>
      </div>

      <Card title="Next renewals">
        <QueryState query={renewals} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No renewals in the next 30 days" />}>
          {(rows) => (
            <div className="-m-4 overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Date</th><th className="px-3 py-2">Tool</th><th className="px-3 py-2">Plan</th>
                    <th className="px-3 py-2 text-right">Amount</th><th className="px-3 py-2">Holders</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.slice(0, 10).map((r) => (
                    <tr key={r.subscription_id}>
                      <td className="whitespace-nowrap px-3 py-2">
                        {fmtDate(r.next_renewal_date)} {r.overdue && <Badge tone="red">Overdue</Badge>}
                      </td>
                      <td className="px-3 py-2">
                        <Link className="font-medium text-indigo-600 hover:underline" to={`/subscriptions/${r.subscription_id}`}>{r.vendor_name}</Link>
                      </td>
                      <td className="px-3 py-2">{r.plan_name}</td>
                      <td className="px-3 py-2 text-right"><MoneyText amount={r.amount} currency={r.currency} /></td>
                      <td className="px-3 py-2 text-slate-600">{r.holders.join(', ') || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryState>
      </Card>
    </div>
  );
}

function MyTools() {
  const q = useMySubscriptions();
  return (
    <Card title="My tools" actions={<Link className="text-xs font-medium text-indigo-600 hover:underline" to="/my/subscriptions">Open my subscriptions</Link>}>
      <QueryState
        query={q}
        isEmpty={(d) => d.active.length === 0 && d.pending_handover.length === 0}
        empty={<EmptyState title="You have no tools yet" hint="Request the tool you need and track it here." action={<Link to="/requests/new"><Button size="sm">New request</Button></Link>} />}
      >
        {(d) => (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {d.pending_handover.map((p) => (
              <li key={`p${p.request_id}`} className="rounded-md border border-indigo-200 bg-indigo-50 p-3">
                <p className="font-medium text-slate-900">{p.tool_name}</p>
                <p className="text-sm text-slate-600">{p.plan_name}</p>
                <div className="mt-2"><StatusBadge status={p.status} /></div>
              </li>
            ))}
            {d.active.map((s) => (
              <li key={s.assignment_id} className="rounded-md border border-slate-200 p-3">
                <p className="font-medium text-slate-900">{s.vendor_name}</p>
                <p className="text-sm text-slate-600">{s.plan_name}</p>
                <p className="mt-2 text-xs text-slate-500">
                  Renews {fmtDate(s.next_renewal_date)}
                  {s.handover && <> · {METHOD_LABEL[s.handover.method]}</>}
                </p>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </Card>
  );
}

function MyOpenRequests() {
  const q = useQuery({ queryKey: ['requests', 'mine', ''], queryFn: () => requestsApi.list('mine') });
  return (
    <Card title="My open requests" actions={<Link className="text-xs font-medium text-indigo-600 hover:underline" to="/requests">All my requests</Link>}>
      <QueryState
        query={{ ...q, data: q.data?.filter((r) => OPEN_REQUEST_STATUSES.includes(r.status)) }}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="No open requests" />}
      >
        {(rows) => (
          <ul className="divide-y divide-slate-100">
            {rows.map((r) => (
              <li key={r.id}>
                <Link to={`/requests/${r.id}`} className="flex flex-wrap items-center justify-between gap-2 py-2 hover:bg-slate-50">
                  <span className="min-w-0">
                    <span className="font-medium text-slate-900">{r.tool_name} {r.plan_name}</span>
                    <span className="block text-xs text-slate-500">{r.req_no} · submitted {fmtDate(r.submitted_at)}</span>
                  </span>
                  <StatusBadge status={r.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </Card>
  );
}

function ManagerDashboard({ currency }: { currency: Currency }) {
  const summary = useQuery({ queryKey: ['dashboard', 'summary', 'accrued', currency], queryFn: () => dashboardApi.summary('accrued', currency) });
  const c = summary.data?.counts ?? {};
  return (
    <div className="space-y-4">
      <CostCards view="accrued" currency={currency} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard title="Team members" value={c.team_size ?? 0} loading={summary.isLoading} />
        <StatCard title="Waiting for my approval" value={c.pending_my_approval ?? 0} loading={summary.isLoading}>
          <Link to="/approvals" className="font-medium text-indigo-600 hover:underline">Open inbox</Link>
        </StatCard>
        <StatCard title="My open requests" value={c.my_open_requests ?? 0} loading={summary.isLoading} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SpendCharts view="accrued" currency={currency} />
      </div>
      <MyTools />
      <MyOpenRequests />
    </div>
  );
}

export default function Dashboard() {
  const me = useMe();
  const { isAdmin, isManager } = useAuth();
  const [view, setView] = useState<View>('accrued');
  const [currency, setCurrency] = useState<Currency>('BDT');

  const scope = isAdmin ? 'Organisation' : isManager ? 'My team' : 'My tools';
  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={`${scope} · welcome, ${me.name}`}
        actions={
          (isAdmin || isManager) && (
            <>
              {isAdmin && (
                <Toggle label="Cost view" value={view} onChange={setView} options={[{ id: 'accrued', label: 'Accrued' }, { id: 'paid', label: 'Paid' }]} />
              )}
              <Toggle label="Currency" value={currency} onChange={setCurrency} options={[{ id: 'BDT', label: 'BDT' }, { id: 'USD', label: 'USD' }]} />
            </>
          )
        }
      />
      {isAdmin ? (
        <AdminDashboard view={view} currency={currency} />
      ) : isManager ? (
        <ManagerDashboard currency={currency} />
      ) : (
        <div className="space-y-4">
          <MyTools />
          <MyOpenRequests />
        </div>
      )}
    </>
  );
}
