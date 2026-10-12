import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { requestsApi } from '@/api/requests';
import { RequestInfo, RequesterCard, Timeline } from '@/components/RequestViews';
import { EmptyState, ErrorState, LoadingRows, QueryState, StatusBadge } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Alert, Button, Card, Field, Input, PageHeader, Select, Textarea } from '@/components/ui';
import { useAction, useRequest } from '@/hooks';
import { DURATIONS } from '@/lib/constants';
import { fmtDate } from '@/lib/format';

type Variant = 'primary' | 'secondary' | 'danger' | 'success';
const ACTIONS: { id: string; label: string; variant: Variant; needsComment?: boolean; commentLabel?: string }[] = [
  { id: 'recommend', label: 'Recommend', variant: 'success' },
  { id: 'approve', label: 'Approve', variant: 'success' },
  { id: 'resume', label: 'Resume', variant: 'primary' },
  { id: 'hold', label: 'Put on hold', variant: 'secondary' },
  { id: 'info', label: 'Ask for information', variant: 'secondary', needsComment: true, commentLabel: 'what you need to know' },
  { id: 'reject', label: 'Reject', variant: 'danger', needsComment: true, commentLabel: 'the reason for rejecting' },
  { id: 'override', label: 'Approve now (urgent override)', variant: 'secondary', needsComment: true, commentLabel: 'why the manager step is skipped' },
];

export default function RequestDecision() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const toast = useToast();
  const query = useRequest(id);
  const tools = useQuery({ queryKey: ['requester-tools', id], queryFn: () => requestsApi.requesterTools(id), enabled: Number.isFinite(id) });

  const [comment, setComment] = useState('');
  const [plan, setPlan] = useState('');
  const [seats, setSeats] = useState(1);
  const [duration, setDuration] = useState('open');

  const r = query.data;
  useEffect(() => {
    if (!r) return;
    setPlan(r.plan_name);
    setSeats(r.seats);
    setDuration(r.duration_months ? String(r.duration_months) : 'open');
  }, [r?.id, r?.plan_name, r?.seats, r?.duration_months]); // eslint-disable-line react-hooks/exhaustive-deps

  const decide = useAction((body: Record<string, unknown>) => requestsApi.decide(id, body), {
    success: (res) => `${res.req_no} updated`,
    onSuccess: () => navigate('/approvals'),
  });

  if (query.isLoading) return <LoadingRows rows={6} />;
  if (query.error || !r) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const available = ACTIONS.filter((a) => r.allowed_actions.includes(a.id));
  // DMD Sir may adjust plan, seats and duration before approving
  const canAdjust = r.allowed_actions.includes('approve') || r.allowed_actions.includes('override');

  const run = (action: (typeof ACTIONS)[number]) => {
    const text = comment.trim();
    if (action.needsComment && !text) {
      toast.error(`Add a comment first — ${action.commentLabel}`);
      return;
    }
    const body: Record<string, unknown> = { decision: action.id, comment: text || null };
    if (canAdjust && (action.id === 'approve' || action.id === 'override')) {
      if (!plan.trim() || !(seats >= 1)) {
        toast.error('Plan and seats cannot be empty');
        return;
      }
      body.plan_name = plan.trim();
      body.seats = seats;
      if (duration !== 'open') body.duration_months = Number(duration);
    }
    decide.mutate(body);
  };

  return (
    <>
      <PageHeader
        title={`${r.req_no} · ${r.tool_name} ${r.plan_name}`}
        subtitle={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={r.status} /> waiting {r.waiting_days} day(s)</span>}
        actions={<Link to="/approvals"><Button variant="secondary">Back to inbox</Button></Link>}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Requester"><RequesterCard request={r} /></Card>
          <Card title="Request"><RequestInfo request={r} /></Card>
          <Card title="Requester's current tools">
            <QueryState query={tools} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No tools held at the moment" />}>
              {(rows) => (
                <ul className="divide-y divide-slate-100 text-sm">
                  {rows.map((t) => (
                    <li key={t.subscription_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <span>{t.vendor_name} <span className="text-slate-500">{t.plan_name}</span></span>
                      <span className="flex items-center gap-2 text-xs text-slate-500">
                        {t.end_date && <>until {fmtDate(t.end_date)}</>}
                        <StatusBadge status={t.status} />
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </QueryState>
          </Card>
          <Card title="Timeline"><Timeline request={r} /></Card>
        </div>

        <div className="lg:col-span-1">
          <Card title="Your decision" className="lg:sticky lg:top-20">
            {available.length === 0 ? (
              <EmptyState
                title="Nothing for you to decide here"
                hint="This request is not at your step, or it has already been decided."
                action={<Link to={`/requests/${r.id}`}><Button size="sm" variant="secondary">Open the request</Button></Link>}
              />
            ) : (
              <div className="space-y-3">
                {canAdjust && (
                  <div className="space-y-3 rounded-md bg-slate-50 p-3">
                    <p className="text-xs font-medium text-slate-600">Adjust before approving (optional)</p>
                    <Field label="Plan">
                      <Input value={plan} onChange={(e) => setPlan(e.target.value)} />
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Seats">
                        <Input type="number" min={1} max={100} value={seats} onChange={(e) => setSeats(Number(e.target.value))} />
                      </Field>
                      <Field label="Duration">
                        <Select value={duration} onChange={(e) => setDuration(e.target.value)}>
                          {DURATIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                        </Select>
                      </Field>
                    </div>
                  </div>
                )}
                <Field label="Comment" hint="Required to reject, ask for information or override. The requester sees it.">
                  <Textarea rows={4} value={comment} onChange={(e) => setComment(e.target.value)} />
                </Field>
                {r.allowed_actions.includes('override') && (
                  <Alert tone="amber">This request is still with the reporting manager. An urgent override skips that step and needs a reason.</Alert>
                )}
                <div className="flex flex-col gap-2">
                  {available.map((a) => (
                    <Button
                      key={a.id}
                      variant={a.variant}
                      loading={decide.isPending && decide.variables?.decision === a.id}
                      disabled={decide.isPending}
                      onClick={() => run(a)}
                    >
                      {a.label}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
