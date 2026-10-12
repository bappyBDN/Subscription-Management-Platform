import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';

import { employeesApi } from '@/api/masters';
import { DataTable, type Columns } from '@/components/DataTable';
import { ImportDialog } from '@/components/forms';
import { StatusBadge } from '@/components/shared';
import { Button, Card, Dialog, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAction, useAllEmployees, useDebounced } from '@/hooks';
import { UNITS } from '@/lib/constants';
import type { Employee } from '@/types';

interface EmployeeForm {
  emp_code: string;
  name: string;
  designation: string;
  department: string;
  team: string;
  unit: string;
  manager_id: string;
  email: string;
  phone: string;
}

const orNull = (v: string) => v.trim() || null;

function EmployeeDialog({ open, onClose, employee, everyone }: {
  open: boolean;
  onClose: () => void;
  employee: Employee | null;
  everyone: Employee[];
}) {
  const { register, handleSubmit, reset, formState } = useForm<EmployeeForm>();
  useEffect(() => {
    if (!open) return;
    reset({
      emp_code: employee?.emp_code ?? '',
      name: employee?.name ?? '',
      designation: employee?.designation ?? '',
      department: employee?.department ?? '',
      team: employee?.team ?? '',
      unit: employee?.unit ?? 'AES',
      manager_id: employee?.manager_id ? String(employee.manager_id) : '',
      email: employee?.email ?? '',
      phone: employee?.phone ?? '',
    });
  }, [open, employee, reset]);

  const save = useAction(
    (v: EmployeeForm) => {
      const body = {
        name: v.name.trim(),
        designation: orNull(v.designation),
        department: orNull(v.department),
        team: orNull(v.team),
        unit: v.unit,
        manager_id: v.manager_id ? Number(v.manager_id) : null,
        email: orNull(v.email),
        phone: orNull(v.phone),
      };
      return employee ? employeesApi.update(employee.id, body) : employeesApi.create({ ...body, emp_code: v.emp_code.trim() });
    },
    { success: employee ? 'Employee updated' : 'Employee added', onSuccess: onClose },
  );
  const e = formState.errors;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title={employee ? `Edit ${employee.name}` : 'Add employee'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={handleSubmit((v) => save.mutate(v))}>Save</Button>
        </>
      }
    >
      <form className="grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={(ev) => ev.preventDefault()}>
        <Field label="Employee code" required error={e.emp_code?.message}>
          <Input disabled={!!employee} {...register('emp_code', { required: 'Enter the employee code', maxLength: { value: 20, message: 'At most 20 characters' } })} />
        </Field>
        <Field label="Name" required error={e.name?.message}>
          <Input {...register('name', { required: 'Enter the name' })} />
        </Field>
        <Field label="Designation"><Input {...register('designation')} /></Field>
        <Field label="Unit" required>
          <Select {...register('unit')}>{UNITS.map((u) => <option key={u}>{u}</option>)}</Select>
        </Field>
        <Field label="Department"><Input {...register('department')} /></Field>
        <Field label="Team"><Input {...register('team')} /></Field>
        <Field label="Reporting manager" className="sm:col-span-2" hint="Changing the manager or team puts the employee's seats under review.">
          <Select {...register('manager_id')}>
            <option value="">None (reports to nobody)</option>
            {everyone.filter((x) => x.id !== employee?.id && x.status === 'active').map((x) => (
              <option key={x.id} value={x.id}>{x.name} ({x.emp_code})</option>
            ))}
          </Select>
        </Field>
        <Field label="Email" error={e.email?.message}>
          <Input type="email" {...register('email', { pattern: { value: /^$|^[^@\s]+@[^@\s]+\.[^@\s]+$/, message: 'Enter a valid email' } })} />
        </Field>
        <Field label="Phone"><Input {...register('phone')} /></Field>
      </form>
    </Dialog>
  );
}

