import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { requestsApi } from '@/api/requests';
import { chargesApi, subscriptionsApi } from '@/api/subscriptions';
import { DataTable, type Columns } from '@/components/DataTable';
import { ChargeFormDialog, SubscriptionFormDialog } from '@/components/forms';
import { ErrorState, LoadingRows, MoneyText, StatusBadge } from '@/components/shared';
import { Badge, Button, Card, Details, PageHeader } from '@/components/ui';
import { useAction } from '@/hooks';
import { fmtDate, label } from '@/lib/format';
import type { Assignment, Charge, RequestRow } from '@/types';

import { AssignDialog, CancelDialog } from './Subscriptions';

export default function SubscriptionDetailPage() {
  const id = Number(useParams().id);
  const query = useQuery({ queryKey: ['subscription', id], queryFn: () => subscriptionsApi.get(id), enabled: Number.isFinite(id) });
  const charges = useQuery({ queryKey: ['charges', { subscription_id: id }], queryFn: () => chargesApi.list({ subscription_id: id }) });
  // the API has no "requests of a subscription" filter, so the latest requests are filtered here
  const requests = useQuery({ queryKey: ['requests', 'all', ''], queryFn: () => requestsApi.list('all') });

  const [editOpen, setEditOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [chargeOpen, setChargeOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const revoke = useAction((assignmentId: number) => subscriptionsApi.revoke(id, assignmentId), { success: 'Seat revoked' });

  const assignmentCols = useMemo<Columns<Assignment>>(
    () => [
      { header: 'Employee', accessorKey: 'employee_name', cell: ({ row }) => <span>{row.original.employee_name} <span className="text-slate-500">({row.original.emp_code})</span></span> },
      { header: 'From', accessorKey: 'start_date', cell: ({ getValue }) => fmtDate(getValue<string>()) },
      { header: 'Until', accessorKey: 'end_date', cell: ({ getValue }) => fmtDate(getValue<string | null>()) },
      { header: 'Status', accessorKey: 'status', cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) =>
          row.original.status !== 'revoked' ? (
            <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50" loading={revoke.isPending && revoke.variables === row.original.id} onClick={() => revoke.mutate(row.original.id)}>
              Revoke
            </Button>
          ) : null,
      },
    ],
    [revoke],
  );

  const chargeCols = useMemo<Columns<Charge>>(
    () => [
      { header: 'Date', accessorKey: 'charge_date', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmtDate(getValue<string>())}</span> },
      { header: 'Amount', accessorFn: (c) => Number(c.amount_original), cell: ({ row }) => <MoneyText amount={row.original.amount_original} currency={row.original.currency} /> },
      { header: 'FX', accessorFn: (c) => Number(c.fx_rate), cell: ({ row }) => String(row.original.fx_rate) },
      { header: 'BDT total', accessorFn: (c) => Number(c.amount_bdt), cell: ({ row }) => <MoneyText amount={row.original.amount_bdt} estimated={row.original.is_expected} /> },
      { header: 'Reference', accessorKey: 'reference', cell: ({ getValue }) => getValue<string | null>() ?? '—' },
      { header: 'State', accessorFn: (c) => (c.is_expected ? 'expected' : c.reconciled ? 'reconciled' : 'open'), cell: ({ row }) => row.original.is_expected ? <Badge tone="amber">Expected</Badge> : row.original.reconciled ? <Badge tone="green">Reconciled</Badge> : <Badge tone="slate">Not reconciled</Badge> },
    ],
    [],
  );

  const requestCols = useMemo<Columns<RequestRow>>(
    () => [
      { header: 'Number', accessorKey: 'req_no', cell: ({ row }) => <Link className="font-medium text-indigo-700 hover:underline" to={`/requests/${row.original.id}`}>{row.original.req_no}</Link> },
      { header: 'Employee', accessorFn: (r) => r.snapshot.name ?? '' },
      { header: 'Type', accessorKey: 'type', cell: ({ getValue }) => label(getValue<string>()) },
      { header: 'Submitted', accessorKey: 'submitted_at', cell: ({ getValue }) => fmtDate(getValue<string>()) },
      { header: 'Status', accessorKey: 'status', cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> },
    ],
    [],
  );

  if (query.isLoading) return <LoadingRows rows={6} />;
  if (query.error || !query.data) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  const s = query.data;
  const live = s.status !== 'cancelled';
  // linked = raised against this subscription, or the request a seat here came from
  const seatRequests = new Set(s.assignments.map((a) => a.request_id));
  const linked = requests.data?.filter((r) => r.subscription_id === id || seatRequests.has(r.id));

  return (
    <>
      <PageHeader
        title={`${s.vendor_name} ${s.plan_name}`}
        subtitle={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={s.status} /> {label(s.type)} · {s.seats_used} of {s.seats_total} seats used</span>}
        actions={
          <>
            <Link to="/subscriptions"><Button variant="secondary">Back</Button></Link>
            <Button variant="secondary" onClick={() => setEditOpen(true)}>Edit</Button>
            {live && <Button variant="danger" onClick={() => setCancelOpen(true)}>Cancel</Button>}
          </>
        }
      />
      <div className="space-y-4">
        <Card title="Details">
          <Details
            items={[
              ['Cost per cycle', <MoneyText key="c" amount={s.cost_per_cycle} currency={s.currency} />],
              ['Billing cycle', label(s.billing_cycle)],
              ['Start date', fmtDate(s.start_date)],
              ['Next renewal', fmtDate(s.next_renewal_date)],
              ['Card', s.card_last4 ? `•••• ${s.card_last4}` : '—'],
              ['Account email', s.account_email ?? '—'],
              ['Unit', s.unit ?? '—'],
              ['Department', s.department ?? '—'],
              ...(s.cancelled_on ? [['Cancelled on', fmtDate(s.cancelled_on)] as [string, string]] : []),
              ['Notes', s.notes ?? '—'],
            ]}
          />
        </Card>

        <Card
          title="Seat assignments"
          className="[&>div:last-child]:p-0"
          actions={live && <Button size="sm" disabled={s.seats_used >= s.seats_total} onClick={() => setAssignOpen(true)}>Assign a seat</Button>}
        >
          <DataTable columns={assignmentCols} data={s.assignments} emptyTitle="No one holds a seat yet" />
        </Card>

        <Card title="Charges" className="[&>div:last-child]:p-0" actions={<Button size="sm" onClick={() => setChargeOpen(true)}>Record charge</Button>}>
          <DataTable
            columns={chargeCols}
            data={charges.data}
            isLoading={charges.isLoading}
            error={charges.error}
            onRetry={() => charges.refetch()}
            emptyTitle="No charges recorded"
            emptyHint="Until a card charge is recorded, cost is estimated from the plan price."
          />
        </Card>

        <Card title="Linked requests" className="[&>div:last-child]:p-0">
          <DataTable
            columns={requestCols}
            data={linked}
            isLoading={requests.isLoading}
            error={requests.error}
            onRetry={() => requests.refetch()}
            emptyTitle="No requests are linked to this subscription"
          />
        </Card>
      </div>

      <SubscriptionFormDialog open={editOpen} onClose={() => setEditOpen(false)} subscription={s} />
      <AssignDialog subscription={assignOpen ? s : null} onClose={() => setAssignOpen(false)} />
      <ChargeFormDialog open={chargeOpen} onClose={() => setChargeOpen(false)} subscription={s} />
      <CancelDialog subscription={cancelOpen ? s : null} onClose={() => setCancelOpen(false)} />
    </>
  );
}
