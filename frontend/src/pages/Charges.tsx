import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { chargesApi } from '@/api/subscriptions';
import { DataTable, type Columns } from '@/components/DataTable';
import { ChargeFormDialog } from '@/components/forms';
import { MoneyText } from '@/components/shared';
import { Badge, Button, Card, Dialog, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAction, useCards, useSubscriptions } from '@/hooks';
import { fmtDate, money, num, todayIso } from '@/lib/format';
import type { Charge } from '@/types';

export default function Charges() {
  const [filters, setFilters] = useState({ month: todayIso().slice(0, 7), card_id: '', subscription_id: '', expected: '', reconciled: '' });
  const query = useQuery({ queryKey: ['charges', filters], queryFn: () => chargesApi.list(filters) });
  const subs = useSubscriptions();
  const cards = useCards();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Charge | null>(null);
  const [deleting, setDeleting] = useState<Charge | null>(null);

  const toggle = useAction((c: Charge) => chargesApi.update(c.id, { reconciled: !c.reconciled }), {
    success: (c) => (c.reconciled ? 'Marked reconciled' : 'Marked not reconciled'),
  });
  const remove = useAction((c: Charge) => chargesApi.remove(c.id), { success: 'Charge deleted', onSuccess: () => setDeleting(null) });

  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => setFilters((f) => ({ ...f, [key]: e.target.value }));
  const subName = useMemo(() => new Map(subs.data?.map((s) => [s.id, `${s.vendor_name} ${s.plan_name}`])), [subs.data]);
  const cardName = useMemo(() => new Map(cards.data?.map((c) => [c.id, `•••• ${c.last4}`])), [cards.data]);

  const columns = useMemo<Columns<Charge>>(
    () => [
      { header: 'Date', accessorKey: 'charge_date', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmtDate(getValue<string>())}</span> },
      { header: 'Subscription', accessorFn: (c) => subName.get(c.subscription_id) ?? `#${c.subscription_id}` },
      { header: 'Card', accessorFn: (c) => (c.card_id ? cardName.get(c.card_id) ?? '—' : '—'), cell: ({ getValue }) => <span className="whitespace-nowrap">{getValue<string>()}</span> },
      { header: 'Amount', accessorFn: (c) => Number(c.amount_original), cell: ({ row }) => <MoneyText amount={row.original.amount_original} currency={row.original.currency} /> },
      { header: 'FX', accessorFn: (c) => Number(c.fx_rate), cell: ({ row }) => String(row.original.fx_rate) },
      { header: 'Bank fee', accessorFn: (c) => Number(c.bank_fee_bdt), cell: ({ row }) => <MoneyText amount={row.original.bank_fee_bdt} /> },
      { header: 'BDT total', accessorFn: (c) => Number(c.amount_bdt), cell: ({ row }) => <MoneyText amount={row.original.amount_bdt} estimated={row.original.is_expected} className="font-medium" /> },
      { header: 'Reference', accessorKey: 'reference', cell: ({ getValue }) => getValue<string | null>() ?? '—' },
      {
        header: 'State',
        accessorFn: (c) => (c.is_expected ? 'expected' : c.reconciled ? 'reconciled' : 'open'),
        cell: ({ row }) => row.original.is_expected ? <Badge tone="amber">Expected</Badge> : row.original.reconciled ? <Badge tone="green">Reconciled</Badge> : <Badge tone="slate">Not reconciled</Badge>,
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1 whitespace-nowrap">
            {!row.original.is_expected && (
              <Button size="sm" variant="ghost" onClick={() => toggle.mutate(row.original)}>
                {row.original.reconciled ? 'Unreconcile' : 'Reconcile'}
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => { setEditing(row.original); setFormOpen(true); }}>Edit</Button>
            <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50" onClick={() => setDeleting(row.original)}>Delete</Button>
          </div>
        ),
      },
    ],
    [subName, cardName, toggle],
  );

  const actual = query.data?.filter((c) => !c.is_expected) ?? [];
  const total = actual.reduce((sum, c) => sum + num(c.amount_bdt), 0);

  return (
    <>
      <PageHeader
        title="Card charges"
        subtitle="What the card was actually charged, in BDT."
        actions={<Button onClick={() => { setEditing(null); setFormOpen(true); }}>Record charge</Button>}
      />
      <Card className="mb-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Field label="Month"><Input type="month" value={filters.month} onChange={set('month')} /></Field>
          <Field label="Card">
            <Select value={filters.card_id} onChange={set('card_id')}>
              <option value="">Every card</option>
              {cards.data?.map((c) => <option key={c.id} value={c.id}>{c.label} •••• {c.last4}</option>)}
            </Select>
          </Field>
          <Field label="Subscription">
            <Select value={filters.subscription_id} onChange={set('subscription_id')}>
              <option value="">Every subscription</option>
              {subs.data?.map((s) => <option key={s.id} value={s.id}>{s.vendor_name} {s.plan_name}</option>)}
            </Select>
          </Field>
          <Field label="Expected / actual">
            <Select value={filters.expected} onChange={set('expected')}>
              <option value="">Both</option>
              <option value="false">Actual</option>
              <option value="true">Expected</option>
            </Select>
          </Field>
          <Field label="Reconciled">
            <Select value={filters.reconciled} onChange={set('reconciled')}>
              <option value="">Both</option>
              <option value="true">Reconciled</option>
              <option value="false">Not reconciled</option>
            </Select>
          </Field>
        </div>
      </Card>
      <Card
        className="[&>div:last-child]:p-0"
        title={query.data ? `${actual.length} actual charge(s) · ${money(total)}` : 'Charges'}
      >
        <DataTable
          columns={columns}
          data={query.data}
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          emptyTitle="No charges match these filters"
          emptyHint="Record each card charge so the paid view of the dashboard is exact."
        />
      </Card>

      <ChargeFormDialog open={formOpen} onClose={() => setFormOpen(false)} charge={editing} subscriptions={subs.data} />
      <Dialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title="Delete this charge?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)}>Keep it</Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => deleting && remove.mutate(deleting)}>Delete</Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          {deleting && <>{money(deleting.amount_bdt)} on {fmtDate(deleting.charge_date)} will be removed from paid totals. The deletion is kept in the audit log.</>}
        </p>
      </Dialog>
    </>
  );
}
