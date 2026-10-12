import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

import { requestsApi } from '@/api/requests';
import { subscriptionsApi } from '@/api/subscriptions';
import { useMe } from '@/auth/AuthProvider';
import { EmptyState, ErrorState, LoadingRows, MoneyText } from '@/components/shared';
import { Alert, Button, Card, Details, Field, Input, PageHeader, Select, Textarea, cn } from '@/components/ui';
import { useAction, useDebounced, useMySubscriptions, useRequest, useVendors } from '@/hooks';
import { BILLING_CYCLES, CURRENCIES, DURATIONS, REQUEST_TYPES } from '@/lib/constants';
import { label, todayIso } from '@/lib/format';
import type { Vendor } from '@/types';

const OTHER = 'other';

const schema = z
  .object({
    tool: z.string().min(1, 'Choose a tool'),
    other_tool_name: z.string().trim().max(100, 'Keep the name under 100 characters'),
    other_tool_url: z.string().trim().max(255, 'Keep the URL under 255 characters'),
    plan_name: z.string().trim().min(1, 'Enter the plan').max(100, 'Keep the plan under 100 characters'),
    type: z.enum(['new', 'renewal', 'upgrade', 'cancel']),
    seats: z.number({ invalid_type_error: 'Enter the number of seats' }).int().min(1, 'At least 1 seat').max(100, 'At most 100 seats'),
    duration: z.enum(['1', '3', '6', '12', 'open']),
    needed_from: z.string().min(1, 'Choose the date you need it from'),
    reason: z.string().trim().min(30, 'Explain why in at least 30 characters'),
    expected_use: z.string().trim(),
    use_shared_seat: z.boolean(),
    subscription_id: z.string(),
    est_cost_per_cycle: z.string(),
    est_currency: z.string(),
    est_billing_cycle: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.tool === OTHER && !v.other_tool_name) {
      ctx.addIssue({ code: 'custom', path: ['other_tool_name'], message: 'Enter the name of the tool' });
    }
    if (v.type !== 'new' && !v.subscription_id) {
      ctx.addIssue({ code: 'custom', path: ['subscription_id'], message: `Choose the subscription this ${v.type} is for` });
    }
    if (v.est_cost_per_cycle && !(Number(v.est_cost_per_cycle) >= 0)) {
      ctx.addIssue({ code: 'custom', path: ['est_cost_per_cycle'], message: 'Enter a valid cost' });
    }
  });
type FormValues = z.infer<typeof schema>;

