import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { requestsApi } from '@/api/requests';
import { EmployeeSearch } from '@/components/EmployeeSearch';
import { SubscriptionFormDialog } from '@/components/forms';
import { HandoverPanel } from '@/components/HandoverPanel';
import { RequestInfo, RequesterCard } from '@/components/RequestViews';
import { EmptyState, ErrorState, LoadingRows, StatusBadge } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Alert, Button, Card, Field, Input, PageHeader, Select, Tabs, Textarea } from '@/components/ui';
import { useAction, useRequest, useSubscriptions } from '@/hooks';
import { fmtDateTime, fromLocalInput, money, toLocalInput } from '@/lib/format';
import type { Employee } from '@/types';

type Method = 'vault' | 'appointment' | 'colleague';

export default function HandoverSetup() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const toast = useToast();
  const query = useRequest(id);
  const subs = useSubscriptions({ status: 'active' });
  const r = query.data;

  const [method, setMethod] = useState<Method>('vault');
  const [subscriptionId, setSubscriptionId] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  // vault
  const [secret, setSecret] = useState('');
  const [showSecret, setShowSecret] = useState(false);
  const [loginEmail, setLoginEmail] = useState('');
  const [loginUrl, setLoginUrl] = useState('');
  const [notes, setNotes] = useState('');
  // appointment
  const [confirmedAt, setConfirmedAt] = useState('');
  const [location, setLocation] = useState('');
  // colleague
  const [collector, setCollector] = useState<Pick<Employee, 'id' | 'name' | 'emp_code'> | null>(null);
  const [collectorNote, setCollectorNote] = useState('');
  const [dueDate, setDueDate] = useState('');

  // Start from the existing handover, if one was already set
  useEffect(() => {
    if (!r) return;
    const h = r.handover;
    if (r.subscription_id && r.type !== 'upgrade') setSubscriptionId(String(r.subscription_id));
    if (!h) return;
    setMethod(h.method);
    setLoginEmail(h.login_email ?? '');
    setLoginUrl(h.login_url ?? '');
    setNotes(h.notes ?? '');
    setConfirmedAt(toLocalInput(h.confirmed_at ?? h.proposed_at));
    setLocation(h.location ?? '');
    setCollector(h.collector_id && h.collector_name ? { id: h.collector_id, name: h.collector_name, emp_code: '' } : null);
    setCollectorNote(h.collector_note ?? '');
    setDueDate(h.due_date ?? '');
  }, [r?.id, r?.handover?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // the secret must never outlive this screen
  useEffect(() => () => setSecret(''), []);

  // Subscriptions of the requested tool first
  const options = useMemo(() => {
    const list = [...(subs.data ?? [])];
    return list.sort((a, b) => Number(b.vendor_id === r?.vendor_id) - Number(a.vendor_id === r?.vendor_id));
  }, [subs.data, r?.vendor_id]);

  const save = useAction((body: Record<string, unknown>) => requestsApi.setHandover(id, body), {
    success: 'Handover set — the requester has been notified',
    onSuccess: () => {
      setSecret('');
      navigate(`/requests/${id}`);
    },
  });

  if (query.isLoading) return <LoadingRows rows={6} />;
  if (query.error || !r) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!r.allowed_actions.includes('set_handover')) {
    return (
      <EmptyState
        title="Handover cannot be set for this request"
        hint="Handover is set after DMD Sir approves, and before the employee confirms receipt."
        action={<Link to={`/requests/${id}`}><Button size="sm" variant="secondary">Open the request</Button></Link>}
      />
    );
  }

  const submit = () => {
    if (!subscriptionId) return toast.error('Choose the subscription (seat) this access belongs to');
    const body: Record<string, unknown> = {
      method,
      subscription_id: Number(subscriptionId),
      notes: notes.trim() || null,
    };
    if (method === 'vault') {
      if (!secret) return toast.error('Enter the password, API key or token');
      Object.assign(body, { secret, login_email: loginEmail.trim() || null, login_url: loginUrl.trim() || null });
    } else if (method === 'appointment') {
      Object.assign(body, { confirmed_at: confirmedAt ? fromLocalInput(confirmedAt) : null, location: location.trim() || null });
    } else {
      if (!collector) return toast.error('Choose the colleague who will hand over access');
      Object.assign(body, { collector_id: collector.id, collector_note: collectorNote.trim() || null, due_date: dueDate || null });
    }
    save.mutate(body);
  };

  const h = r.handover;
  return (
    <>
      <PageHeader
        title={`Handover · ${r.req_no}`}
        subtitle={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={r.status} /> {r.tool_name} {r.plan_name} for {r.snapshot.name}</span>}
        actions={<Link to={`/requests/${id}`}><Button variant="secondary">Back to the request</Button></Link>}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {h && (
            <Card title="Current handover">
              <HandoverPanel handover={h} isRequester={false} canReceive={false} />
            </Card>
          )}

          <Card title="1 · Which subscription (seat)">
            <div className="space-y-3">
              <Field label="Subscription" required hint="The employee gets a seat on this subscription when they confirm receipt.">
                <Select value={subscriptionId} onChange={(e) => setSubscriptionId(e.target.value)} disabled={subs.isLoading}>
                  <option value="">{subs.isLoading ? 'Loading…' : 'Choose…'}</option>
                  {options.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.vendor_name} {s.plan_name} · {s.seats_total - s.seats_used} of {s.seats_total} seats free · {money(s.cost_per_cycle, s.currency)}
                    </option>
                  ))}
                </Select>
              </Field>
              {subs.error ? <Alert tone="red">Could not load the register. <button type="button" className="underline" onClick={() => subs.refetch()}>Try again</button></Alert> : null}
              <p className="text-sm text-slate-600">
                Bought a new one for this request?{' '}
                <button type="button" className="font-medium text-indigo-600 hover:underline" onClick={() => setAddOpen(true)}>
                  Add it to the register
                </button>
              </p>
            </div>
          </Card>

          <Card title="2 · How access is handed over">
            <Tabs
              value={method}
              onChange={setMethod}
              tabs={[
                { id: 'vault', label: 'A · Secure vault' },
                { id: 'appointment', label: 'B · Come to DMD Sir' },
                { id: 'colleague', label: 'C · Via colleague' },
              ]}
            />
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {method === 'vault' && (
                <>
                  <Field label="Login email">
                    <Input type="email" autoComplete="off" value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)} />
                  </Field>
                  <Field label="Login URL">
                    <Input type="url" placeholder="https://" value={loginUrl} onChange={(e) => setLoginUrl(e.target.value)} />
                  </Field>
                  <Field
                    label="Password / API key"
                    required
                    className="sm:col-span-2"
                    hint={h?.has_secret ? 'A credential is already stored — entering a new one replaces it.' : 'Encrypted before it is stored. The employee reveals it once with an email code.'}
                  >
                    <div className="flex gap-2">
                      <Input
                        type={showSecret ? 'text' : 'password'}
                        autoComplete="new-password"
                        spellCheck={false}
                        value={secret}
                        onChange={(e) => setSecret(e.target.value)}
                        className="font-mono"
                      />
                      <Button variant="secondary" onClick={() => setShowSecret((v) => !v)}>{showSecret ? 'Hide' : 'Show'}</Button>
                    </div>
                  </Field>
                </>
              )}

              {method === 'appointment' && (
                <>
                  <Field label="Requester's proposed slot" className="sm:col-span-2">
                    <Input readOnly value={h?.proposed_at ? fmtDateTime(h.proposed_at) : 'None yet — the employee can propose one after you save'} className="bg-slate-100" />
                  </Field>
                  <Field label="Confirmed date and time (Dhaka)" hint="Leave empty to let the employee propose a time.">
                    <Input type="datetime-local" value={confirmedAt} onChange={(e) => setConfirmedAt(e.target.value)} />
                  </Field>
                  <Field label="Location">
                    <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="DMD Sir's office, 5th floor" />
                  </Field>
                </>
              )}

              {method === 'colleague' && (
                <>
                  <Field label="Collector" required className="sm:col-span-2" hint="The colleague who holds the login and will hand it over.">
                    <EmployeeSearch value={collector} onChange={setCollector} />
                  </Field>
                  <Field label="Note to collector" className="sm:col-span-2">
                    <Textarea rows={2} value={collectorNote} onChange={(e) => setCollectorNote(e.target.value)} />
                  </Field>
                  <Field label="Due date">
                    <Input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
                  </Field>
                </>
              )}

              <Field label={method === 'colleague' ? 'Note to requester' : 'Notes'} className="sm:col-span-2" hint="Shown to the employee. Never type passwords or card numbers here.">
                <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
              </Field>
            </div>
            <div className="mt-4 flex justify-end">
              <Button loading={save.isPending} onClick={submit}>{h ? 'Update handover' : 'Save handover'}</Button>
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Requester"><RequesterCard request={r} /></Card>
          <Card title="Request"><RequestInfo request={r} /></Card>
        </div>
      </div>

      <SubscriptionFormDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        defaults={{
          vendor_id: r.vendor_id ? String(r.vendor_id) : '',
          plan_name: r.plan_name,
          seats_total: r.seats,
          currency: r.est_currency ?? 'USD',
          billing_cycle: r.est_billing_cycle ?? 'monthly',
          unit: r.snapshot.unit ?? '',
          department: r.snapshot.department ?? '',
        }}
        onSaved={(sub) => setSubscriptionId(String(sub.id))}
      />
    </>
  );
}
