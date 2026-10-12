import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { usersApi } from '@/api/masters';
import { useAuth } from '@/auth/AuthProvider';
import { DataTable, type Columns } from '@/components/DataTable';
import { useToast } from '@/components/Toast';
import { Alert, Badge, Button, Card, Checkbox, Dialog, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAction, useAllEmployees } from '@/hooks';
import type { Employee, UserRow } from '@/types';

const ROLE_LABEL: Record<string, string> = { dmd: 'DMD', delegate: 'Delegate', employee: 'Employee' };

function UserDialog({ open, onClose, user, employees, withoutAccount }: {
  open: boolean;
  onClose: () => void;
  user: UserRow | null;
  employees: Map<number, Employee>;
  withoutAccount: Employee[];
}) {
  const { isDmd } = useAuth();
  const toast = useToast();
  const [employeeId, setEmployeeId] = useState('');
  const [password, setPassword] = useState('');
  const [roles, setRoles] = useState<string[]>(['employee']);
  const [reveal, setReveal] = useState(false);
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setEmployeeId('');
    setPassword('');
    setRoles(user?.roles ?? ['employee']);
    setReveal(user?.can_reveal_vault ?? false);
    setActive(user?.is_active ?? true);
  }, [open, user]);

  const save = useAction(
    () => {
      if (user) {
        const body: Record<string, unknown> = { roles, can_reveal_vault: reveal, is_active: active };
        if (password) body.password = password;
        return usersApi.update(user.id, body);
      }
      return usersApi.create({ employee_id: Number(employeeId), password, roles, can_reveal_vault: reveal });
    },
    { success: user ? 'Account updated' : 'Account created', onSuccess: onClose },
  );

  const submit = () => {
    if (!user && !employeeId) return toast.error('Choose the employee');
    if ((!user || password) && password.length < 8) return toast.error('The password needs at least 8 characters');
    save.mutate(undefined);
  };
  const toggleRole = (role: string, on: boolean) => setRoles((r) => (on ? [...new Set([...r, role])] : r.filter((x) => x !== role)));
  const name = user ? employees.get(user.employee_id)?.name ?? `User #${user.id}` : '';

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={user ? `Account · ${name}` : 'Create account'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={submit}>Save</Button>
        </>
      }
    >
      <div className="space-y-3">
        {!user && (
          <Field label="Employee" required hint="Only employees without an account are listed.">
            <Select value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              <option value="">Choose…</option>
              {withoutAccount.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.emp_code})</option>)}
            </Select>
          </Field>
        )}
        <Field label={user ? 'New password' : 'Password'} required={!user} hint={user ? 'Leave empty to keep the current password. Setting one also unlocks the account.' : 'At least 8 characters. Ask them to change it after the first sign-in.'}>
          <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-slate-700">Roles</legend>
          <div className="flex flex-wrap gap-4">
            <Checkbox label="Employee" checked disabled readOnly />
            <Checkbox label="Delegate (admin)" checked={roles.includes('delegate')} disabled={!isDmd} onChange={(e) => toggleRole('delegate', e.target.checked)} />
            <Checkbox label="DMD" checked={roles.includes('dmd')} disabled={!isDmd} onChange={(e) => toggleRole('dmd', e.target.checked)} />
          </div>
        </fieldset>
        <Checkbox label="May reveal vault credentials (delegates only)" checked={reveal} disabled={!isDmd} onChange={(e) => setReveal(e.target.checked)} />
        {user && <Checkbox label="Account is active" checked={active} onChange={(e) => setActive(e.target.checked)} />}
        {!isDmd && <Alert tone="amber">Only DMD Sir can grant admin roles or vault access.</Alert>}
      </div>
    </Dialog>
  );
}

export default function Users() {
  const { isDmd } = useAuth();
  const query = useQuery({ queryKey: ['users'], queryFn: usersApi.list });
  const everyone = useAllEmployees();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);

  const employees = useMemo(() => new Map(everyone.data?.map((e) => [e.id, e])), [everyone.data]);
  const withoutAccount = useMemo(() => {
    const taken = new Set(query.data?.map((u) => u.employee_id));
    return (everyone.data ?? []).filter((e) => e.status === 'active' && !taken.has(e.id));
  }, [everyone.data, query.data]);

  const columns = useMemo<Columns<UserRow>>(
    () => [
      {
        header: 'Employee',
        accessorFn: (u) => employees.get(u.employee_id)?.name ?? '',
        cell: ({ row }) => {
          const e = employees.get(row.original.employee_id);
          return <span>{e?.name ?? `Employee #${row.original.employee_id}`}<span className="block text-xs text-slate-500">{e?.emp_code} · {e?.email ?? 'no email'}</span></span>;
        },
      },
      {
        header: 'Roles',
        accessorFn: (u) => u.roles.join(','),
        cell: ({ row }) => (
          <span className="flex flex-wrap gap-1">
            {row.original.roles.map((r) => <Badge key={r} tone={r === 'dmd' ? 'indigo' : r === 'delegate' ? 'blue' : 'slate'}>{ROLE_LABEL[r] ?? r}</Badge>)}
          </span>
        ),
      },
      { header: 'Vault reveal', accessorKey: 'can_reveal_vault', cell: ({ getValue }) => (getValue<boolean>() ? 'Yes' : '—') },
      { header: 'Status', accessorKey: 'is_active', cell: ({ getValue }) => (getValue<boolean>() ? <Badge tone="green">Active</Badge> : <Badge tone="slate">Disabled</Badge>) },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) =>
          isDmd ? (
            <div className="text-right">
              <Button size="sm" variant="ghost" onClick={() => { setEditing(row.original); setFormOpen(true); }}>Edit</Button>
            </div>
          ) : null,
      },
    ],
    [employees, isDmd],
  );

  return (
    <>
      <PageHeader
        title="Users & roles"
        subtitle={isDmd ? 'Who can sign in and what they may do.' : 'You can create employee accounts. Only DMD Sir can change roles.'}
        actions={<Button onClick={() => { setEditing(null); setFormOpen(true); }}>Create account</Button>}
      />
      <Card className="[&>div:last-child]:p-0">
        <DataTable
          columns={columns}
          data={query.data}
          isLoading={query.isLoading || everyone.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          emptyTitle="No accounts yet"
        />
      </Card>
      <UserDialog open={formOpen} onClose={() => setFormOpen(false)} user={editing} employees={employees} withoutAccount={withoutAccount} />
    </>
  );
}
