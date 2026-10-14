import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { usersApi } from '@/api/masters';
import { useAuth } from '@/auth/AuthProvider';
import { DataTable, type Columns } from '@/components/DataTable';
import { DeleteButton } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Alert, Badge, Button, Card, Checkbox, Dialog, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAction, useAllEmployees } from '@/hooks';
import type { Employee, UserRow } from '@/types';

const ROLE_LABEL: Record<string, string> = { dmd: 'DMD', delegate: 'Delegate', employee: 'Employee' };

/** 12 random characters, no look-alikes (0/O, 1/l/I), always with a digit and a symbol. */
function generatePassword(): string {
  const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz';
  const digits = '23456789';
  const symbols = '#@$%&*!?';
  const pick = (set: string) => set[crypto.getRandomValues(new Uint32Array(1))[0] % set.length];
  const chars = [...Array.from({ length: 10 }, () => pick(letters + digits)), pick(digits), pick(symbols)];
  for (let i = chars.length - 1; i > 0; i--) {
    const j = crypto.getRandomValues(new Uint32Array(1))[0] % (i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join('');
}

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
  const [showPassword, setShowPassword] = useState(false);
  const [emailIt, setEmailIt] = useState(true);
  const [roles, setRoles] = useState<string[]>(['employee']);
  const [reveal, setReveal] = useState(false);
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setEmployeeId('');
    setPassword('');
    setShowPassword(false);
    setEmailIt(!user);
    setRoles(user?.roles ?? ['employee']);
    setReveal(user?.can_reveal_vault ?? false);
    setActive(user?.is_active ?? true);
  }, [open, user]);

  const target = user ? employees.get(user.employee_id) : withoutAccount.find((e) => e.id === Number(employeeId));
  const sendEmail = emailIt && !!password && !!target?.email;

  const save = useAction(
    () => {
      if (user) {
        const body: Record<string, unknown> = { roles, can_reveal_vault: reveal, is_active: active };
        if (password) Object.assign(body, { password, send_email: sendEmail });
        return usersApi.update(user.id, body);
      }
      return usersApi.create({ employee_id: Number(employeeId), password, roles, can_reveal_vault: reveal, send_email: sendEmail });
    },
    {
      success: `${user ? 'Account updated' : 'Account created'}${sendEmail ? ` — password emailed to ${target?.email}` : ''}`,
      onSuccess: onClose,
    },
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
        <Field label={user ? 'New password' : 'Password'} required={!user} hint={user ? 'Leave empty to keep the current password. Setting one also unlocks the account.' : 'At least 8 characters. They can change it after signing in.'}>
          <div className="flex gap-2">
            <Input
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="flex-1"
            />
            <Button type="button" variant="secondary" onClick={() => setShowPassword((v) => !v)}>{showPassword ? 'Hide' : 'Show'}</Button>
            <Button type="button" variant="secondary" onClick={() => { setPassword(generatePassword()); setShowPassword(true); }}>Generate</Button>
          </div>
        </Field>
        {(!user || password) && (
          <Checkbox
            label={target?.email ? `Email the password to ${target.email}` : 'Email the password (this employee has no email address)'}
            checked={emailIt && !!target?.email}
            disabled={!target?.email}
            onChange={(e) => setEmailIt(e.target.checked)}
          />
        )}
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
        cell: ({ row }) => {
          const u = row.original;
          // delegates may only delete plain employee accounts (the server checks this too)
          const canDelete = isDmd || !u.roles.some((r) => r === 'dmd' || r === 'delegate');
          return (
            <div className="flex justify-end gap-1">
              {isDmd && <Button size="sm" variant="ghost" onClick={() => { setEditing(u); setFormOpen(true); }}>Edit</Button>}
              {canDelete && (
                <DeleteButton
                  what={`the login of ${employees.get(u.employee_id)?.name ?? `user #${u.id}`}`}
                  onDelete={() => usersApi.remove(u.id)}
                  note={<p>The employee record stays. An account that has already been used cannot be deleted — untick “Account is active” instead.</p>}
                />
              )}
            </div>
          );
        },
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
