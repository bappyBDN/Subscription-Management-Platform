import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { requestsApi } from '@/api/requests';
import { useMe } from '@/auth/AuthProvider';
import { SubscriptionFormDialog } from '@/components/forms';
import { HandoverPanel } from '@/components/HandoverPanel';
import { RequestInfo, RequesterCard, Timeline } from '@/components/RequestViews';
import { ErrorState, LoadingRows, StatusBadge } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Alert, Button, Card, Dialog, Field, PageHeader, Select } from '@/components/ui';
import { useAction, useRequest, useSubscriptions } from '@/hooks';
import { fmtDateTime, label, money } from '@/lib/format';
import type { RequestDetail } from '@/types';

const APPROVER_ACTIONS = ['recommend', 'approve', 'reject', 'hold', 'info', 'resume', 'override'];

/** DMD / delegate: close an approved proposal by linking the subscription that was bought for it */
function FulfilDialog({ request, open, onClose }: { request: RequestDetail; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const subs = useSubscriptions({ status: 'active', unit_id: request.unit_id ?? '' }, open);
  const [subscriptionId, setSubscriptionId] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const forUnit = request.owner_scope === 'unit';
  const forFunction = request.owner_scope === 'function';
  const functionId = request.snapshot.function_id ?? null;
  // the subscription must be owned the way the proposal asked: SBU-wide, by that department or by that function
  const options = useMemo(
    () => (subs.data ?? []).filter((s) => (forUnit
      ? s.owner_scope === 'unit'
      : forFunction
        ? s.owner_scope === 'function' && s.function_id === functionId
        : s.owner_scope === 'department' && s.department_id === request.department_id)),
    [subs.data, forUnit, forFunction, functionId, request.department_id],
  );
  const fulfil = useAction(() => requestsApi.fulfil(request.id, Number(subscriptionId)), {
    success: 'Proposal fulfilled — colleagues can now request a seat',
    onSuccess: onClose,
  });
  const owner = forUnit
    ? `the whole ${request.snapshot.unit ?? ''} SBU`
    : forFunction
      ? `the ${request.snapshot.function ?? ''} function`
      : `the ${request.snapshot.department ?? ''} department`;

  return (
    <>
      <Dialog
        open={open && !addOpen}
        onClose={onClose}
        title={`Fulfil ${request.req_no}`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button loading={fulfil.isPending} onClick={() => (subscriptionId ? fulfil.mutate(undefined) : toast.error('Choose the subscription'))}>
              Fulfil proposal
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            Link the subscription that was bought for this proposal. It must be owned by {owner}.
          </p>
          <Field label="Subscription" required>
            <Select value={subscriptionId} disabled={subs.isLoading} onChange={(e) => setSubscriptionId(e.target.value)}>
              <option value="">{subs.isLoading ? 'Loading…' : 'Choose…'}</option>
              {options.map((s) => (
                <option key={s.id} value={s.id}>{s.vendor_name} {s.plan_name} · {s.owner_label} · {money(s.cost_per_cycle, s.currency)}</option>
              ))}
            </Select>
          </Field>
          {subs.error ? <Alert tone="red">Could not load the register.</Alert> : null}
          {subs.data && options.length === 0 && <Alert tone="amber">No active subscription is owned by {owner} yet.</Alert>}
          <p className="text-sm text-slate-600">
            Not in the register yet?{' '}
            <button type="button" className="font-medium text-indigo-600 hover:underline" onClick={() => setAddOpen(true)}>Add it now</button>
          </p>
        </div>
      </Dialog>
      <SubscriptionFormDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        defaults={{
          vendor_id: request.vendor_id ? String(request.vendor_id) : '',
          plan_name: request.plan_name,
          seats_total: request.seats,
          currency: request.est_currency ?? 'USD',
          billing_cycle: request.est_billing_cycle ?? 'monthly',
          owner_scope: forUnit ? 'unit' : forFunction ? 'function' : 'department',
          unit_id: request.unit_id ? String(request.unit_id) : '',
          department_id: !forUnit && request.department_id ? String(request.department_id) : '',
          function_id: forFunction && functionId ? String(functionId) : '',
        }}
        onSaved={(sub) => setSubscriptionId(String(sub.id))}
      />
    </>
  );
}

export default function RequestDetailPage() {
  const id = Number(useParams().id);
  const me = useMe();
  const query = useRequest(id);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [fulfilOpen, setFulfilOpen] = useState(false);
  const withdraw = useAction(() => requestsApi.withdraw(id), {
    success: 'Request withdrawn',
    onSuccess: () => setConfirmWithdraw(false),
  });

  if (query.isLoading) return <LoadingRows rows={6} />;
  if (query.error || !query.data) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const r = query.data;
  const can = (action: string) => r.allowed_actions.includes(action);
  const isRequester = r.employee_id === me.employee_id;
  const canDecide = APPROVER_ACTIONS.some(can);
  const isProposal = r.type === 'proposal';

  return (
    <>
      <PageHeader
        title={`${r.req_no} · ${r.tool_name} ${r.plan_name}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={r.status} /> {isProposal ? 'Proposal for a new tool' : `${label(r.type)} request`} · updated {fmtDateTime(r.status_changed_at)}
          </span>
        }
        actions={
          <>
            {canDecide && <Link to={`/approvals/${r.id}`}><Button>Review and decide</Button></Link>}
            {can('fulfil') && <Button onClick={() => setFulfilOpen(true)}>Fulfil proposal</Button>}
            {can('set_handover') && !isProposal && (
              <Link to={`/requests/${r.id}/handover`}>
                <Button>{r.handover ? 'Change handover' : 'Set up handover'}</Button>
              </Link>
            )}
            {can('resubmit') && <Link to={`/requests/${r.id}/edit`}><Button>Edit &amp; resubmit</Button></Link>}
            {can('withdraw') && <Button variant="danger" onClick={() => setConfirmWithdraw(true)}>Withdraw</Button>}
          </>
        }
      />

      {r.status === 'info_needed' && isRequester && (
        <div className="mb-4">
          <Alert tone="blue">
            More information is needed — see the latest comment in the timeline, then use <strong>Edit &amp; resubmit</strong>.
          </Alert>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Request">
            <RequestInfo request={r} />
          </Card>
          {!isRequester && (
            <Card title="Requester">
              <RequesterCard request={r} />
            </Card>
          )}
          {r.handover ? (
            <Card title="Handover">
              <HandoverPanel handover={r.handover} isRequester={isRequester} canReceive={can('receive')} />
            </Card>
          ) : isProposal && (r.status === 'approved' || r.status === 'fulfilled') ? (
            <Card title="Next step">
              <p className="text-sm text-slate-600">
                {r.status === 'approved'
                  ? "Approved. DMD Sir's office will buy the subscription and add it to the register; it then becomes available to request."
                  : 'The subscription is in the register. People in the owning SBU, department or function can now request a seat on it from New request.'}
              </p>
            </Card>
          ) : r.status === 'approved' ? (
            <Card title="Handover">
              <p className="text-sm text-slate-600">
                Approved. DMD Sir&apos;s office is arranging how you will get access — you will be notified here.
              </p>
            </Card>
          ) : null}
        </div>
        <Card title="Timeline" className="self-start">
          <Timeline request={r} />
        </Card>
      </div>

      <FulfilDialog request={r} open={fulfilOpen} onClose={() => setFulfilOpen(false)} />
      <Dialog
        open={confirmWithdraw}
        onClose={() => setConfirmWithdraw(false)}
        title="Withdraw this request?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmWithdraw(false)}>Keep it</Button>
            <Button variant="danger" loading={withdraw.isPending} onClick={() => withdraw.mutate(undefined)}>Withdraw</Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          {r.req_no} will be closed and cannot be reopened. You can always raise a new request.
        </p>
      </Dialog>
    </>
  );
}
