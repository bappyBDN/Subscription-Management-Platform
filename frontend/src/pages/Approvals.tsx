import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { settingsApi } from '@/api/masters';
import { requestsApi } from '@/api/requests';
import { useAuth } from '@/auth/AuthProvider';
import { DataTable, type Columns } from '@/components/DataTable';
import { EmptyState, ErrorState, LoadingRows, MoneyText, StatusBadge } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Alert, Button, Card, Dialog, Field, PageHeader, Tabs, Textarea, cn } from '@/components/ui';
import { useAction } from '@/hooks';
import { DEFAULT_SLA_DAYS } from '@/lib/constants';
import { fmtDate } from '@/lib/format';
import type { RequestRow } from '@/types';

type TabId = 'waiting' | 'hold' | 'decided';
const DECIDED_STATUSES = ['rejected', 'approved', 'handover_pending', 'active', 'ended', 'info_needed'];

/** The one-tap positive action for a row */
const quickAction = (r: RequestRow) => (r.status === 'pending_manager' ? 'recommend' : 'approve');
const quickLabel = (r: RequestRow) => (r.status === 'pending_manager' ? 'Recommend' : 'Approve');

export default function Approvals() {
  const { isDmd, isAdmin } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<TabId>('waiting');
  const [selected, setSelected] = useState<number[]>([]);
  const [rejecting, setRejecting] = useState<RequestRow | null>(null);
  const [comment, setComment] = useState('');

  const pending = useQuery({ queryKey: ['requests', 'pending', ''], queryFn: () => requestsApi.list('pending') });
  // "Decided": requests from my team (managers) or everyone (DMD Sir) that have moved past my step
  const decidedScope = isAdmin ? 'all' : 'team';
  const decided = useQuery({
    queryKey: ['requests', decidedScope, ''],
    queryFn: () => requestsApi.list(decidedScope),
    enabled: tab === 'decided',
  });
  const settings = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get, enabled: isAdmin });
  const sla = Number(settings.data?.approval_sla_days) || DEFAULT_SLA_DAYS;

  const waiting = useMemo(() => pending.data?.filter((r) => r.status !== 'on_hold') ?? [], [pending.data]);
  const onHold = useMemo(() => pending.data?.filter((r) => r.status === 'on_hold') ?? [], [pending.data]);
  const decidedRows = useMemo(
    () => decided.data?.filter((r) => DECIDED_STATUSES.includes(r.status) || (!isDmd && r.status === 'pending_dmd')),
    [decided.data, isDmd],
  );

  const decide = useAction(
    (v: { row: RequestRow; decision: string; comment?: string }) =>
      requestsApi.decide(v.row.id, { decision: v.decision, comment: v.comment || null }),
    {
      success: (r) => `${r.req_no} updated`,
      onSuccess: () => {
        setRejecting(null);
        setComment('');
      },
    },
  );
  const bulk = useAction((ids: number[]) => requestsApi.bulkApprove(ids), {
    onSuccess: (res) => {
      setSelected([]);
      if (res.approved.length) toast.success(`${res.approved.length} request(s) approved`);
      if (res.failed.length) toast.error(`${res.failed.length} could not be approved: ${res.failed.map((f) => f.error).join('; ')}`);
    },
  });

  const rows = tab === 'waiting' ? waiting : tab === 'hold' ? onHold : decidedRows;
  const query = tab === 'decided' ? decided : pending;
  const actionable = tab !== 'decided';
  // bulk approve applies to DMD Sir's own step only
  const bulkable = (r: RequestRow) => isDmd && (r.status === 'pending_dmd' || r.status === 'on_hold');
  const bulkIds = (rows ?? []).filter(bulkable).map((r) => r.id);

  const columns = useMemo<Columns<RequestRow>>(() => {
    const cols: Columns<RequestRow> = [];
    if (isDmd && actionable) {
      cols.push({
        id: 'select',
        enableSorting: false,
        header: () => (
          <input
            type="checkbox"
            aria-label="Select all"
            className="h-4 w-4 accent-indigo-600"
            checked={bulkIds.length > 0 && bulkIds.every((id) => selected.includes(id))}
            onChange={(e) => setSelected(e.target.checked ? bulkIds : [])}
          />
        ),
        cell: ({ row }) =>
          bulkable(row.original) ? (
            <input
              type="checkbox"
              aria-label={`Select ${row.original.req_no}`}
              className="h-4 w-4 accent-indigo-600"
              checked={selected.includes(row.original.id)}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) =>
                setSelected((ids) => (e.target.checked ? [...ids, row.original.id] : ids.filter((x) => x !== row.original.id)))
              }
            />
          ) : null,
      });
    }
    cols.push(
      { header: 'Number', accessorKey: 'req_no', cell: ({ getValue }) => <span className="whitespace-nowrap font-medium text-indigo-700">{getValue<string>()}</span> },
      {
        header: 'Employee',
        accessorFn: (r) => r.snapshot.name ?? '',
        cell: ({ row }) => (
          <span>
            {row.original.snapshot.name}
            <span className="block text-xs text-slate-500">{row.original.snapshot.emp_code} · {row.original.snapshot.team ?? '—'}</span>
          </span>
        ),
      },
      { header: 'Tool / plan', accessorFn: (r) => `${r.tool_name} ${r.plan_name}`, cell: ({ row }) => <span>{row.original.tool_name} <span className="text-slate-500">{row.original.plan_name}</span></span> },
      { header: 'Monthly cost', accessorFn: (r) => Number(r.est_cost_bdt ?? 0), cell: ({ row }) => <MoneyText amount={row.original.est_cost_bdt} estimated={row.original.est_cost_bdt !== null} /> },
    );
    if (actionable) {
      cols.push({
        header: 'Waiting',
        accessorKey: 'waiting_days',
        cell: ({ getValue }) => {
          const days = getValue<number>();
          return <span className={cn('whitespace-nowrap', days > sla && 'font-semibold text-red-600')}>{days} day{days === 1 ? '' : 's'}</span>;
        },
      });
    } else {
      cols.push({ header: 'Updated', accessorKey: 'status_changed_at', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmtDate(getValue<string>())}</span> });
    }
    cols.push({ header: 'Status', accessorKey: 'status', cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> });
    return cols;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDmd, actionable, selected, bulkIds.join(','), sla]);

  const tabs: { id: TabId; label: string; count?: number }[] = [{ id: 'waiting', label: 'Waiting for me', count: waiting.length }];
  if (isDmd) tabs.push({ id: 'hold', label: 'On hold', count: onHold.length });
  tabs.push({ id: 'decided', label: isDmd ? 'Decided' : 'Decided · my team' });

  return (
    <>
      <PageHeader
        title="Approvals"
        subtitle={`Requests older than ${sla} day(s) are shown in red.`}
        actions={
          isDmd && actionable && (
            <Button disabled={!selected.length} loading={bulk.isPending} onClick={() => bulk.mutate(selected)}>
              Bulk approve{selected.length ? ` (${selected.length})` : ''}
            </Button>
          )
        }
      />
      <div className="mb-3">
        <Tabs tabs={tabs} value={tab} onChange={(id) => { setTab(id); setSelected([]); }} />
      </div>

      {/* desktop: table */}
      <Card className="hidden sm:block [&>div:last-child]:p-0">
        <DataTable
          columns={columns}
          data={rows}
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          onRowClick={(r) => navigate(actionable ? `/approvals/${r.id}` : `/requests/${r.id}`)}
          emptyTitle={tab === 'waiting' ? 'Nothing is waiting for you' : tab === 'hold' ? 'Nothing is on hold' : 'No decided requests yet'}
          emptyHint={tab === 'waiting' ? 'New requests from your team appear here.' : undefined}
        />
      </Card>

      {/* mobile: cards with two-tap actions */}
      <div className="space-y-3 sm:hidden">
        {query.isLoading ? (
          <Card><LoadingRows /></Card>
        ) : query.error ? (
          <Card><ErrorState error={query.error} onRetry={() => query.refetch()} /></Card>
        ) : !rows?.length ? (
          <Card><EmptyState title={tab === 'waiting' ? 'Nothing is waiting for you' : 'Nothing here'} /></Card>
        ) : (
          rows.map((r) => (
            <div key={r.id} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <Link to={actionable ? `/approvals/${r.id}` : `/requests/${r.id}`} className="block">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{r.tool_name} <span className="font-normal text-slate-500">{r.plan_name}</span></p>
                    <p className="text-sm text-slate-600">{r.snapshot.name} · {r.snapshot.emp_code}</p>
                    <p className="text-xs text-slate-500">{r.req_no} · {r.snapshot.team ?? '—'}</p>
                  </div>
                  <StatusBadge status={r.status} />
                </div>
                <div className="mt-2 flex items-center justify-between text-sm">
                  <MoneyText amount={r.est_cost_bdt} estimated={r.est_cost_bdt !== null} />
                  {actionable && (
                    <span className={cn('text-xs', r.waiting_days > sla ? 'font-semibold text-red-600' : 'text-slate-500')}>
                      waiting {r.waiting_days} day{r.waiting_days === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
              </Link>
              {actionable && (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button variant="success" loading={decide.isPending && decide.variables?.row.id === r.id} onClick={() => decide.mutate({ row: r, decision: quickAction(r) })}>
                    {quickLabel(r)}
                  </Button>
                  <Button variant="danger" onClick={() => { setRejecting(r); setComment(''); }}>Reject</Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <Dialog
        open={!!rejecting}
        onClose={() => setRejecting(null)}
        title={`Reject ${rejecting?.req_no ?? ''}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejecting(null)}>Cancel</Button>
            <Button
              variant="danger"
              loading={decide.isPending}
              disabled={!comment.trim()}
              onClick={() => rejecting && decide.mutate({ row: rejecting, decision: 'reject', comment: comment.trim() })}
            >
              Reject
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Alert tone="amber">The requester will see your comment.</Alert>
          <Field label="Reason for rejecting" required>
            <Textarea autoFocus value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
        </div>
      </Dialog>
    </>
  );
}
