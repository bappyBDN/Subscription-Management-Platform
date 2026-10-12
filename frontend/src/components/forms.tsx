import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';

import { settingsApi } from '@/api/masters';
import { chargesApi, subscriptionsApi } from '@/api/subscriptions';
import { useAction, useCards, useVendors } from '@/hooks';
import { BILLING_CYCLES, CURRENCIES, SUBSCRIPTION_STATUSES, SUBSCRIPTION_TYPES, UNITS } from '@/lib/constants';
import { label, money, num, todayIso } from '@/lib/format';
import type { Charge, ImportResult, Subscription } from '@/types';

import { useToast } from './Toast';
import { Alert, Button, Checkbox, Dialog, Field, Input, Select, Textarea } from './ui';

const orNull = (v: unknown) => (v === '' || v === undefined ? null : v);

// ------------------------------------------------------------------ subscription

interface SubForm {
  vendor_id: string;
  plan_name: string;
  type: string;
  seats_total: number;
  cost_per_cycle: string;
  currency: string;
  billing_cycle: string;
  start_date: string;
  next_renewal_date: string;
  card_id: string;
  account_email: string;
  unit: string;
  department: string;
  status: string;
  notes: string;
}

export function SubscriptionFormDialog({
  open,
  onClose,
  subscription,
  defaults,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  subscription?: Subscription | null;
  defaults?: Partial<SubForm>;
  onSaved?: (sub: Subscription) => void;
}) {
  const vendors = useVendors(true);
  const cards = useCards();
  const form = useForm<SubForm>();
  const { register, handleSubmit, reset, formState } = form;

  useEffect(() => {
    if (!open) return;
    const s = subscription;
    reset({
      vendor_id: s ? String(s.vendor_id) : '',
      plan_name: s?.plan_name ?? '',
      type: s?.type ?? 'individual',
      seats_total: s?.seats_total ?? 1,
      cost_per_cycle: s ? String(s.cost_per_cycle) : '',
      currency: s?.currency ?? 'USD',
      billing_cycle: s?.billing_cycle ?? 'monthly',
      start_date: s?.start_date ?? todayIso(),
      next_renewal_date: s?.next_renewal_date ?? '',
      card_id: s?.card_id ? String(s.card_id) : '',
      account_email: s?.account_email ?? '',
      unit: s?.unit ?? '',
      department: s?.department ?? '',
      status: s?.status ?? 'active',
      notes: s?.notes ?? '',
      ...(s ? {} : defaults),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, subscription?.id]);

  const save = useAction(
    (v: SubForm) => {
      const body: Record<string, unknown> = {
        plan_name: v.plan_name.trim(),
        type: v.type,
        seats_total: Number(v.seats_total),
        cost_per_cycle: v.cost_per_cycle,
        currency: v.currency,
        billing_cycle: v.billing_cycle,
        start_date: v.start_date,
        next_renewal_date: orNull(v.next_renewal_date),
        card_id: v.card_id ? Number(v.card_id) : null,
        account_email: orNull(v.account_email.trim()),
        unit: orNull(v.unit),
        department: orNull(v.department.trim()),
        status: v.status,
        notes: orNull(v.notes.trim()),
      };
      return subscription
        ? subscriptionsApi.update(subscription.id, body)
        : subscriptionsApi.create({ ...body, vendor_id: Number(v.vendor_id) });
    },
    {
      success: subscription ? 'Subscription updated' : 'Subscription added to the register',
      onSuccess: (sub) => {
        onSaved?.(sub);
        onClose();
      },
    },
  );

  const e = formState.errors;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title={subscription ? `Edit ${subscription.vendor_name} ${subscription.plan_name}` : 'Add subscription'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={handleSubmit((v) => save.mutate(v))}>Save</Button>
        </>
      }
    >
      <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={(ev) => ev.preventDefault()}>
        <Field label="Tool" required error={e.vendor_id?.message}>
          <Select disabled={!!subscription} {...register('vendor_id', { required: 'Choose a tool' })}>
            <option value="">Choose…</option>
            {vendors.data?.map((v) => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Plan" required error={e.plan_name?.message}>
          <Input {...register('plan_name', { required: 'Enter the plan name' })} />
        </Field>
        <Field label="Type">
          <Select {...register('type')}>
            {SUBSCRIPTION_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </Select>
        </Field>
        <Field label="Seats" error={e.seats_total?.message}>
          <Input type="number" min={1} {...register('seats_total', { required: true, min: { value: 1, message: 'At least 1 seat' } })} />
        </Field>
        <Field label="Cost per cycle" required error={e.cost_per_cycle?.message}>
          <Input type="number" step="0.01" min={0} {...register('cost_per_cycle', { required: 'Enter the cost' })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Currency">
            <Select {...register('currency')}>
              {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </Field>
          <Field label="Billing cycle">
            <Select {...register('billing_cycle')}>
              {BILLING_CYCLES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Start date" required error={e.start_date?.message}>
          <Input type="date" {...register('start_date', { required: 'Enter the start date' })} />
        </Field>
        <Field label="Next renewal">
          <Input type="date" {...register('next_renewal_date')} />
        </Field>
        <Field label="Card">
          <Select {...register('card_id')}>
            <option value="">—</option>
            {cards.data?.map((c) => (
              <option key={c.id} value={c.id}>{c.label} •••• {c.last4}</option>
            ))}
          </Select>
        </Field>
        <Field label="Account email">
          <Input type="email" {...register('account_email')} />
        </Field>
        <Field label="Unit">
          <Select {...register('unit')}>
            <option value="">—</option>
            {UNITS.map((u) => <option key={u}>{u}</option>)}
          </Select>
        </Field>
        <Field label="Department">
          <Input {...register('department')} />
        </Field>
        {subscription && (
          <Field label="Status">
            <Select {...register('status')}>
              {SUBSCRIPTION_STATUSES.filter((s) => s !== 'cancelled' || subscription.status === 'cancelled').map((s) => (
                <option key={s} value={s}>{label(s)}</option>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Notes" className="sm:col-span-2" hint="Never enter card numbers here.">
          <Textarea rows={2} {...register('notes')} />
        </Field>
      </form>
    </Dialog>
  );
}

// ------------------------------------------------------------------ card charge

interface ChargeForm {
  subscription_id: string;
  card_id: string;
  charge_date: string;
  amount_original: string;
  currency: string;
  fx_rate: string;
  bank_fee_bdt: string;
  reference: string;
  is_expected: boolean;
  reconciled: boolean;
}

export function ChargeFormDialog({
  open,
  onClose,
  charge,
  subscription,
  subscriptions,
}: {
  open: boolean;
  onClose: () => void;
  charge?: Charge | null;
  /** fixed subscription (when recording from a subscription row) */
  subscription?: Subscription | null;
  subscriptions?: Subscription[];
}) {
  const cards = useCards();
  const settings = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get, enabled: open });
  const { register, handleSubmit, reset, watch, setValue, formState } = useForm<ChargeForm>();
  const defaultFx = settings.data?.default_fx_rate_usd ?? '';

  useEffect(() => {
    if (!open) return;
    const c = charge;
    reset({
      subscription_id: c ? String(c.subscription_id) : subscription ? String(subscription.id) : '',
      card_id: c?.card_id ? String(c.card_id) : subscription?.card_id ? String(subscription.card_id) : '',
      charge_date: c?.charge_date ?? todayIso(),
      amount_original: c ? String(c.amount_original) : subscription ? String(subscription.cost_per_cycle) : '',
      currency: c?.currency ?? subscription?.currency ?? 'USD',
      fx_rate: c ? String(c.fx_rate) : '',
      bank_fee_bdt: c ? String(c.bank_fee_bdt) : '0',
      reference: c?.reference ?? '',
      is_expected: c?.is_expected ?? false,
      reconciled: c?.reconciled ?? false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, charge?.id, subscription?.id]);

  const currency = watch('currency');
  const fx = watch('fx_rate');
  const amount = watch('amount_original');
  const fee = watch('bank_fee_bdt');

  // FX rate is prefilled from settings (1 for BDT) until the user types their own
  useEffect(() => {
    if (!open || charge || formState.dirtyFields.fx_rate) return;
    setValue('fx_rate', currency === 'BDT' ? '1' : currency === 'USD' ? String(defaultFx) : '');
  }, [open, charge, currency, defaultFx, setValue, formState.dirtyFields.fx_rate]);

  const totalBdt = useMemo(() => num(amount) * num(fx) + num(fee), [amount, fx, fee]);

  const save = useAction(
    (v: ChargeForm) => {
      const body: Record<string, unknown> = {
        card_id: v.card_id ? Number(v.card_id) : null,
        charge_date: v.charge_date,
        amount_original: v.amount_original,
        currency: v.currency,
        fx_rate: v.fx_rate || null,
        bank_fee_bdt: v.bank_fee_bdt || '0',
        reference: orNull(v.reference.trim()),
        is_expected: v.is_expected,
        reconciled: v.reconciled,
      };
      if (charge) {
        if (!body.fx_rate) delete body.fx_rate;
        return chargesApi.update(charge.id, body);
      }
      return chargesApi.create({ ...body, subscription_id: Number(v.subscription_id) });
    },
    { success: charge ? 'Charge updated' : 'Charge recorded', onSuccess: onClose },
  );

  const e = formState.errors;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={charge ? 'Edit charge' : 'Record card charge'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={handleSubmit((v) => save.mutate(v))}>Save</Button>
        </>
      }
    >
      <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={(ev) => ev.preventDefault()}>
        <Field label="Subscription" required className="sm:col-span-2" error={e.subscription_id?.message}>
          {subscription ? (
            <Input disabled value={`${subscription.vendor_name} ${subscription.plan_name}`} />
          ) : (
            <Select disabled={!!charge} {...register('subscription_id', { required: 'Choose the subscription' })}>
              <option value="">Choose…</option>
              {subscriptions?.map((s) => (
                <option key={s.id} value={s.id}>{s.vendor_name} {s.plan_name} (#{s.id})</option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Date" required error={e.charge_date?.message}>
          <Input type="date" {...register('charge_date', { required: 'Enter the date' })} />
        </Field>
        <Field label="Card">
          <Select {...register('card_id')}>
            <option value="">Subscription's card</option>
            {cards.data?.map((c) => (
              <option key={c.id} value={c.id}>{c.label} •••• {c.last4}</option>
            ))}
          </Select>
        </Field>
        <Field label="Amount" required error={e.amount_original?.message}>
          <Input type="number" step="0.01" min={0} {...register('amount_original', {
            required: 'Enter the amount',
            validate: (v) => num(v) > 0 || 'Amount must be more than 0',
          })} />
        </Field>
        <Field label="Currency">
          <Select {...register('currency')}>
            {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
          </Select>
        </Field>
        <Field label="FX rate (BDT per unit)" hint={currency === 'USD' && defaultFx ? `Default ${defaultFx}` : undefined} error={e.fx_rate?.message}>
          <Input type="number" step="0.0001" min={0} {...register('fx_rate', {
            validate: (v) => !v || num(v) > 0 || 'FX rate must be more than 0',
          })} />
        </Field>
        <Field label="Bank fee (BDT)">
          <Input type="number" step="0.01" min={0} {...register('bank_fee_bdt')} />
        </Field>
        <Field label="BDT total" className="sm:col-span-2" hint="Amount × FX rate + bank fee. The server stores its own calculation.">
          <Input readOnly tabIndex={-1} value={money(totalBdt, 'BDT')} className="bg-slate-100 font-semibold" />
        </Field>
        <Field label="Reference" className="sm:col-span-2" hint="Statement reference or receipt number — never the card number.">
          <Input {...register('reference')} />
        </Field>
        <Checkbox label="Expected (not charged yet)" {...register('is_expected')} />
        <Checkbox label="Reconciled with statement" {...register('reconciled')} />
      </form>
    </Dialog>
  );
}

// ------------------------------------------------------------------ import

function previewCsv(text: string): string[][] {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .slice(0, 11)
    .map((line) => line.split(',').map((cell) => cell.trim().replace(/^"|"$/g, '')));
}

/** Upload an xlsx / csv file. CSV files are previewed first; error rows are listed after saving. */
export function ImportDialog({
  open,
  onClose,
  title,
  columns,
  upload,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  columns: string;
  upload: (file: File) => Promise<ImportResult>;
}) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string[][] | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    if (open) return;
    setFile(null);
    setPreview(null);
    setResult(null);
  }, [open]);

  const choose = async (f: File | null) => {
    setFile(f);
    setResult(null);
    setPreview(null);
    if (f && f.name.toLowerCase().endsWith('.csv')) {
      try {
        setPreview(previewCsv(await f.text()));
      } catch {
        toast.error('Could not read that file');
      }
    }
  };

  const run = useAction((f: File) => upload(f), {
    success: (r) => `${r.created} row${r.created === 1 ? '' : 's'} created`,
    onSuccess: setResult,
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{result ? 'Close' : 'Cancel'}</Button>
          {!result && (
            <Button loading={run.isPending} disabled={!file} onClick={() => file && run.mutate(file)}>
              Import
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-xs text-slate-600">
          <span className="font-medium">Columns (first row):</span> {columns}
        </p>
        <input
          type="file"
          accept=".xlsx,.csv"
          onChange={(e) => choose(e.target.files?.[0] ?? null)}
          className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-indigo-700"
        />
        {file && !preview && !result && (
          <p className="text-xs text-slate-500">{file.name} — Excel files are checked by the server when you import.</p>
        )}
        {preview && !result && (
          <div>
            <p className="mb-1 text-xs font-medium text-slate-600">Preview (first {Math.max(preview.length - 1, 0)} rows)</p>
            <div className="max-h-64 overflow-auto rounded-md border border-slate-200">
              <table className="min-w-full text-xs">
                <tbody>
                  {preview.map((row, i) => (
                    <tr key={i} className={i === 0 ? 'bg-slate-50 font-semibold' : 'border-t border-slate-100'}>
                      {row.map((cell, j) => (
                        <td key={j} className="whitespace-nowrap px-2 py-1">{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {result && (
          <>
            <Alert tone={result.errors.length ? 'amber' : 'green'}>
              {result.created} created{result.errors.length ? `, ${result.errors.length} row(s) with problems` : ' — no problems'}.
            </Alert>
            {result.errors.length > 0 && (
              <div className="max-h-64 overflow-auto rounded-md border border-slate-200">
                <table className="min-w-full text-xs">
                  <thead className="bg-slate-50 text-left">
                    <tr><th className="px-2 py-1">Row</th><th className="px-2 py-1">Problem</th></tr>
                  </thead>
                  <tbody>
                    {result.errors.map((err, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="px-2 py-1">{err.row}</td>
                        <td className="px-2 py-1 text-red-700">{err.error}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
