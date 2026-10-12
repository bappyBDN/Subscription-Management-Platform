import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { usersApi } from '@/api/masters';
import { auditApi } from '@/api/system';
import { DataTable, type Columns } from '@/components/DataTable';
import { Button, Card, Dialog, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAllEmployees, useDebounced } from '@/hooks';
import { fmtDateTime } from '@/lib/format';
import type { AuditRow } from '@/types';

export default function AuditLog() {
  const [filters, setFilters] = useState({ user_id: '', action: '', from: '', to: '' });
  const debounced = useDebounced(filters);
  const query = useQuery({ queryKey: ['audit', debounced], queryFn: () => auditApi.list(debounced) });
  const users = useQuery({ queryKey: ['users'], queryFn: usersApi.list });
  const everyone = useAllEmployees();
  const [detail, setDetail] = useState<AuditRow | null>(null);

  // user id -> "Name (code)"
  const userName = useMemo(() => {
    const emp = new Map(everyone.data?.map((e) => [e.id, e]));
    return new Map(users.data?.map((u) => {
      const e = emp.get(u.employee_id);
      return [u.id, e ? `${e.name} (${e.emp_code})` : `User #${u.id}`];
    }));
  }, [users.data, everyone.data]);

  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  const columns = useMemo<Columns<AuditRow>>(
    () => [
      { header: 'Time', accessorKey: 'created_at', cell: ({ getValue }) => <span className="whitespace-nowrap">{fmtDateTime(getValue<string>())}</span> },
      { header: 'User', accessorFn: (r) => (r.user_id ? userName.get(r.user_id) ?? `User #${r.user_id}` : 'System') },
      { header: 'Action', accessorKey: 'action', cell: ({ getValue }) => <code className="whitespace-nowrap rounded bg-slate-100 px-1.5 py-0.5 text-xs">{getValue<string>()}</code> },
      { header: 'Entity', accessorFn: (r) => (r.entity ? `${r.entity}${r.entity_id ? ` #${r.entity_id}` : ''}` : '—') },
      { header: 'IP', accessorKey: 'ip', cell: ({ getValue }) => getValue<string | null>() ?? '—' },
      {
        id: 'detail',
        header: '',
        enableSorting: false,
        cell: ({ row }) =>
          row.original.before || row.original.after ? (
            <Button size="sm" variant="ghost" onClick={() => setDetail(row.original)}>Details</Button>
          ) : null,
      },
    ],
    [userName],
  );

  return (
    <>
      <PageHeader title="Audit log" subtitle="Every sign-in, decision, credential reveal and change. Newest first, up to 200 rows." />
      <Card className="mb-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Field label="User">
            <Select value={filters.user_id} onChange={set('user_id')}>
              <option value="">Everyone</option>
              {users.data?.map((u) => <option key={u.id} value={u.id}>{userName.get(u.id)}</option>)}
            </Select>
          </Field>
          <Field label="Action starts with" hint="e.g. auth, request, handover.reveal">
            <Input value={filters.action} onChange={set('action')} />
          </Field>
          <Field label="From"><Input type="date" value={filters.from} onChange={set('from')} /></Field>
          <Field label="To"><Input type="date" value={filters.to} onChange={set('to')} /></Field>
        </div>
      </Card>
      <Card className="[&>div:last-child]:p-0">
        <DataTable
          columns={columns}
          data={query.data}
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          pageSize={25}
          emptyTitle="No audit entries match these filters"
        />
      </Card>

      <Dialog open={!!detail} onClose={() => setDetail(null)} wide title={detail ? `${detail.action} · ${fmtDateTime(detail.created_at)}` : ''}>
        {detail && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(['before', 'after'] as const).map((side) => (
              <div key={side}>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{side}</p>
                <pre className="max-h-80 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                  {detail[side] ? JSON.stringify(detail[side], null, 2) : '—'}
                </pre>
              </div>
            ))}
          </div>
        )}
      </Dialog>
    </>
  );
}
