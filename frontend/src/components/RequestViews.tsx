import { DECISION_LABEL } from '@/lib/constants';
import { durationLabel, fmtDate, fmtDateTime, label } from '@/lib/format';
import type { RequestDetail } from '@/types';

import { MoneyText, StatusBadge } from './shared';
import { Details } from './ui';

export function RequesterCard({ request }: { request: RequestDetail }) {
  const s = request.snapshot;
  return (
    <Details
      items={[
        ['Name', s.name ?? '—'],
        ['Employee ID', s.emp_code ?? '—'],
        ['Designation', s.designation ?? '—'],
        ['SBU', s.unit ?? '—'],
        ['Department', s.department ?? '—'],
        ...(s.function ? [['Function', s.function] as [string, string]] : []),
        ['Team', s.team ?? '—'],
        ['Reporting manager', s.manager_name ? `${s.manager_name} (${s.manager_code ?? ''})` : '—'],
        ['Email', s.email ?? '—'],
      ]}
    />
  );
}

export function RequestInfo({ request }: { request: RequestDetail }) {
  const r = request;
  return (
    <div className="space-y-4">
      <Details
        items={[
          ['Tool', r.other_tool_url
            ? <>{r.tool_name} · <a className="text-indigo-600 hover:underline" href={r.other_tool_url} target="_blank" rel="noreferrer">website</a></>
            : r.tool_name],
          ['Plan', r.plan_name],
          ['Request type', r.type === 'proposal' ? 'Proposal for a new tool' : label(r.type)],
          ['Seats', r.seats],
          ...(r.type === 'proposal'
            ? [['Proposed for', r.owner_scope === 'unit'
              ? `The whole ${r.snapshot.unit ?? ''} SBU`
              : r.owner_scope === 'function'
                ? `${r.snapshot.function ?? 'The'} function`
                : `${r.snapshot.department ?? 'The'} department`] as [string, string]]
            : []),
          ['Duration', durationLabel(r.duration_months)],
          ['Needed from', fmtDate(r.needed_from)],
          ['Estimated monthly cost', r.est_cost_bdt !== null
            ? <>
                <MoneyText amount={r.est_cost_bdt} currency="BDT" estimated />
                {r.est_currency && r.est_currency !== 'BDT' && (
                  <span className="ml-2 text-slate-500"><MoneyText amount={r.est_cost_original} currency={r.est_currency} /></span>
                )}
              </>
            : 'Not known'],
          ['Submitted', fmtDateTime(r.submitted_at)],
        ]}
      />
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Reason</p>
        <p className="mt-0.5 whitespace-pre-wrap text-sm text-slate-900">{r.reason}</p>
      </div>
      {r.expected_use && (
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Expected use</p>
          <p className="mt-0.5 whitespace-pre-wrap text-sm text-slate-900">{r.expected_use}</p>
        </div>
      )}
    </div>
  );
}

export function Timeline({ request }: { request: RequestDetail }) {
  const events = [
    { key: 'submitted', title: 'Submitted', who: request.snapshot.name ?? 'Requester', at: request.submitted_at, comment: null as string | null, status: null as string | null },
    ...request.approvals.map((a) => ({
      key: `a${a.id}`,
      title: DECISION_LABEL[a.decision] ?? label(a.decision),
      who: a.approver_name ?? 'System',
      at: a.created_at,
      comment: a.comment,
      status: a.to_status,
    })),
  ];
  return (
    <ol className="relative space-y-4 border-l border-slate-200 pl-4">
      {events.map((e) => (
        <li key={e.key} className="relative">
          <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-indigo-500" aria-hidden />
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-medium text-slate-900">{e.title}</span>
            {e.status && <StatusBadge status={e.status} />}
          </div>
          <p className="text-xs text-slate-500">{e.who} · {fmtDateTime(e.at)}</p>
          {e.comment && <p className="mt-1 whitespace-pre-wrap rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">{e.comment}</p>}
        </li>
      ))}
    </ol>
  );
}
