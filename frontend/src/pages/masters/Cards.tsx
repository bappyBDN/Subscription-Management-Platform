import { useEffect, useMemo, useState } from 'react';

import { cardsApi } from '@/api/masters';
import { DataTable, type Columns } from '@/components/DataTable';
import { useToast } from '@/components/Toast';
import { Alert, Badge, Button, Card, Checkbox, Dialog, Field, Input, PageHeader } from '@/components/ui';
import { useAction, useCards } from '@/hooks';
import type { CardRow } from '@/types';

function CardDialog({ open, onClose, card }: { open: boolean; onClose: () => void; card: CardRow | null }) {
  const toast = useToast();
  const [labelText, setLabelText] = useState('');
  const [holder, setHolder] = useState('');
  const [last4, setLast4] = useState('');
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setLabelText(card?.label ?? '');
    setHolder(card?.holder_name ?? '');
    setLast4(card?.last4 ?? '');
    setActive(card?.active ?? true);
  }, [open, card]);

  const save = useAction(
    () => {
      const body = { label: labelText.trim(), holder_name: holder.trim(), last4, active };
      return card ? cardsApi.update(card.id, body) : cardsApi.create(body);
    },
    { success: card ? 'Card updated' : 'Card added', onSuccess: onClose },
  );
  const submit = () => {
    if (!labelText.trim() || !holder.trim()) return toast.error('Enter the label and the card holder');
    if (!/^\d{4}$/.test(last4)) return toast.error('Enter exactly the last 4 digits');
    save.mutate(undefined);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={card ? `Edit ${card.label}` : 'Add card'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={submit}>Save</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Alert tone="amber">Only the last 4 digits are stored. Never enter a full card number anywhere in SMP.</Alert>
        <Field label="Label" required hint="e.g. DMD Visa"><Input value={labelText} maxLength={60} onChange={(e) => setLabelText(e.target.value)} /></Field>
        <Field label="Card holder" required><Input value={holder} maxLength={120} onChange={(e) => setHolder(e.target.value)} /></Field>
        <Field label="Last 4 digits" required>
          <Input inputMode="numeric" maxLength={4} value={last4} onChange={(e) => setLast4(e.target.value.replace(/\D/g, ''))} className="w-28 tracking-widest" />
        </Field>
        <Checkbox label="Active" checked={active} onChange={(e) => setActive(e.target.checked)} />
      </div>
    </Dialog>
  );
}

export default function Cards() {
  const query = useCards();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CardRow | null>(null);

  const columns = useMemo<Columns<CardRow>>(
    () => [
      { header: 'Label', accessorKey: 'label', cell: ({ getValue }) => <span className="font-medium">{getValue<string>()}</span> },
      { header: 'Card holder', accessorKey: 'holder_name' },
      { header: 'Number', accessorKey: 'last4', cell: ({ getValue }) => <span className="whitespace-nowrap">•••• {getValue<string>()}</span> },
      { header: 'Status', accessorKey: 'active', cell: ({ getValue }) => (getValue<boolean>() ? <Badge tone="green">Active</Badge> : <Badge tone="slate">Inactive</Badge>) },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => (
          <div className="text-right">
            <Button size="sm" variant="ghost" onClick={() => { setEditing(row.original); setFormOpen(true); }}>Edit</Button>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader title="Cards" subtitle="The cards subscriptions are paid with." actions={<Button onClick={() => { setEditing(null); setFormOpen(true); }}>Add card</Button>} />
      <Card className="[&>div:last-child]:p-0">
        <DataTable columns={columns} data={query.data} isLoading={query.isLoading} error={query.error} onRetry={() => query.refetch()} emptyTitle="No cards yet" emptyHint="Add DMD Sir's card so charges can be matched to it." />
      </Card>
      <CardDialog open={formOpen} onClose={() => setFormOpen(false)} card={editing} />
    </>
  );
}
