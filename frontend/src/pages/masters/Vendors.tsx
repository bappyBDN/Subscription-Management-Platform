import { useEffect, useState } from 'react';

import { vendorsApi } from '@/api/masters';
import { EmptyState, MoneyText, QueryState } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Badge, Button, Card, Checkbox, Dialog, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAction, useVendors } from '@/hooks';
import { BILLING_CYCLES, CURRENCIES, VENDOR_CATEGORIES } from '@/lib/constants';
import { label } from '@/lib/format';
import type { Vendor } from '@/types';

function VendorDialog({ open, onClose, vendor }: { open: boolean; onClose: () => void; vendor: Vendor | null }) {
  const toast = useToast();
  const [name, setName] = useState('');
  const [category, setCategory] = useState('ai');
  const [website, setWebsite] = useState('');
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setName(vendor?.name ?? '');
    setCategory(vendor?.category ?? 'ai');
    setWebsite(vendor?.website ?? '');
    setActive(vendor?.active ?? true);
  }, [open, vendor]);

  const save = useAction(
    () => {
      const body = { name: name.trim(), category, website: website.trim() || null, active };
      return vendor ? vendorsApi.update(vendor.id, body) : vendorsApi.create(body);
    },
    { success: vendor ? 'Tool updated' : 'Tool added', onSuccess: onClose },
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={vendor ? `Edit ${vendor.name}` : 'Add tool'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => (name.trim() ? save.mutate(undefined) : toast.error('Enter the tool name'))}>Save</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Name" required><Input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Category">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            {VENDOR_CATEGORIES.map((c) => <option key={c} value={c}>{c === 'ai' ? 'AI' : label(c)}</option>)}
          </Select>
        </Field>
        <Field label="Website"><Input type="url" placeholder="https://" value={website} onChange={(e) => setWebsite(e.target.value)} /></Field>
        <Checkbox label="Active — employees can request it" checked={active} onChange={(e) => setActive(e.target.checked)} />
      </div>
    </Dialog>
  );
}

function PlanDialog({ vendor, onClose }: { vendor: Vendor | null; onClose: () => void }) {
  const toast = useToast();
  const [plan, setPlan] = useState('');
  const [cost, setCost] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [cycle, setCycle] = useState('monthly');

  useEffect(() => {
    if (!vendor) return;
    setPlan('');
    setCost('');
  }, [vendor]);

  const add = useAction(
    () => vendorsApi.addPlan(vendor!.id, { plan_name: plan.trim(), default_cost: cost, currency, billing_cycle: cycle }),
    { success: 'Plan added', onSuccess: onClose },
  );
  const submit = () => {
    if (!plan.trim()) return toast.error('Enter the plan name');
    if (cost === '' || !(Number(cost) >= 0)) return toast.error('Enter the price per seat');
    add.mutate(undefined);
  };

  return (
    <Dialog
      open={!!vendor}
      onClose={onClose}
      title={`Add a plan · ${vendor?.name ?? ''}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={add.isPending} onClick={submit}>Add plan</Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Plan name" required className="col-span-2"><Input value={plan} onChange={(e) => setPlan(e.target.value)} placeholder="Pro, Team, Max…" /></Field>
        <Field label="Price per seat" required className="col-span-2"><Input type="number" step="0.01" min={0} value={cost} onChange={(e) => setCost(e.target.value)} /></Field>
        <Field label="Currency">
          <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</Select>
        </Field>
        <Field label="Billing cycle">
          <Select value={cycle} onChange={(e) => setCycle(e.target.value)}>{BILLING_CYCLES.map((c) => <option key={c} value={c}>{label(c)}</option>)}</Select>
        </Field>
      </div>
    </Dialog>
  );
}

export default function Vendors() {
  const query = useVendors(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Vendor | null>(null);
  const [planFor, setPlanFor] = useState<Vendor | null>(null);
  const deletePlan = useAction((v: { vendorId: number; planId: number }) => vendorsApi.deletePlan(v.vendorId, v.planId), { success: 'Plan removed' });

  return (
    <>
      <PageHeader
        title="Tools & plans"
        subtitle="The catalogue employees choose from. Plan prices drive the cost preview on requests."
        actions={<Button onClick={() => { setEditing(null); setFormOpen(true); }}>Add tool</Button>}
      />
      <QueryState
        query={query}
        isEmpty={(d) => d.length === 0}
        empty={<Card><EmptyState title="No tools yet" hint="Add Claude, ChatGPT and the other tools you pay for." /></Card>}
      >
        {(vendors) => (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {vendors.map((v) => (
              <Card
                key={v.id}
                title={
                  <span className="flex flex-wrap items-center gap-2">
                    {v.name}
                    <Badge tone="slate">{v.category === 'ai' ? 'AI' : label(v.category)}</Badge>
                    {!v.active && <Badge tone="red">Inactive</Badge>}
                  </span>
                }
                actions={
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => { setEditing(v); setFormOpen(true); }}>Edit</Button>
                    <Button size="sm" variant="secondary" onClick={() => setPlanFor(v)}>Add plan</Button>
                  </span>
                }
              >
                {v.website && (
                  <p className="mb-2 text-xs">
                    <a className="text-indigo-600 hover:underline" href={v.website} target="_blank" rel="noreferrer">{v.website}</a>
                  </p>
                )}
                {v.plans.length === 0 ? (
                  <p className="text-sm text-slate-500">No plans yet — requesters will have to type the cost themselves.</p>
                ) : (
                  <ul className="divide-y divide-slate-100 text-sm">
                    {v.plans.map((p) => (
                      <li key={p.id} className="flex items-center justify-between gap-2 py-1.5">
                        <span className="font-medium text-slate-800">{p.plan_name}</span>
                        <span className="flex items-center gap-2 text-slate-600">
                          <MoneyText amount={p.default_cost} currency={p.currency} /> / {label(p.billing_cycle).toLowerCase()}
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-700 hover:bg-red-50"
                            aria-label={`Remove plan ${p.plan_name}`}
                            loading={deletePlan.isPending && deletePlan.variables?.planId === p.id}
                            onClick={() => deletePlan.mutate({ vendorId: v.id, planId: p.id })}
                          >
                            Remove
                          </Button>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            ))}
          </div>
        )}
      </QueryState>
      <VendorDialog open={formOpen} onClose={() => setFormOpen(false)} vendor={editing} />
      <PlanDialog vendor={planFor} onClose={() => setPlanFor(null)} />
    </>
  );
}
