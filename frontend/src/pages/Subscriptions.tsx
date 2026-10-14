import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { subscriptionsApi } from '@/api/subscriptions';
import { DataTable, type Columns } from '@/components/DataTable';
import { EmployeeSearch } from '@/components/EmployeeSearch';
import { ChargeFormDialog, ImportDialog, SubscriptionFormDialog } from '@/components/forms';
import { MoneyText, StatusBadge } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Badge, Button, Card, Dialog, Field, Input, PageHeader, Select, Textarea } from '@/components/ui';
import { useAction, useSubscriptions, useUnits, useVendors } from '@/hooks';
import { SUBSCRIPTION_STATUSES } from '@/lib/constants';
import { fmtDate, label, todayIso } from '@/lib/format';
import type { Employee, Subscription } from '@/types';

export function AssignDialog({ subscription, onClose }: { subscription: Subscription | null; onClose: () => void }) {
  const toast = useToast();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [start, setStart] = useState(todayIso());
  const [end, setEnd] = useState('');
  const assign = useAction(
    () => subscriptionsApi.assign(subscription!.id, { employee_id: employee!.id, start_date: start || null, end_date: end || null }),
    {
      success: 'Seat assigned',
      onSuccess: () => {
        setEmployee(null);
        onClose();
      },
    },
  );
  return (
    <Dialog
      open={!!subscription}
      onClose={onClose}
      title={`Assign a seat · ${subscription?.vendor_name ?? ''} ${subscription?.plan_name ?? ''}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={assign.isPending} onClick={() => (employee ? assign.mutate(undefined) : toast.error('Choose an employee'))}>Assign</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Employee" required>
          <EmployeeSearch value={employee} onChange={setEmployee} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="From"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="Until" hint="Empty = open-ended"><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
        </div>
      </div>
    </Dialog>
  );
}

export function CancelDialog({ subscription, onClose }: { subscription: Subscription | null; onClose: () => void }) {
  const [date, setDate] = useState(todayIso());
  const [reason, setReason] = useState('');
  const cancel = useAction(
    () => subscriptionsApi.cancel(subscription!.id, { cancelled_on: date || null, reason: reason.trim() || null }),
    { success: 'Subscription cancelled — holders have been notified', onSuccess: onClose },
  );
  return (
    <Dialog
      open={!!subscription}
      onClose={onClose}
      title={`Cancel ${subscription?.vendor_name ?? ''} ${subscription?.plan_name ?? ''}?`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Keep it</Button>
          <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate(undefined)}>Cancel subscription</Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          All {subscription?.seats_used ?? 0} seat(s) will be revoked and cost stops accruing from the cancellation date. This cannot be undone.
        </p>
        <Field label="Cancelled on"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        <Field label="Reason" hint="Sent to the people who hold a seat."><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </div>
    </Dialog>
  );
}

export default function Subscriptions() {
  const navigate = useNavigate();
  const vendors = useVendors(true);
  const units = useUnits(true);
  const [filters, setFilters] = useState({ status: 'active', vendor_id: '', unit_id: '', department_id: '', owner_scope: '', renewal_within_days: '' });
  const departments = units.data?.find((u) => String(u.id) === filters.unit_id)?.departments ?? [];
  const query = useSubscriptions(filters);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [assigning, setAssigning] = useState<Subscription | null>(null);
  const [charging, setCharging] = useState<Subscription | null>(null);
  const [cancelling, setCancelling] = useState<Subscription | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => setFilters((f) => ({ ...f, [key]: e.target.value }));
  const today = todayIso();

  const columns = useMemo<Columns<Subscription>>(
    () => [
      { header: 'Tool', accessorKey: 'vendor_name', cell: ({ getValue }) => <span className="font-medium text-indigo-700">{getValue<string>()}</span> },
      { header: 'Plan', accessorKey: 'plan_name' },
      {
        header: 'Owner',
        accessorKey: 'owner_label',
        cell: ({ row }) => (
          <span className="block max-w-[16rem]">
            {row.original.owner_label}
            {row.original.owner_scope === 'shared' && <span className="ml-1"><Badge tone="blue">Shared</Badge></span>}
          </span>
        ),
      },
      {
        header: 'Bought with',
        accessorKey: 'account_email',
        cell: ({ getValue }) => <span className="whitespace-nowrap text-slate-700">{getValue<string | null>() ?? '—'}</span>,
      },
      { header: 'Seats', accessorFn: (s) => s.seats_used, cell: ({ row }) => <span className="whitespace-nowrap">{row.original.seats_used} / {row.original.seats_total}</span> },
      {
        header: 'Cost / cycle',
        accessorFn: (s) => Number(s.cost_per_cycle),
        cell: ({ row }) => (
          <span className="whitespace-nowrap">
            <MoneyText amount={row.original.cost_per_cycle} currency={row.original.currency} />
            <span className="block text-xs text-slate-500">{label(row.original.billing_cycle)}</span>
          </span>
        ),
      },
      {
        header: 'Next renewal',
        accessorKey: 'next_renewal_date',
        cell: ({ row }) => {
          const d = row.original.next_renewal_date;
          return (
            <span className="whitespace-nowrap">
              {fmtDate(d)} {d && d < today && row.original.status === 'active' && <Badge tone="red">Overdue</Badge>}
            </span>
          );
        },
      },
      { header: 'Status', accessorKey: 'status', cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => {
          const s = row.original;
          const live = s.status !== 'cancelled';
          return (
            <div className="flex justify-end gap-1 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
              <Button size="sm" variant="ghost" onClick={() => { setEditing(s); setFormOpen(true); }}>Edit</Button>
              {live && <Button size="sm" variant="ghost" disabled={s.seats_used >= s.seats_total} title={s.seats_used >= s.seats_total ? 'No free seat' : undefined} onClick={() => setAssigning(s)}>Assign</Button>}
              <Button size="sm" variant="ghost" onClick={() => setCharging(s)}>Charge</Button>
              {live && <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50" onClick={() => setCancelling(s)}>Cancel</Button>}
            </div>
          );
        },
      },
    ],
    [today],
  );

  return (
    <>
      <PageHeader
        title="Subscriptions"
        subtitle="Every paid subscription, the account it was bought with, and the SBU, department or function that owns it."
        actions={
          <>
            <Button variant="secondary" onClick={() => setImportOpen(true)}>Import</Button>
            <Button onClick={() => { setEditing(null); setFormOpen(true); }}>Add subscription</Button>
          </>
        }
      />
      <Card className="mb-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Field label="Status">
            <Select value={filters.status} onChange={set('status')}>
              <option value="">Every status</option>
              {SUBSCRIPTION_STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
            </Select>
          </Field>
          <Field label="Tool">
            <Select value={filters.vendor_id} onChange={set('vendor_id')}>
              <option value="">Every tool</option>
              {vendors.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </Select>
          </Field>
          <Field label="SBU">
            <Select value={filters.unit_id} onChange={(e) => setFilters((f) => ({ ...f, unit_id: e.target.value, department_id: '' }))}>
              <option value="">Every SBU</option>
              {units.data?.map((u) => <option key={u.id} value={u.id}>{u.code}</option>)}
            </Select>
          </Field>
          <Field label="Department">
            <Select value={filters.department_id} onChange={set('department_id')} disabled={!filters.unit_id}>
              <option value="">{filters.unit_id ? 'Every department' : 'Choose an SBU first'}</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          </Field>
          <Field label="Owned by">
            <Select value={filters.owner_scope} onChange={set('owner_scope')}>
              <option value="">Any owner</option>
              <option value="unit">Whole SBU</option>
              <option value="department">A department</option>
              <option value="function">A function</option>
              <option value="shared">Shared</option>
            </Select>
          </Field>
          <Field label="Renewal within (days)">
            <Input type="number" min={0} value={filters.renewal_within_days} onChange={set('renewal_within_days')} placeholder="Any" />
          </Field>
        </div>
      </Card>
      <Card className="[&>div:last-child]:p-0">
        <DataTable
          columns={columns}
          data={query.data}
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          onRowClick={(s) => navigate(`/subscriptions/${s.id}`)}
          emptyTitle="No subscriptions match these filters"
          emptyHint="Add one, or import your existing list from Excel."
        />
      </Card>

      <SubscriptionFormDialog open={formOpen} onClose={() => setFormOpen(false)} subscription={editing} />
      <AssignDialog subscription={assigning} onClose={() => setAssigning(null)} />
      <ChargeFormDialog open={!!charging} onClose={() => setCharging(null)} subscription={charging} />
      <CancelDialog subscription={cancelling} onClose={() => setCancelling(null)} />
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import subscriptions"
        columns="vendor, plan_name, type, seats_total, cost_per_cycle, currency, billing_cycle, start_date, next_renewal_date, card_last4, account_email, unit (SBU code), department (name), owner_scope (unit or department), holder_codes"
        upload={subscriptionsApi.importFile}
      />
    </>
  );
}
