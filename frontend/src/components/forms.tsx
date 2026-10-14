import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';

import { settingsApi } from '@/api/masters';
import { chargesApi, subscriptionsApi } from '@/api/subscriptions';
import { useAction, useCards, useTeams, useUnits, useVendors } from '@/hooks';
import { BILLING_CYCLES, CURRENCIES, SUBSCRIPTION_STATUSES, SUBSCRIPTION_TYPES } from '@/lib/constants';
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
  seats_unnamed: number;
  cost_per_cycle: string;
  currency: string;
  billing_cycle: string;
  start_date: string;
  next_renewal_date: string;
  card_id: string;
  account_email: string;
  owner_scope: string;
  unit_id: string;
  department_id: string;
  function_id: string;
  team_id: string;
  usage_provider: string;
  status: string;
  notes: string;
}

/** A department or function sharing a subscription, as picked in the form (ids as strings, '' = none) */
interface ShareRow {
  department_id: string;
  function_id: string;
}

function Section({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="border-b border-slate-200 pb-1 pt-2 sm:col-span-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  );
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
  const toast = useToast();
  const vendors = useVendors(true);
  const cards = useCards();
  const units = useUnits();
  const teams = useTeams();
  const form = useForm<SubForm>();
  const { register, handleSubmit, reset, watch, setValue, formState } = form;
  const [shares, setShares] = useState<ShareRow[]>([]);
  const scope = watch('owner_scope');
  const unitId = watch('unit_id');
  const departmentId = watch('department_id');
  const functionId = watch('function_id');
  const teamId = watch('team_id');
  const type = watch('type');
  const billingCycle = watch('billing_cycle');
  const usageProvider = watch('usage_provider');
  const seatsUnnamed = watch('seats_unnamed');

  const departments = units.data?.find((u) => String(u.id) === unitId)?.departments.filter((d) => d.active) ?? [];
  const functions = departments.find((d) => String(d.id) === departmentId)?.functions?.filter((f) => f.active) ?? [];
  const unitTeams = teams.data?.filter((t) => String(t.unit_id) === unitId) ?? [];
  // every department of every SBU, for picking sharers
  const allDepartments = useMemo(
    () => (units.data ?? []).flatMap((u) => u.departments.filter((d) => d.active).map((d) => ({ ...d, unit_code: u.code }))),
    [units.data],
  );

  useEffect(() => {
    if (!open) return;
    const s = subscription;
    reset({
      vendor_id: s ? String(s.vendor_id) : '',
      plan_name: s?.plan_name ?? '',
      type: s?.type ?? 'individual',
      seats_total: s?.seats_total ?? 1,
      seats_unnamed: s?.seats_unnamed ?? 0,
      cost_per_cycle: s ? String(s.cost_per_cycle) : '',
      currency: s?.currency ?? 'USD',
      billing_cycle: s?.billing_cycle ?? 'monthly',
      start_date: s?.start_date ?? todayIso(),
      next_renewal_date: s?.next_renewal_date ?? '',
      card_id: s?.card_id ? String(s.card_id) : '',
      account_email: s?.account_email ?? '',
      owner_scope: s?.owner_scope ?? 'unit',
      unit_id: s ? String(s.unit_id) : '',
      department_id: s?.department_id ? String(s.department_id) : '',
      function_id: s?.function_id ? String(s.function_id) : '',
      team_id: s?.team_id ? String(s.team_id) : '',
      usage_provider: s?.usage_provider ?? '',
      status: s?.status ?? 'active',
      notes: s?.notes ?? '',
      ...(s ? {} : defaults),
    });
    const existing = (s?.shares ?? []).map((x) => ({ department_id: String(x.department_id), function_id: x.function_id ? String(x.function_id) : '' }));
    setShares(existing.length ? existing : [{ department_id: '', function_id: '' }, { department_id: '', function_id: '' }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, subscription?.id, units.data, teams.data]);

  const setShare = (i: number, patch: Partial<ShareRow>) => setShares((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const save = useAction(
    (v: SubForm) => {
      const picked = shares.filter((r) => r.department_id);
      const body: Record<string, unknown> = {
        plan_name: v.plan_name.trim(),
        type: v.type,
        seats_total: Number(v.seats_total),
        seats_unnamed: v.team_id ? Number(v.seats_unnamed) || 0 : 0,
        cost_per_cycle: v.cost_per_cycle,
        currency: v.currency,
        billing_cycle: v.billing_cycle,
        start_date: v.start_date,
        next_renewal_date: orNull(v.next_renewal_date),
        card_id: v.card_id ? Number(v.card_id) : null,
        account_email: orNull(v.account_email.trim()),
        owner_scope: v.owner_scope,
        unit_id: Number(v.unit_id),
        department_id: (v.owner_scope === 'department' || v.owner_scope === 'function') && v.department_id ? Number(v.department_id) : null,
        function_id: v.owner_scope === 'function' && v.function_id ? Number(v.function_id) : null,
        shares: v.owner_scope === 'shared'
          ? picked.map((r) => ({ department_id: Number(r.department_id), function_id: r.function_id ? Number(r.function_id) : null }))
          : [],
        team_id: v.team_id ? Number(v.team_id) : null,
        usage_provider: orNull(v.usage_provider),
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

  const submit = handleSubmit((v) => {
    if (v.owner_scope === 'shared') {
      const picked = shares.filter((r) => r.department_id);
      const keys = picked.map((r) => `${r.department_id}/${r.function_id}`);
      if (picked.length < 2) return toast.error('A shared subscription needs at least two departments or functions');
      if (new Set(keys).size !== keys.length) return toast.error('The same department / function is listed twice');
    }
    save.mutate(v);
  });

  const showMetering = type === 'api_credit' || billingCycle === 'usage' || !!usageProvider;
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
          <Button loading={save.isPending} onClick={submit}>Save</Button>
        </>
      }
    >
      <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={(ev) => ev.preventDefault()}>
        <Section title="1 · Tool & plan" />
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
        {subscription ? (
          <Field label="Status">
            <Select {...register('status')}>
              {SUBSCRIPTION_STATUSES.filter((s) => s !== 'cancelled' || subscription.status === 'cancelled').map((s) => (
                <option key={s} value={s}>{label(s)}</option>
              ))}
            </Select>
          </Field>
        ) : <div className="hidden sm:block" />}

        <Section title="2 · Owner" hint="Decides who may request a seat and who carries the cost." />
        <Field label="SBU" required error={e.unit_id?.message}>
          <Select {...register('unit_id', { required: 'Choose the SBU', onChange: () => { setValue('department_id', ''); setValue('function_id', ''); setValue('team_id', ''); } })}>
            <option value="">Choose…</option>
            {units.data?.map((u) => <option key={u.id} value={u.id}>{u.code} — {u.name}</option>)}
          </Select>
        </Field>
        <Field label="Who owns it">
          <Select {...register('owner_scope')}>
            <option value="unit">Whole SBU</option>
            <option value="department">One department</option>
            <option value="function">One function</option>
            <option value="shared">Shared by several departments / functions</option>
          </Select>
        </Field>
        {(scope === 'department' || scope === 'function') && (
          <Field label="Department" required error={e.department_id?.message}>
            <Select
              value={departmentId ?? ''}
              {...register('department_id', {
                validate: (val) => (scope !== 'department' && scope !== 'function') || !!val || 'Choose the department',
                onChange: () => setValue('function_id', ''),
              })}
            >
              <option value="">{unitId ? 'Choose…' : 'Choose the SBU first'}</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          </Field>
        )}
        {scope === 'function' && (
          <Field label="Function" required error={e.function_id?.message}>
            <Select value={functionId ?? ''} {...register('function_id', { validate: (val) => scope !== 'function' || !!val || 'Choose the function' })}>
              <option value="">{departmentId ? 'Choose…' : 'Choose the department first'}</option>
              {functions.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </Select>
          </Field>
        )}
        {scope === 'shared' && (
          <div className="space-y-2 sm:col-span-2">
            <p className="text-xs text-slate-600">
              Shared by these departments / functions (any SBU). Each pays for the seats its own people hold; empty seats are split equally.
            </p>
            {shares.map((row, i) => {
              const dept = allDepartments.find((d) => String(d.id) === row.department_id);
              const fns = (dept?.functions ?? []).filter((f) => f.active || String(f.id) === row.function_id);
              return (
                <div key={i} className="flex flex-wrap items-end gap-2">
                  <Field label={i === 0 ? 'SBU / Department' : ''} className="min-w-[12rem] flex-1">
                    <Select value={row.department_id} onChange={(ev) => setShare(i, { department_id: ev.target.value, function_id: '' })}>
                      <option value="">Choose…</option>
                      {allDepartments.map((d) => <option key={d.id} value={d.id}>{d.unit_code} / {d.name}</option>)}
                    </Select>
                  </Field>
                  <Field label={i === 0 ? 'Function (optional)' : ''} className="min-w-[10rem] flex-1">
                    <Select value={row.function_id} disabled={!row.department_id} onChange={(ev) => setShare(i, { function_id: ev.target.value })}>
                      <option value="">Whole department</option>
                      {fns.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                    </Select>
                  </Field>
                  <Button
                    variant="ghost"
                    className="text-red-700 hover:bg-red-50"
                    disabled={shares.length <= 2}
                    onClick={() => setShares((rows) => rows.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </div>
              );
            })}
            <Button size="sm" variant="secondary" onClick={() => setShares((rows) => [...rows, { department_id: '', function_id: '' }])}>
              Add department / function
            </Button>
          </div>
        )}
        <Field label="Team (optional)" hint="Only when one team uses and pays for it: only its members may request it.">
          <Select value={teamId ?? ''} {...register('team_id')}>
            <option value="">{unitId ? 'No team' : 'Choose the SBU first'}</option>
            {unitTeams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
        {teamId || num(seatsUnnamed) > 0 ? (
          <Field label="Seats in use (holders not named)" hint="Seats the team already uses without a named holder.">
            <Input type="number" min={0} {...register('seats_unnamed', { min: { value: 0, message: 'Cannot be negative' } })} />
          </Field>
        ) : <div className="hidden sm:block" />}

        <Section title="3 · Billing" />
        <Field label="Seats bought" error={e.seats_total?.message}>
          <Input type="number" min={1} {...register('seats_total', { required: true, min: { value: 1, message: 'At least 1 seat' } })} />
        </Field>
        <Field label="Cost per cycle" required error={e.cost_per_cycle?.message}>
          <Input type="number" step="0.01" min={0} {...register('cost_per_cycle', { required: 'Enter the cost' })} />
        </Field>
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
        <Field label="Bought with account (Gmail)" hint="The login the subscription was bought with." error={e.account_email?.message}>
          <Input type="email" placeholder="name@gmail.com" {...register('account_email', { pattern: { value: /^$|^[^@\s]+@[^@\s]+\.[^@\s]+$/, message: 'Enter a valid email' } })} />
        </Field>
        {showMetering && (
          <Field label="Usage metering" className="sm:col-span-2" hint="For pay-as-you-go API accounts: daily cost is read from the provider instead of card charges.">
            <Select {...register('usage_provider')}>
              <option value="">None — cost from card charges</option>
              <option value="deepseek">DeepSeek API balance</option>
            </Select>
          </Field>
        )}

        <Section title="4 · Notes" />
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