/** Searchable tool select: filter box + list, with "Other" at the end */
function ToolPicker({ vendors, value, onChange, disabled }: {
  vendors: Vendor[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const selected = value === OTHER ? 'Other (not in the list)' : vendors.find((v) => String(v.id) === value)?.name ?? '';
  const matches = vendors.filter((v) => v.name.toLowerCase().includes(text.trim().toLowerCase()));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
    setText('');
  };

  return (
    <div className="relative" ref={ref}>
      <Input
        role="combobox"
        aria-expanded={open}
        aria-label="Tool"
        disabled={disabled}
        placeholder="Search tools…"
        value={open ? text : selected}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
      />
      {open && !disabled && (
        <ul role="listbox" className="absolute z-20 mt-1 max-h-60 w-full overflow-y-auto rounded-md border border-slate-200 bg-white text-sm shadow-lg">
          {matches.map((v) => (
            <li key={v.id}>
              <button type="button" role="option" aria-selected={String(v.id) === value} onClick={() => pick(String(v.id))}
                className={cn('flex w-full items-center justify-between px-3 py-2 text-left hover:bg-indigo-50', String(v.id) === value && 'bg-indigo-50 font-medium')}>
                {v.name}
                <span className="text-xs text-slate-400">{label(v.category)}</span>
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="px-3 py-2 text-slate-500">No tool matches “{text}”</li>}
          <li className="border-t border-slate-100">
            <button type="button" role="option" aria-selected={value === OTHER} onClick={() => pick(OTHER)} className="block w-full px-3 py-2 text-left text-indigo-700 hover:bg-indigo-50">
              Other — a tool that is not in the list
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}

export default function RequestForm() {
  const me = useMe();
  const navigate = useNavigate();
  const params = useParams();
  const [search] = useSearchParams();
  const editId = params.id ? Number(params.id) : null;

  const vendors = useVendors();
  const mySubs = useMySubscriptions();
  const existing = useRequest(editId ?? NaN);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      tool: '',
      other_tool_name: '',
      other_tool_url: '',
      plan_name: search.get('plan') ?? '',
      type: (REQUEST_TYPES.includes(search.get('type') ?? '') ? search.get('type') : 'new') as FormValues['type'],
      seats: 1,
      duration: '12',
      needed_from: todayIso(),
      reason: '',
      expected_use: '',
      use_shared_seat: false,
      subscription_id: search.get('subscription_id') ?? '',
      est_cost_per_cycle: '',
      est_currency: 'USD',
      est_billing_cycle: 'monthly',
    },
  });
  const { register, handleSubmit, watch, setValue, reset, formState } = form;
  const errors = formState.errors;
  const v = watch();

  // Prefill the tool from ?tool=<name> (renewal / cancel links from "My subscriptions")
  const prefilled = useRef(false);
  useEffect(() => {
    const toolName = search.get('tool');
    if (prefilled.current || editId || !toolName || !vendors.data) return;
    prefilled.current = true;
    const match = vendors.data.find((x) => x.name.toLowerCase() === toolName.toLowerCase());
    if (match) setValue('tool', String(match.id));
    else {
      setValue('tool', OTHER);
      setValue('other_tool_name', toolName);
    }
  }, [search, vendors.data, editId, setValue]);

  // Edit mode: load the request being corrected
  useEffect(() => {
    const r = existing.data;
    if (!r) return;
    reset({
      tool: r.vendor_id ? String(r.vendor_id) : OTHER,
      other_tool_name: r.vendor_id ? '' : r.tool_name,
      other_tool_url: r.other_tool_url ?? '',
      plan_name: r.plan_name,
      type: r.type as FormValues['type'],
      seats: r.seats,
      duration: (r.duration_months ? String(r.duration_months) : 'open') as FormValues['duration'],
      needed_from: r.needed_from,
      reason: r.reason,
      expected_use: r.expected_use ?? '',
      use_shared_seat: r.use_shared_seat,
      subscription_id: r.subscription_id ? String(r.subscription_id) : '',
      est_cost_per_cycle: '',
      est_currency: r.est_currency ?? 'USD',
      est_billing_cycle: r.est_billing_cycle ?? 'monthly',
    });
  }, [existing.data, reset]);

  const vendor = vendors.data?.find((x) => String(x.id) === v.tool);
  const vendorId = vendor?.id ?? null;
  const inCatalogue = !!vendor?.plans.some((p) => p.plan_name.toLowerCase() === v.plan_name.trim().toLowerCase());
  const showCost = v.tool === OTHER || (!!vendor && !!v.plan_name.trim() && !inCatalogue && !v.use_shared_seat);

  // Free shared seats on this tool
  const shared = useQuery({
    queryKey: ['shared-seats', vendorId],
    queryFn: () => subscriptionsApi.sharedSeats(vendorId!),
    enabled: !!vendorId && v.type === 'new' && !editId,
  });
  const freeSeat = shared.data?.[0];

  // Live cost preview
  const estimateInput = useDebounced(
    useMemo(
      () => ({
        vendor_id: vendorId,
        plan_name: v.plan_name.trim() || null,
        seats: Number.isFinite(v.seats) && v.seats > 0 ? v.seats : 1,
        ...(showCost && v.est_cost_per_cycle !== '' && Number(v.est_cost_per_cycle) >= 0
          ? { est_cost_per_cycle: v.est_cost_per_cycle, est_currency: v.est_currency, est_billing_cycle: v.est_billing_cycle }
          : {}),
      }),
      [vendorId, v.plan_name, v.seats, showCost, v.est_cost_per_cycle, v.est_currency, v.est_billing_cycle],
    ),
    400,
  );
  const estimate = useQuery({
    queryKey: ['estimate', estimateInput],
    queryFn: () => requestsApi.estimate(estimateInput),
    enabled: !!estimateInput.plan_name || 'est_cost_per_cycle' in estimateInput,
  });

  const submit = useAction(
    async (f: FormValues) => {
      const isOther = f.tool === OTHER;
      const cost =
        showCost && f.est_cost_per_cycle !== ''
          ? { est_cost_per_cycle: f.est_cost_per_cycle, est_currency: f.est_currency, est_billing_cycle: f.est_billing_cycle }
          : {};
      const common = {
        vendor_id: isOther ? null : Number(f.tool),
        other_tool_name: isOther ? f.other_tool_name : null,
        other_tool_url: isOther && f.other_tool_url ? f.other_tool_url : null,
        plan_name: f.plan_name,
        seats: f.seats,
        duration_months: f.duration === 'open' ? null : Number(f.duration),
        needed_from: f.needed_from,
        reason: f.reason,
        expected_use: f.expected_use || null,
        use_shared_seat: f.use_shared_seat,
        ...cost,
      };
      if (editId) {
        await requestsApi.update(editId, common);
        return requestsApi.resubmit(editId);
      }
      return requestsApi.create({
        ...common,
        type: f.type,
        subscription_id: f.subscription_id ? Number(f.subscription_id) : null,
      });
    },
    {
      success: (r) => (editId ? `${r.req_no} resubmitted` : `Request ${r.req_no} submitted`),
      onSuccess: (r) => navigate(`/requests/${r.id}`),
    },
  );

  if (editId) {
    if (existing.isLoading) return <LoadingRows />;
    if (existing.error) return <ErrorState error={existing.error} onRetry={() => existing.refetch()} />;
    if (existing.data && !existing.data.allowed_actions.includes('resubmit')) {
      return (
        <EmptyState
          title="This request cannot be edited now"
          hint="A request can only be edited while more information is needed."
          action={<Link to={`/requests/${editId}`}><Button size="sm" variant="secondary">Back to the request</Button></Link>}
        />
      );
    }
  }

  const reasonLength = v.reason.trim().length;
  const needsSubscription = v.type !== 'new';

  return (
    <form onSubmit={handleSubmit((f) => submit.mutate(f))} noValidate>
      <PageHeader
        title={editId ? `Edit ${existing.data?.req_no ?? 'request'}` : 'New request'}
        subtitle={editId ? 'Update the details that were asked for, then resubmit.' : 'Ask for a paid tool. Your manager and DMD Sir will review it.'}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="1 · Your details">
            <Details
              items={[
                ['Name', me.name],
                ['Employee ID', me.emp_code],
                ['Designation', me.designation ?? '—'],
                ['Department', me.department ?? '—'],
                ['Team', me.team ?? '—'],
                ['Unit', me.unit],
                ['Reporting manager', me.manager ? `${me.manager.name} (${me.manager.emp_code})` : 'None — goes straight to DMD Sir'],
              ]}
            />
          </Card>

          <Card title="2 · What you need">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Tool" required error={errors.tool?.message} className="sm:col-span-2">
                {vendors.isLoading ? (
                  <Input disabled placeholder="Loading tools…" />
                ) : vendors.error ? (
                  <Alert tone="red">Could not load the tool list. <button type="button" className="underline" onClick={() => vendors.refetch()}>Try again</button></Alert>
                ) : (
                  <ToolPicker
                    vendors={vendors.data ?? []}
                    value={v.tool}
                    disabled={needsSubscription && !!v.subscription_id && !editId}
                    onChange={(value) => {
                      setValue('tool', value, { shouldValidate: true });
                      setValue('use_shared_seat', false);
                      if (!editId && v.type === 'new') setValue('subscription_id', '');
                    }}
                  />
                )}
              </Field>

              {v.tool === OTHER && (
                <>
                  <Field label="Tool name" required error={errors.other_tool_name?.message}>
                    <Input {...register('other_tool_name')} />
                  </Field>
                  <Field label="Website" error={errors.other_tool_url?.message}>
                    <Input type="url" placeholder="https://" {...register('other_tool_url')} />
                  </Field>
                </>
              )}

              {freeSeat && !v.use_shared_seat && (
                <div className="sm:col-span-2">
                  <Alert tone="blue">
                    There is a free seat on <strong>{freeSeat.vendor_name} {freeSeat.plan_name}</strong> ({freeSeat.seats_free} free).{' '}
                    <button
                      type="button"
                      className="font-semibold underline"
                      onClick={() => {
                        setValue('use_shared_seat', true);
                        setValue('subscription_id', String(freeSeat.subscription_id));
                        setValue('plan_name', freeSeat.plan_name, { shouldValidate: true });
                        setValue('seats', 1);
                      }}
                    >
                      Request the shared seat instead?
                    </button>
                  </Alert>
                </div>
              )}
              {v.use_shared_seat && (
                <div className="sm:col-span-2">
                  <Alert tone="green">
                    You are requesting a free seat on the existing subscription — no new purchase needed.{' '}
                    {!editId && (
                      <button type="button" className="font-semibold underline" onClick={() => { setValue('use_shared_seat', false); setValue('subscription_id', ''); }}>
                        Undo
                      </button>
                    )}
                  </Alert>
                </div>
              )}

              <Field label="Plan" required error={errors.plan_name?.message} hint={vendor?.plans.length ? 'Pick a plan or type another one' : undefined}>
                <Input list="plan-options" readOnly={v.use_shared_seat} {...register('plan_name')} />
                <datalist id="plan-options">
                  {vendor?.plans.map((p) => (
                    <option key={p.id} value={p.plan_name}>{`${p.currency} ${p.default_cost} / ${label(p.billing_cycle).toLowerCase()}`}</option>
                  ))}
                </datalist>
              </Field>
              <Field label="Request type">
                <Select disabled={!!editId} {...register('type')}>
                  {REQUEST_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
                </Select>
              </Field>

              {needsSubscription && (
                <Field label="Existing subscription" required error={errors.subscription_id?.message} className="sm:col-span-2">
                  <Select
                    disabled={!!editId}
                    {...register('subscription_id', {
                      onChange: (e) => {
                        const sub = mySubs.data?.active.find((s) => String(s.subscription_id) === e.target.value);
                        if (!sub) return;
                        const match = vendors.data?.find((x) => x.name === sub.vendor_name);
                        setValue('tool', match ? String(match.id) : OTHER, { shouldValidate: true });
                        if (!match) setValue('other_tool_name', sub.vendor_name);
                        setValue('plan_name', sub.plan_name, { shouldValidate: true });
                      },
                    })}
                  >
                    <option value="">Choose one of your subscriptions…</option>
                    {mySubs.data?.active.map((s) => (
                      <option key={s.assignment_id} value={s.subscription_id}>{s.vendor_name} {s.plan_name}</option>
                    ))}
                    {editId && v.subscription_id && !mySubs.data?.active.some((s) => String(s.subscription_id) === v.subscription_id) && (
                      <option value={v.subscription_id}>Subscription #{v.subscription_id}</option>
                    )}
                  </Select>
                </Field>
              )}

              <Field label="Seats" error={errors.seats?.message}>
                <Input type="number" min={1} max={100} readOnly={v.use_shared_seat} {...register('seats', { valueAsNumber: true })} />
              </Field>
              <Field label="Duration">
                <Select {...register('duration')}>
                  {DURATIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </Select>
              </Field>
              <Field label="Needed from" required error={errors.needed_from?.message}>
                <Input type="date" {...register('needed_from')} />
              </Field>

              {showCost && (
                <div className="grid grid-cols-1 gap-3 rounded-md bg-slate-50 p-3 sm:col-span-2 sm:grid-cols-3">
                  <p className="text-xs text-slate-600 sm:col-span-3">
                    This {v.tool === OTHER ? 'tool' : 'plan'} is not in the catalogue. Enter what it costs per seat so the approvers can see it
                    {editId ? ' (leave empty to keep the cost you entered before).' : '.'}
                  </p>
                  <Field label="Cost per cycle" error={errors.est_cost_per_cycle?.message}>
                    <Input type="number" step="0.01" min={0} {...register('est_cost_per_cycle')} />
                  </Field>
                  <Field label="Currency">
                    <Select {...register('est_currency')}>
                      {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                    </Select>
                  </Field>
                  <Field label="Billing cycle">
                    <Select {...register('est_billing_cycle')}>
                      {BILLING_CYCLES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
                    </Select>
                  </Field>
                </div>
              )}
            </div>
          </Card>

          <Card title="3 · Why">
            <div className="space-y-3">
              <Field
                label="Reason"
                required
                error={errors.reason?.message}
                hint={
                  <span className={reasonLength >= 30 ? 'text-emerald-700' : undefined}>
                    {reasonLength} / 30 characters minimum
                  </span>
                }
              >
                <Textarea rows={4} placeholder="What work needs this tool, and why the free options are not enough" {...register('reason')} />
              </Field>
              {errors.reason && <p className="-mt-2 text-xs text-slate-500">{reasonLength} / 30 characters minimum</p>}
              <Field label="Expected use">
                <Textarea rows={2} placeholder="How often and for which projects" {...register('expected_use')} />
              </Field>
            </div>
          </Card>
        </div>

        <div className="lg:col-span-1">
          <div className="space-y-4 lg:sticky lg:top-20">
            <Card title="4 · Cost preview">
              {estimate.isFetching && !estimate.data ? (
                <LoadingRows rows={2} />
              ) : estimate.error ? (
                <ErrorState error={estimate.error} onRetry={() => estimate.refetch()} />
              ) : !estimate.data || estimate.data.source === 'unknown' ? (
                <p className="text-sm text-slate-500">
                  {v.plan_name.trim() || v.tool === OTHER
                    ? 'No catalogue price for this — enter the cost to see an estimate.'
                    : 'Choose a tool and plan to see the cost.'}
                </p>
              ) : (
                <dl className="space-y-3 text-sm">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="text-slate-500">Monthly</dt>
                    <dd className="text-right">
                      <MoneyText amount={estimate.data.monthly_bdt} currency="BDT" estimated className="block text-lg font-semibold text-slate-900" />
                      {estimate.data.currency !== 'BDT' && <MoneyText amount={estimate.data.monthly_original} currency={estimate.data.currency} className="text-slate-500" />}
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-2 border-t border-slate-100 pt-3">
                    <dt className="text-slate-500">Yearly</dt>
                    <dd className="text-right">
                      <MoneyText amount={estimate.data.yearly_bdt} currency="BDT" estimated className="block text-lg font-semibold text-slate-900" />
                      {estimate.data.currency !== 'BDT' && <MoneyText amount={estimate.data.yearly_original} currency={estimate.data.currency} className="text-slate-500" />}
                    </dd>
                  </div>
                  <p className="text-xs text-slate-500">
                    {estimate.data.source === 'catalogue' ? 'Catalogue price' : 'Your entered cost'} · {v.seats || 1} seat(s)
                    {estimate.data.currency !== 'BDT' && <> · 1 {estimate.data.currency} = ৳ {String(estimate.data.fx_rate)}</>}
                  </p>
                </dl>
              )}
            </Card>
            <div className="flex gap-2">
              <Button type="submit" className="flex-1" loading={submit.isPending}>
                {editId ? 'Save and resubmit' : 'Submit request'}
              </Button>
              <Button variant="secondary" onClick={() => navigate(-1)}>Cancel</Button>
            </div>
            {formState.isSubmitted && Object.keys(errors).length > 0 && (
              <Alert tone="red">Some fields need your attention — see the messages above.</Alert>
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
