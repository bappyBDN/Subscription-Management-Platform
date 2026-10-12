import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { requestsApi, type Scope } from '@/api/requests';
import { useAuth } from '@/auth/AuthProvider';
import { DataTable, type Columns } from '@/components/DataTable';
import { StatusBadge } from '@/components/shared';
import { Button, Card, PageHeader, Select, Tabs } from '@/components/ui';
import { REQUEST_STATUSES, STATUS_LABEL } from '@/lib/constants';
import { fmtDate, fmtDateTime, label } from '@/lib/format';
import type { RequestRow } from '@/types';

export default function RequestsList() {
  const { isAdmin, isManager } = useAuth();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [status, setStatus] = useState('');

  const tabs = useMemo(() => {
    const list: { id: Scope; label: string }[] = [{ id: 'mine', label: 'My requests' }];
    if (isAdmin) list.push({ id: 'handover', label: 'Needs handover' }, { id: 'all', label: 'All requests' });
    else if (isManager) list.push({ id: 'team', label: 'My team' });
    return list;
  }, [isAdmin, isManager]);
  const wanted = search.get('scope') as Scope | null;
  const scope: Scope = tabs.some((t) => t.id === wanted) ? wanted! : 'mine';

  const query = useQuery({ queryKey: ['requests', scope, status], queryFn: () => requestsApi.list(scope, status || undefined) });

  const columns = useMemo<Columns<RequestRow>>(() => {
    const cols: Columns<RequestRow> = [
      { header: 'Number', accessorKey: 'req_no', cell: ({ row }) => <span className="whitespace-nowrap font-medium text-indigo-700">{row.original.req_no}</span> },
    ];
    if (scope !== 'mine') {
      cols.push({
        header: 'Employee',
        accessorFn: (r) => r.snapshot.name ?? '',
        cell: ({ row }) => (
          <span>
            {row.original.snapshot.name}
            <span className="block text-xs text-slate-500">{row.original.snapshot.emp_code} · {row.original.snapshot.team ?? '—'}</span>
          </span>
        ),
      });
    }
    cols.push(
      { header: 'Tool', accessorFn: (r) => `${r.tool_name} ${r.plan_name}`, cell: ({ row }) => <span>{row.original.tool_name} <span className="text-slate-500">{row.original.plan_name}</span></span> },
      { header: 'Type', accessorKey: 'type', cell: ({ getValue }) => label(getValue<string>()) },
      { header: 'Status', accessorKey: 'status', cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> },
      { header: 'Submitted', accessorKey: 'submitted_at', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmtDate(getValue<string>())}</span> },
      { header: 'Last update', accessorKey: 'status_changed_at', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmtDateTime(getValue<string>())}</span> },
    );
    if (scope === 'handover') {
      cols.push({
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => (
          <Link to={`/requests/${row.original.id}/handover`} onClick={(e) => e.stopPropagation()}>
            <Button size="sm">{row.original.status === 'approved' ? 'Set up handover' : 'Change handover'}</Button>
          </Link>
        ),
      });
    }
    return cols;
  }, [scope]);

  return (
    <>
      <PageHeader
        title="Requests"
        actions={<Link to="/requests/new"><Button>New request</Button></Link>}
      />
      {tabs.length > 1 && (
        <div className="mb-3">
          <Tabs tabs={tabs} value={scope} onChange={(id) => setSearch(id === 'mine' ? {} : { scope: id })} />
        </div>
      )}
      <Card
        className="[&>div:last-child]:p-0"
        title={tabs.find((t) => t.id === scope)?.label}
        actions={
          scope !== 'handover' && (
            <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="!w-auto !py-1 text-xs">
              <option value="">Every status</option>
              {REQUEST_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s] ?? label(s)}</option>)}
            </Select>
          )
        }
      >
        <DataTable
          columns={columns}
          data={query.data}
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          onRowClick={(r) => navigate(`/requests/${r.id}`)}
          emptyTitle={scope === 'handover' ? 'No approved requests are waiting for handover' : 'No requests found'}
          emptyHint={scope === 'mine' && !status ? 'When you ask for a tool, it shows up here with its status.' : undefined}
          emptyAction={scope === 'mine' && !status ? <Link to="/requests/new"><Button size="sm">New request</Button></Link> : undefined}
        />
      </Card>
    </>
  );
}
