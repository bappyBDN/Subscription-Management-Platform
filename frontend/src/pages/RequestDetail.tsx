import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { requestsApi } from '@/api/requests';
import { useMe } from '@/auth/AuthProvider';
import { HandoverPanel } from '@/components/HandoverPanel';
import { RequestInfo, RequesterCard, Timeline } from '@/components/RequestViews';
import { ErrorState, LoadingRows, StatusBadge } from '@/components/shared';
import { Alert, Button, Card, Dialog, PageHeader } from '@/components/ui';
import { useAction, useRequest } from '@/hooks';
import { fmtDateTime, label } from '@/lib/format';

const APPROVER_ACTIONS = ['recommend', 'approve', 'reject', 'hold', 'info', 'resume', 'override'];

export default function RequestDetailPage() {
  const id = Number(useParams().id);
  const me = useMe();
  const query = useRequest(id);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
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

  return (
    <>
      <PageHeader
        title={`${r.req_no} · ${r.tool_name} ${r.plan_name}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={r.status} /> {label(r.type)} request · updated {fmtDateTime(r.status_changed_at)}
          </span>
        }
        actions={
          <>
            {canDecide && <Link to={`/approvals/${r.id}`}><Button>Review and decide</Button></Link>}
            {can('set_handover') && (
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
