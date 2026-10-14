import { Link } from 'react-router-dom';

import { HandoverPanel } from '@/components/HandoverPanel';
import { EmptyState, ErrorState, LoadingRows, StatusBadge } from '@/components/shared';
import { Button, Card, PageHeader } from '@/components/ui';
import { useMySubscriptions } from '@/hooks';
import { METHOD_LABEL } from '@/lib/constants';
import { fmtDate } from '@/lib/format';
import type { MySubscription } from '@/types';

function prefill(type: string, s: MySubscription) {
  const q = new URLSearchParams({ type, subscription_id: String(s.subscription_id) });
  return `/requests/new?${q.toString()}`;
}

export default function MySubscriptions() {
  const query = useMySubscriptions();

  if (query.isLoading) return <LoadingRows rows={6} />;
  if (query.error || !query.data) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  const { active, pending_handover: pending } = query.data;

  return (
    <>
      <PageHeader
        title="My subscriptions"
        subtitle="The tools you hold, and access that is on its way to you."
        actions={<Link to="/requests/new"><Button>New request</Button></Link>}
      />

      {pending.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">On its way to you</h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {pending.map((p) => (
              <Card
                key={p.request_id}
                title={<span>{p.tool_name} <span className="font-normal text-slate-500">{p.plan_name}</span></span>}
                actions={<StatusBadge status={p.status} />}
              >
                {p.handover ? (
                  <HandoverPanel handover={p.handover} isRequester canReceive={p.status === 'handover_pending'} />
                ) : (
                  <p className="text-sm text-slate-600">Approved. DMD Sir&apos;s office is arranging how you will get access.</p>
                )}
                <p className="mt-3 text-xs text-slate-500">
                  <Link className="font-medium text-indigo-600 hover:underline" to={`/requests/${p.request_id}`}>{p.req_no}</Link>
                </p>
              </Card>
            ))}
          </div>
        </section>
      )}

      <h2 className="mb-2 text-sm font-semibold text-slate-700">Active tools</h2>
      {active.length === 0 ? (
        <Card>
          <EmptyState
            title="You have no active tools"
            hint="Once a request is approved and you confirm you received access, the tool appears here."
            action={<Link to="/requests/new"><Button size="sm">New request</Button></Link>}
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {active.map((s) => (
            <Card
              key={s.assignment_id}
              title={<span>{s.vendor_name} <span className="font-normal text-slate-500">{s.plan_name}</span></span>}
              actions={<StatusBadge status={s.status} />}
            >
              <dl className="mb-3 grid grid-cols-2 gap-3 text-sm">
                <div><dt className="text-xs uppercase tracking-wide text-slate-500">Since</dt><dd>{fmtDate(s.start_date)}</dd></div>
                <div><dt className="text-xs uppercase tracking-wide text-slate-500">{s.end_date ? 'Your access ends' : 'Renews'}</dt><dd>{fmtDate(s.end_date ?? s.next_renewal_date)}</dd></div>
                <div><dt className="text-xs uppercase tracking-wide text-slate-500">Handover</dt><dd>{s.handover ? METHOD_LABEL[s.handover.method] : 'Assigned directly'}</dd></div>
                {s.req_no && s.request_id && (
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Request</dt>
                    <dd><Link className="text-indigo-600 hover:underline" to={`/requests/${s.request_id}`}>{s.req_no}</Link></dd>
                  </div>
                )}
              </dl>
              {s.status === 'revoke_pending' && (
                <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  This seat is under review because your team or role changed.
                </p>
              )}
              {s.handover && <HandoverPanel handover={s.handover} isRequester canReceive={false} />}
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                <Link to={prefill('renewal', s)}><Button variant="secondary" size="sm">Request renewal</Button></Link>
                <Link to={prefill('cancel', s)}><Button variant="ghost" size="sm" className="text-red-700 hover:bg-red-50">Cancel</Button></Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
