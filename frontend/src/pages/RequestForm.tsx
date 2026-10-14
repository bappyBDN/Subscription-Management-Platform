import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { z } from 'zod';

import { requestsApi } from '@/api/requests';
import { subscriptionsApi } from '@/api/subscriptions';
import { useAuth, useMe } from '@/auth/AuthProvider';
import { EmptyState, ErrorState, LoadingRows, MoneyText } from '@/components/shared';
import { Alert, Button, Card, Details, Field, Input, PageHeader, Select, Textarea, cn } from '@/components/ui';
import { useAction, useDebounced, useRequest, useVendors } from '@/hooks';
import { BILLING_CYCLES, CURRENCIES, DURATIONS, SEAT_REQUEST_TYPES } from '@/lib/constants';
import { label, money, num, todayIso } from '@/lib/format';
import type { Vendor } from '@/types';

const OTHER = 'other';

// v2: a seat request points at a subscription the requester's SBU, department or function owns;
// a tool they do not have yet is raised as a proposal by a head or manager.
const schema = z
  .object({
    kind: z.enum(['seat', 'proposal']),
    // seat
    subscription_id: z.string(),
    type: z.enum(['new', 'renewal', 'upgrade', 'cancel']),
    // proposal
    tool: z.string(),
    other_tool_name: z.string().trim().max(100, 'Keep the name under 100 characters'),
    other_tool_url: z.string().trim().max(255, 'Keep the URL under 255 characters'),
    plan_name: z.string().trim().max(100, 'Keep the plan under 100 characters'),
    owner_scope: z.enum(['department', 'function', 'unit']),
    est_cost_per_cycle: z.string(),
    est_currency: z.string(),
    est_billing_cycle: z.string(),
    // both
    seats: z.number({ invalid_type_error: 'Enter the number of seats' }).int().min(1, 'At least 1 seat').max(100, 'At most 100 seats'),
    duration: z.enum(['1', '3', '6', '12', 'open']),
    needed_from: z.string().min(1, 'Choose the date you need it from'),
    reason: z.string().trim().min(30, 'Explain why in at least 30 characters'),
    expected_use: z.string().trim(),
  })
  .superRefine((v, ctx) => {
    if (v.kind === 'seat') {
      if (!v.subscription_id) ctx.addIssue({ code: 'custom', path: ['subscription_id'], message: 'Choose a subscription' });
      return;
    }
    if (!v.tool) ctx.addIssue({ code: 'custom', path: ['tool'], message: 'Choose a tool' });
    if (v.tool === OTHER && !v.other_tool_name) {
      ctx.addIssue({ code: 'custom', path: ['other_tool_name'], message: 'Enter the name of the tool' });
    }
    if (!v.plan_name) ctx.addIssue({ code: 'custom', path: ['plan_name'], message: 'Enter the plan you propose' });
    if (v.est_cost_per_cycle && !(Number(v.est_cost_per_cycle) >= 0)) {
      ctx.addIssue({ code: 'custom', path: ['est_cost_per_cycle'], message: 'Enter a valid cost' });
    }
  });
type FormValues = z.infer<typeof schema>;