export default function Employees() {
  const [status, setStatus] = useState('active');
  const [unit, setUnit] = useState('');
  const [text, setText] = useState('');
  const q = useDebounced(text.trim());
  const query = useQuery({ queryKey: ['employees', { q, status, unit }], queryFn: () => employeesApi.list({ q, status, unit }) });
  const everyone = useAllEmployees();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Employee | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [deactivating, setDeactivating] = useState<Employee | null>(null);

  const setStatusOf = useAction(
    (v: { employee: Employee; status: string }) => employeesApi.update(v.employee.id, { status: v.status }),
    { success: (emp) => `${emp.name} is now ${emp.status}`, onSuccess: () => setDeactivating(null) },
  );

  const names = useMemo(() => new Map(everyone.data?.map((x) => [x.id, x.name])), [everyone.data]);
  const columns = useMemo<Columns<Employee>>(
    () => [
      { header: 'Code', accessorKey: 'emp_code', cell: ({ getValue }) => <span className="whitespace-nowrap font-medium">{getValue<string>()}</span> },
      { header: 'Name', accessorKey: 'name', cell: ({ row }) => <span>{row.original.name}<span className="block text-xs text-slate-500">{row.original.designation ?? ''}</span></span> },
      { header: 'Unit', accessorKey: 'unit' },
      { header: 'Department', accessorKey: 'department', cell: ({ getValue }) => getValue<string | null>() ?? '—' },
      { header: 'Team', accessorKey: 'team', cell: ({ getValue }) => getValue<string | null>() ?? '—' },
      { header: 'Manager', accessorFn: (x) => (x.manager_id ? names.get(x.manager_id) ?? '' : ''), cell: ({ getValue }) => getValue<string>() || '—' },
      { header: 'Email', accessorKey: 'email', cell: ({ getValue }) => getValue<string | null>() ?? '—' },
      { header: 'Status', accessorKey: 'status', cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1 whitespace-nowrap">
            <Button size="sm" variant="ghost" onClick={() => { setEditing(row.original); setFormOpen(true); }}>Edit</Button>
            {row.original.status === 'active' ? (
              <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50" onClick={() => setDeactivating(row.original)}>Mark inactive</Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setStatusOf.mutate({ employee: row.original, status: 'active' })}>Reactivate</Button>
            )}
          </div>
        ),
      },
    ],
    [names, setStatusOf],
  );

  return (
    <>
      <PageHeader
        title="Employees"
        actions={
          <>
            <Button variant="secondary" onClick={() => setImportOpen(true)}>Import</Button>
            <Button onClick={() => { setEditing(null); setFormOpen(true); }}>Add employee</Button>
          </>
        }
      />
      <Card className="mb-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="Search"><Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Name or employee code" /></Field>
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="all">Everyone</option>
            </Select>
          </Field>
          <Field label="Unit">
            <Select value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option value="">Both units</option>
              {UNITS.map((u) => <option key={u}>{u}</option>)}
            </Select>
          </Field>
        </div>
      </Card>
      <Card className="[&>div:last-child]:p-0">
        <DataTable
          columns={columns}
          data={query.data}
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          emptyTitle="No employees match"
          emptyHint="Add employees one by one or import the HR list from Excel."
        />
      </Card>

      <EmployeeDialog open={formOpen} onClose={() => setFormOpen(false)} employee={editing} everyone={everyone.data ?? []} />
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import employees"
        columns="emp_code, name, designation, department, team, unit (BMD/AES), manager_code, email, phone — existing codes are updated"
        upload={employeesApi.importFile}
      />
      <Dialog
        open={!!deactivating}
        onClose={() => setDeactivating(null)}
        title={`Mark ${deactivating?.name ?? ''} inactive?`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeactivating(null)}>Cancel</Button>
            <Button variant="danger" loading={setStatusOf.isPending} onClick={() => deactivating && setStatusOf.mutate({ employee: deactivating, status: 'inactive' })}>
              Mark inactive
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          They will no longer be able to sign in, and every seat they hold is put under review so you can revoke it or reassign it.
        </p>
      </Dialog>
    </>
  );
}
