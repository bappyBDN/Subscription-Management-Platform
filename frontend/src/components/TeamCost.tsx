import { useQuery } from '@tanstack/react-query';
import { format, parseISO } from 'date-fns';
import { useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { teamCostApi } from '@/api/dashboard';
import { useAuth } from '@/auth/AuthProvider';
import { useAction } from '@/hooks';
import { compactMoney, fmtDate, fmtDateTime, money, num } from '@/lib/format';

import { EmptyState, ErrorState, LoadingRows, MoneyText, QueryState } from './shared';
import { Alert, Badge, Button, Card, cn } from './ui';

/** Admins only: is DeepSeek metering set up, when was the balance last read, and a button to read it now. */
function UsageSync() {
  const status = useQuery({ queryKey: ['usage', 'status'], queryFn: teamCostApi.usageStatus });
  const sync = useAction(teamCostApi.syncUsage, {
    success: (r) => `DeepSeek balance read — ${money(r.amount_original, r.currency)} used today`,
  });
  const s = status.data;
  if (!s) return null;
  const problem = !s.key_configured
    ? 'DeepSeek metering is off: set DEEPSEEK_API_KEY in backend/.env and restart the backend.'
    : !s.subscription_id
      ? 'DeepSeek metering has no subscription yet: edit the DeepSeek subscription and set "Usage metering" to DeepSeek API balance.'
      : null;
  if (problem) return <Alert tone="amber">{problem}</Alert>;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <span>
        {s.subscription_name}{s.team_name ? ` · ${s.team_name}` : ''} —{' '}
        {s.last
          ? <>balance {money(s.last.balance, s.last.currency)}, read {fmtDateTime(s.last.synced_at)}</>
          : 'balance not read yet; the first reading is the starting point, cost shows from the second'}
      </span>
      <Button size="sm" variant="secondary" loading={sync.isPending} onClick={() => sync.mutate(undefined)}>Read DeepSeek balance now</Button>
    </div>
  );
}

function TeamDaily({ teamId }: { teamId: number }) {
  const q = useQuery({ queryKey: ['costs', 'team', teamId], queryFn: () => teamCostApi.detail(teamId, 30) });
  if (q.isLoading) return <LoadingRows rows={4} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const data = d.series.map((p) => ({ ...p, amount: num(p.amount) }));
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-slate-700">
        {d.name} · daily cost, last 30 days <span className="font-normal text-slate-500">({money(d.amount_bdt)} in total)</span>
      </p>
      {data.every((p) => p.amount === 0) ? (
        <EmptyState title="No cost recorded for this team in the last 30 days" />
      ) : (
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="date" tickFormatter={(v: string) => format(parseISO(v), 'd MMM')} fontSize={11} minTickGap={24} />
              <YAxis tickFormatter={(v: number) => compactMoney(v)} fontSize={11} width={52} />
              <Tooltip formatter={(v: number | string) => money(v)} labelFormatter={(v: string) => fmtDate(v)} />
              <Bar dataKey="amount" name="Cost" fill="#0d9488" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="text-xs text-slate-500">
        Subscriptions: {d.subscriptions.map((s) => s.name).join(', ') || 'none'} · Members: {d.member_list.map((m) => m.name).join(', ') || 'none'}
      </p>
    </div>
  );
}

/** Cost per team — the whole cost of the subscriptions a team owns, never split across individuals. */
export function TeamCostCard() {
  const { isAdmin } = useAuth();
  const query = useQuery({ queryKey: ['costs', 'teams'], queryFn: teamCostApi.list });
  const [selected, setSelected] = useState<number | null>(null);
  const active = selected ?? query.data?.rows[0]?.team_id ?? null;

  return (
    <Card title="Cost by team">
      <div className="space-y-4">
        {isAdmin && <UsageSync />}
        <QueryState
          query={query}
          isEmpty={(d) => d.rows.length === 0}
          empty={<EmptyState title="No teams yet" hint="Add a team under SBUs & departments, then set it on the subscription it owns." />}
        >
          {(d) => (
            <>
              <div className="-mx-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-2">Team</th><th className="px-3 py-2">Leader</th><th className="px-3 py-2">Subscription</th>
                      <th className="px-3 py-2 text-right">Seats used</th><th className="px-3 py-2 text-right">Seats free</th>
                      <th className="px-3 py-2 text-right">Today</th><th className="px-3 py-2 text-right">This month</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {d.rows.map((r) => (
                      <tr
                        key={r.team_id}
                        onClick={() => setSelected(r.team_id)}
                        className={cn('cursor-pointer hover:bg-slate-50', r.team_id === active && 'bg-indigo-50/60')}
                      >
                        <td className="whitespace-nowrap px-4 py-2">
                          <span className="font-medium text-slate-800">{r.name}</span>
                          <span className="block text-xs text-slate-500">{r.unit_code}{r.department_name ? ` / ${r.department_name}` : ''} · {r.members} member(s)</span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2">{r.lead_name ?? '—'}</td>
                        <td className="px-3 py-2">
                          {r.subscriptions.length === 0
                            ? <span className="text-slate-400">None</span>
                            : r.subscriptions.map((s) => (
                                <span key={s.subscription_id} className="block whitespace-nowrap">
                                  {s.name} {s.metered && <Badge tone="blue">Metered</Badge>}
                                  <span className="ml-1 text-xs text-slate-500">{money(s.amount_bdt)} this month</span>
                                </span>
                              ))}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {r.subscriptions.map((s) => <span key={s.subscription_id} className="block">{s.seats_used} / {s.seats_total}</span>)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {r.subscriptions.map((s) => <span key={s.subscription_id} className="block">{s.seats_free}</span>)}
                        </td>
                        <td className="px-3 py-2 text-right"><MoneyText amount={r.today_bdt} /></td>
                        <td className="px-3 py-2 text-right"><MoneyText amount={r.month_to_date_bdt} estimated={r.estimated} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {active !== null && <TeamDaily teamId={active} />}
            </>
          )}
        </QueryState>
      </div>
    </Card>
  );
}