/** Searchable tool select: filter box + list, with "Other" at the end */
function ToolPicker({ vendors, value, onChange }: { vendors: Vendor[]; value: string; onChange: (value: string) => void }) {
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
        placeholder="Search tools…"
        value={open ? text : selected}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
      />
      {open && (
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
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const params = useParams();
  const [search] = useSearchParams();
  const editId = params.id ? Number(params.id) : null;

  const vendors = useVendors();
  const available = useQuery({ queryKey: ['available-subscriptions'], queryFn: subscriptionsApi.available });
  const existing = useRequest(editId ?? NaN);

  const wantedType = search.get('type') ?? '';
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      kind: wantedType === 'proposal' && me.can_propose ? 'proposal' : 'seat',
      subscription_id: search.get('subscription_id') ?? '',
      type: (SEAT_REQUEST_TYPES.includes(wantedType) ? wantedType : 'new') as FormValues['type'],
      tool: '',
      other_tool_name: '',
      other_tool_url: '',
      plan_name: '',
      owner_scope: me.function_id ? 'function' : me.department_id ? 'department' : 'unit',
      est_cost_per_cycle: '',
      est_currency: 'USD',
      est_billing_cycle: 'monthly',
      seats: 1,
      duration: '12',
      needed_from: todayIso(),
      reason: '',
      expected_use: '',
    },
  });
  const { register, handleSubmit, watch, setValue, reset, formState } = form;
  const errors = formState.errors;
  const v = watch();
  const isProposal = v.kind === 'proposal';

  // Edit mode: load the request being corrected
  useEffect(() => {
    const r = existing.data;
    if (!r) return;
    reset({
      kind: r.type === 'proposal' ? 'proposal' : 'seat',
      subscription_id: r.subscription_id ? String(r.subscription_id) : '',
      type: (SEAT_REQUEST_TYPES.includes(r.type) ? r.type : 'new') as FormValues['type'],
      tool: r.vendor_id ? String(r.vendor_id) : OTHER,
      other_tool_name: r.vendor_id ? '' : r.tool_name,
      other_tool_url: r.other_tool_url ?? '',
      plan_name: r.plan_name,
      owner_scope: r.owner_scope === 'unit' ? 'unit' : r.owner_scope === 'function' ? 'function' : 'department',
      est_cost_per_cycle: '',
      est_currency: r.est_currency ?? 'USD',
      est_billing_cycle: r.est_billing_cycle ?? 'monthly',
      seats: r.seats,
      duration: (r.duration_months ? String(r.duration_months) : 'open') as FormValues['duration'],
      needed_from: r.needed_from,
      reason: r.reason,
      expected_use: r.expected_use ?? '',
    });
  }, [existing.data, reset]);

  // ---- seat request: subscriptions my SBU / department / function owns
  const holding = v.type !== 'new';
  const options = useMemo(
    () => (available.data ?? []).filter((s) => s.already_holding === holding),
    [available.data, holding],
  );
  const chosen = available.data?.find((s) => String(s.subscription_id) === v.subscription_id);

  // ---- proposal: catalogue + live estimate
  const vendor = vendors.data?.find((x) => String(x.id) === v.tool);
  const vendorId = vendor?.id ?? null;
  const inCatalogue = !!vendor?.plans.some((p) => p.plan_name.toLowerCase() === v.plan_name.trim().toLowerCase());
  const showCost = isProposal && (v.tool === OTHER || (!!vendor && !!v.plan_name.trim() && !inCatalogue));
  const seats = Number.isFinite(v.seats) && v.seats > 0 ? v.seats : 1;

  const estimateInput = useDebounced(
    useMemo(
      () => ({
        vendor_id: vendorId,
        plan_name: v.plan_name.trim() || null,
        seats,
        ...(showCost && v.est_cost_per_cycle !== '' && Number(v.est_cost_per_cycle) >= 0
          ? { est_cost_per_cycle: v.est_cost_per_cycle, est_currency: v.est_currency, est_billing_cycle: v.est_billing_cycle }
          : {}),
      }),
      [vendorId, v.plan_name, seats, showCost, v.est_cost_per_cycle, v.est_currency, v.est_billing_cycle],
    ),
    400,
  );
  const estimate = useQuery({
    queryKey: ['estimate', estimateInput],
    queryFn: () => requestsApi.estimate(estimateInput),
    enabled: isProposal && (!!estimateInput.plan_name || 'est_cost_per_cycle' in estimateInput),
  });

  const submit = useAction(
    async (f: FormValues) => {
      const common = {
        seats: f.seats,
        duration_months: f.duration === 'open' ? null : Number(f.duration),
        needed_from: f.needed_from,
        reason: f.reason,
        expected_use: f.expected_use || null,
      };
      const isOther = f.tool === OTHER;
      const proposal = {
        vendor_id: isOther ? null : Number(f.tool),
        other_tool_name: isOther ? f.other_tool_name : null,
        other_tool_url: isOther && f.other_tool_url ? f.other_tool_url : null,
        plan_name: f.plan_name,
        ...(showCost && f.est_cost_per_cycle !== ''
          ? { est_cost_per_cycle: f.est_cost_per_cycle, est_currency: f.est_currency, est_billing_cycle: f.est_billing_cycle }
          : {}),
      };
      if (editId) {
        await requestsApi.update(editId, f.kind === 'proposal' ? { ...common, ...proposal } : common);
        return requestsApi.resubmit(editId);
      }
      if (f.kind === 'proposal') {
        return requestsApi.create({ ...common, ...proposal, type: 'proposal', owner_scope: f.owner_scope });
      }
      return requestsApi.create({ ...common, type: f.type, subscription_id: Number(f.subscription_id) });
    },
    {
      success: (r) => (editId ? `${r.req_no} resubmitted` : `${r.type === 'proposal' ? 'Proposal' : 'Request'} ${r.req_no} submitted`),
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
  const canProposeUnit = isAdmin || me.heads_unit_ids.includes(me.unit_id);
  const monthly = chosen ? num(chosen.monthly_bdt_per_seat) * seats : 0;

  return (
    <form onSubmit={handleSubmit((f) => submit.mutate(f))} noValidate>
      <PageHeader
        title={editId ? `Edit ${existing.data?.req_no ?? 'request'}` : 'New request'}
        subtitle={editId ? 'Update the details that were asked for, then resubmit.' : 'Ask for a seat on a tool your SBU, department or function already has, or propose a new one.'}
      />

      {!editId && me.can_propose && (
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {([
            ['seat', 'A seat on an existing subscription', `One of the tools ${me.department ?? me.unit} already pays for.`],
            ['proposal', 'Propose a new tool', 'A tool your function, department or SBU does not have yet.'],
          ] as const).map(([id, title, hint]) => (
            <button
              key={id}
              type="button"
              aria-pressed={v.kind === id}
              onClick={() => setValue('kind', id, { shouldValidate: formState.isSubmitted })}
              className={cn(
                'rounded-lg border p-3 text-left',
                v.kind === id ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500' : 'border-slate-200 bg-white hover:border-slate-300',
              )}
            >
              <span className="block text-sm font-semibold text-slate-900">{title}</span>
              <span className="block text-xs text-slate-600">{hint}</span>
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="1 · Your details">
            <Details
              items={[
                ['Name', me.name],
                ['Employee ID', me.emp_code],
                ['Designation', me.designation ?? '—'],
                ['SBU', me.unit],
                ['Department', me.department ?? '—'],
                ['Team', me.team ?? '—'],
                ['Reporting manager', me.manager ? `${me.manager.name} (${me.manager.emp_code})` : 'None — goes straight to DMD Sir'],
              ]}
            />
          </Card>

          <Card title="2 · What you need">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {!isProposal ? (
                <>
                  <Field label="Request type">
                    <Select disabled={!!editId} {...register('type', { onChange: () => setValue('subscription_id', '') })}>
                      {SEAT_REQUEST_TYPES.map((t) => <option key={t} value={t}>{t === 'new' ? 'New seat' : label(t)}</option>)}
                    </Select>
                  </Field>
                  <Field label="Seats" error={errors.seats?.message}>
                    <Input type="number" min={1} max={100} {...register('seats', { valueAsNumber: true })} />
                  </Field>
                  <Field label="Subscription" required error={errors.subscription_id?.message} className="sm:col-span-2"
                    hint={holding ? 'Subscriptions you currently hold a seat on.' : `Subscriptions owned by your SBU (${me.unit})${me.department ? `, your department (${me.department})` : ''} or your function.`}>
                    {editId ? (
                      <Input disabled value={`${existing.data?.tool_name ?? ''} ${existing.data?.plan_name ?? ''}`} />
                    ) : (
                      <Select disabled={available.isLoading} {...register('subscription_id')}>
                        <option value="">{available.isLoading ? 'Loading…' : 'Choose…'}</option>
                        {options.map((s) => (
                          <option key={s.subscription_id} value={s.subscription_id}>
                            {s.vendor_name} {s.plan_name} · {s.owner_label} · {s.seats_free} of {s.seats_total} seats free
                          </option>
                        ))}
                      </Select>
                    )}
                  </Field>
                  {available.error ? (
                    <div className="sm:col-span-2">
                      <Alert tone="red">Could not load the subscriptions. <button type="button" className="underline" onClick={() => available.refetch()}>Try again</button></Alert>
                    </div>
                  ) : null}
                  {!editId && available.data && options.length === 0 && (
                    <div className="sm:col-span-2">
                      <Alert tone="amber">
                        {holding
                          ? 'You do not hold a seat on any subscription yet, so there is nothing to renew, upgrade or cancel.'
                          : `There is no subscription available to you that you do not already hold. ${me.can_propose ? 'Propose a new tool above.' : 'Ask your manager or department head to propose the tool you need.'}`}
                      </Alert>
                    </div>
                  )}
                  {chosen && !holding && chosen.seats_free < seats && (
                    <div className="sm:col-span-2">
                      <Alert tone="amber">This subscription has {chosen.seats_free} free seat(s). DMD Sir&apos;s office will have to add seats before access can be handed over.</Alert>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <Field label="Tool" required error={errors.tool?.message} className="sm:col-span-2">
                    {vendors.isLoading ? (
                      <Input disabled placeholder="Loading tools…" />
                    ) : vendors.error ? (
                      <Alert tone="red">Could not load the tool list. <button type="button" className="underline" onClick={() => vendors.refetch()}>Try again</button></Alert>
                    ) : (
                      <ToolPicker vendors={vendors.data ?? []} value={v.tool} onChange={(value) => setValue('tool', value, { shouldValidate: true })} />
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
                  <Field label="Plan" required error={errors.plan_name?.message} hint={vendor?.plans.length ? 'Pick a plan or type another one' : undefined}>
                    <Input list="plan-options" {...register('plan_name')} />
                    <datalist id="plan-options">
                      {vendor?.plans.map((p) => (
                        <option key={p.id} value={p.plan_name}>{`${p.currency} ${p.default_cost} / ${label(p.billing_cycle).toLowerCase()}`}</option>
                      ))}
                    </datalist>
                  </Field>
                  <Field label="Seats" error={errors.seats?.message}>
                    <Input type="number" min={1} max={100} {...register('seats', { valueAsNumber: true })} />
                  </Field>
                  <Field label="Who is it for" className="sm:col-span-2" hint="Only the SBU head can propose a tool for the whole SBU.">
                    <Select disabled={!!editId} {...register('owner_scope')}>
                      <option value="function" disabled={!me.function_id}>My function{me.function_id ? '' : ' — you are not linked to one'}</option>
                      <option value="department" disabled={!me.department_id}>My department{me.department ? ` (${me.department})` : ' — you are not linked to one'}</option>
                      <option value="unit" disabled={!canProposeUnit}>The whole SBU ({me.unit})</option>
                    </Select>
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
                </>
              )}

              <Field label="Duration">
                <Select {...register('duration')}>
                  {DURATIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </Select>
              </Field>
              <Field label="Needed from" required error={errors.needed_from?.message}>
                <Input type="date" {...register('needed_from')} />
              </Field>
            </div>
          </Card>

          <Card title="3 · Why">
            <div className="space-y-3">
              <Field label="Reason" required error={errors.reason?.message}>
                <Textarea rows={4} placeholder="What work needs this tool, and why the free options are not enough" {...register('reason')} />
              </Field>
              <p className={cn('-mt-2 text-xs', reasonLength >= 30 ? 'text-emerald-700' : 'text-slate-500')}>
                {reasonLength} / 30 characters minimum
              </p>
              <Field label="Expected use">
                <Textarea rows={2} placeholder="How often and for which projects" {...register('expected_use')} />
              </Field>
            </div>
          </Card>
        </div>

        <div className="lg:col-span-1">
          <div className="space-y-4 lg:sticky lg:top-20">
            <Card title="4 · Cost preview">
              {!isProposal ? (
                chosen ? (
                  <dl className="space-y-3 text-sm">
                    <div className="flex items-baseline justify-between gap-2">
                      <dt className="text-slate-500">Monthly</dt>
                      <dd><MoneyText amount={monthly} estimated className="text-lg font-semibold text-slate-900" /></dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-2 border-t border-slate-100 pt-3">
                      <dt className="text-slate-500">Yearly</dt>
                      <dd><MoneyText amount={monthly * 12} estimated className="text-lg font-semibold text-slate-900" /></dd>
                    </div>
                    <p className="text-xs text-slate-500">
                      {money(chosen.cost_per_seat, chosen.currency)} per seat / {label(chosen.billing_cycle).toLowerCase()} · {seats} seat(s) · owned by {chosen.owner_label}
                    </p>
                  </dl>
                ) : (
                  <p className="text-sm text-slate-500">
                    {editId ? 'The cost is shown on the request.' : 'Choose a subscription to see the cost of a seat.'}
                  </p>
                )
              ) : estimate.isFetching && !estimate.data ? (
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
                    {estimate.data.source === 'catalogue' ? 'Catalogue price' : 'Your entered cost'} · {seats} seat(s)
                    {estimate.data.currency !== 'BDT' && <> · 1 {estimate.data.currency} = ৳ {String(estimate.data.fx_rate)}</>}
                  </p>
                </dl>
              )}
            </Card>
            <div className="flex gap-2">
              <Button type="submit" className="flex-1" loading={submit.isPending}>
                {editId ? 'Save and resubmit' : isProposal ? 'Submit proposal' : 'Submit request'}
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
