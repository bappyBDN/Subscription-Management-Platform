import { Fragment, useEffect, useMemo, useState } from 'react';

import { functionsApi, teamsApi, unitsApi } from '@/api/masters';
import { DeleteButton, EmptyState, MoneyText, QueryState } from '@/components/shared';
import { useToast } from '@/components/Toast';
import { Badge, Button, Card, Checkbox, Dialog, Field, Input, PageHeader, Select } from '@/components/ui';
import { useAction, useAllEmployees, useTeams, useUnits } from '@/hooks';
import { num } from '@/lib/format';
import type { Department, Employee, OrgFunction, Team, Unit } from '@/types';

type Target =
  | { kind: 'unit'; unit: Unit | null }
  | { kind: 'department'; unit: Unit; department: Department | null }
  | { kind: 'function'; unit: Unit; department: Department; fn: OrgFunction | null };

/** One dialog for creating / editing an SBU, a department or a function */
function OrgDialog({ target, onClose, employees }: { target: Target | null; onClose: () => void; employees: Employee[] }) {
  const toast = useToast();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [head, setHead] = useState('');
  const [budget, setBudget] = useState('0');
  const [active, setActive] = useState(true);

  const isUnit = target?.kind === 'unit';
  const existing = !target ? null : target.kind === 'unit' ? target.unit : target.kind === 'department' ? target.department : target.fn;
  const unitId = !target ? null : target.kind === 'unit' ? target.unit?.id ?? null : target.unit.id;

  useEffect(() => {
    if (!target) return;
    setCode(target.kind === 'unit' ? target.unit?.code ?? '' : '');
    setName(existing?.name ?? '');
    setHead(existing?.head_employee_id ? String(existing.head_employee_id) : '');
    setBudget(existing ? String(existing.monthly_budget_bdt) : '0');
    setActive(existing?.active ?? true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  // a head must be an employee of the same SBU
  const candidates = employees.filter((e) => e.status === 'active' && unitId !== null && e.unit_id === unitId);

  const save = useAction(
    async (): Promise<unknown> => {
      const common = {
        name: name.trim(),
        head_employee_id: head ? Number(head) : null,
        monthly_budget_bdt: budget || '0',
        active,
      };
      const t = target!;
      if (t.kind === 'unit') {
        return t.unit ? unitsApi.update(t.unit.id, { ...common, code: code.trim() }) : unitsApi.create({ ...common, code: code.trim() });
      }
      if (t.kind === 'department') {
        return t.department ? unitsApi.updateDepartment(t.department.id, common) : unitsApi.createDepartment({ ...common, unit_id: t.unit.id });
      }
      return t.fn ? functionsApi.update(t.fn.id, common) : functionsApi.create({ ...common, department_id: t.department.id });
    },
    { success: 'Saved', onSuccess: onClose },
  );

  const submit = () => {
    if (!name.trim()) return toast.error('Enter the name');
    if (isUnit && !/^[A-Za-z0-9_-]{1,10}$/.test(code.trim())) return toast.error('The SBU code is 1–10 letters or digits, e.g. A1P');
    if (!(num(budget) >= 0)) return toast.error('The budget cannot be negative');
    save.mutate(undefined);
  };

  let title = '';
  if (target?.kind === 'unit') title = target.unit ? `Edit SBU ${target.unit.code}` : 'Add SBU';
  else if (target?.kind === 'department') title = target.department ? `Edit ${target.department.name}` : `Add department · ${target.unit.code}`;
  else if (target?.kind === 'function') title = target.fn ? `Edit function ${target.fn.name}` : `Add function · ${target.unit.code} / ${target.department.name}`;

  return (
    <Dialog
      open={!!target}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={submit}>Save</Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {isUnit && (
          <Field label="SBU code" required hint="Short, e.g. A1P.">
            <Input value={code} maxLength={10} onChange={(e) => setCode(e.target.value.toUpperCase())} />
          </Field>
        )}
        <Field label="Name" required className={isUnit ? undefined : 'sm:col-span-2'}>
          <Input value={name} maxLength={isUnit ? 120 : 100} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Head" className="sm:col-span-2" hint={unitId === null ? 'Add employees to the SBU first, then choose its head.' : 'Heads may propose new tools and see the cost they are responsible for.'}>
          <Select value={head} disabled={unitId === null} onChange={(e) => setHead(e.target.value)}>
            <option value="">No head</option>
            {candidates.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.emp_code})</option>)}
          </Select>
        </Field>
        <Field label="Monthly budget (BDT)" hint="0 = no budget. Alerts go out at 80% and 100%.">
          <Input type="number" step="0.01" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} />
        </Field>
        <Checkbox className="self-end sm:col-span-1" label="Active" checked={active} onChange={(e) => setActive(e.target.checked)} />
      </div>
    </Dialog>
  );
}

/** Create / edit a team (optional): its name must match the "team" chosen on its members. */
function TeamDialog({ target, onClose, employees }: { target: { unit: Unit; team: Team | null } | null; onClose: () => void; employees: Employee[] }) {
  const toast = useToast();
  const [name, setName] = useState('');
  const [lead, setLead] = useState('');
  const [department, setDepartment] = useState('');
  const [fn, setFn] = useState('');
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!target) return;
    setName(target.team?.name ?? '');
    setDepartment(target.team?.department_id ? String(target.team.department_id) : '');
    setFn(target.team?.function_id ? String(target.team.function_id) : '');
    setLead(target.team?.lead_employee_id ? String(target.team.lead_employee_id) : '');
    setActive(target.team?.active ?? true);
  }, [target]);

  const inUnit = employees.filter((e) => e.status === 'active' && e.unit_id === target?.unit.id);
  const memberCount = inUnit.filter((e) => (e.team ?? '').trim().toLowerCase() === name.trim().toLowerCase()).length;
  const dept = target?.unit.departments.find((d) => String(d.id) === department);
  const functions = (dept?.functions ?? []).filter((f) => f.active || String(f.id) === fn);

  const save = useAction(
    async (): Promise<unknown> => {
      const body = {
        name: name.trim(),
        department_id: department ? Number(department) : null,
        function_id: department && fn ? Number(fn) : null,
        lead_employee_id: lead ? Number(lead) : null,
        active,
      };
      return target!.team ? teamsApi.update(target!.team.id, body) : teamsApi.create({ ...body, unit_id: target!.unit.id });
    },
    { success: 'Saved', onSuccess: onClose },
  );

  return (
    <Dialog
      open={!!target}
      onClose={onClose}
      title={target?.team ? `Edit team ${target.team.name}` : `Add team · ${target?.unit.code ?? ''}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => (name.trim() ? save.mutate(undefined) : toast.error('Enter the team name'))}>Save</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field
          label="Team name"
          required
          hint={name.trim() ? `${memberCount} employee(s) of ${target?.unit.code} are in this team.` : 'Employees are put in the team from the employee form.'}
        >
          <Input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Department" hint="Optional">
            <Select value={department} onChange={(e) => { setDepartment(e.target.value); setFn(''); }}>
              <option value="">No department</option>
              {target?.unit.departments.filter((d) => d.active || String(d.id) === department).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          </Field>
          <Field label="Function" hint="Optional">
            <Select value={fn} disabled={!department} onChange={(e) => setFn(e.target.value)}>
              <option value="">No function</option>
              {functions.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Team leader" hint="Sees the team's cost on their dashboard.">
          <Select value={lead} onChange={(e) => setLead(e.target.value)}>
            <option value="">No leader</option>
            {inUnit.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.emp_code}){e.team ? ` · ${e.team}` : ''}</option>)}
          </Select>
        </Field>
        <Checkbox label="Active" checked={active} onChange={(e) => setActive(e.target.checked)} />
      </div>
    </Dialog>
  );
}

export default function Units() {
  const query = useUnits(true);
  const teams = useTeams(true);
  const [teamTarget, setTeamTarget] = useState<{ unit: Unit; team: Team | null } | null>(null);
  const everyone = useAllEmployees();
  const [target, setTarget] = useState<Target | null>(null);
  const names = useMemo(() => new Map(everyone.data?.map((e) => [e.id, `${e.name} (${e.emp_code})`])), [everyone.data]);
  const headName = (id: number | null) => (id ? names.get(id) ?? `Employee #${id}` : 'No head');
  const budget = (value: number | string) => (num(value) > 0 ? <MoneyText amount={value} /> : <span className="text-slate-400">No budget</span>);

  return (
    <>
      <PageHeader
        title="SBUs, departments & functions"
        subtitle="SBU → Department → Function (→ optional Team). They own subscriptions and carry their cost."
        actions={<Button onClick={() => setTarget({ kind: 'unit', unit: null })}>Add SBU</Button>}
      />
      <QueryState
        query={query}
        isEmpty={(d) => d.length === 0}
        empty={<Card><EmptyState title="No SBUs yet" hint="Create the SBUs first (for example A1 Polymer), then their departments and functions." /></Card>}
      >
        {(units) => (
          <div className="space-y-4">
            {units.map((u) => {
              const unitTeams = (teams.data ?? []).filter((t) => t.unit_id === u.id);
              return (
                <Card
                  key={u.id}
                  title={
                    <span className="flex flex-wrap items-center gap-2">
                      {u.code} <span className="font-normal text-slate-500">{u.name}</span>
                      {!u.active && <Badge tone="red">Inactive</Badge>}
                    </span>
                  }
                  actions={
                    <span className="flex flex-wrap gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setTarget({ kind: 'unit', unit: u })}>Edit SBU</Button>
                      <Button size="sm" variant="secondary" onClick={() => setTarget({ kind: 'department', unit: u, department: null })}>Add department</Button>
                      <Button size="sm" variant="secondary" onClick={() => setTeamTarget({ unit: u, team: null })}>Add team</Button>
                      <DeleteButton
                        what={`SBU ${u.code}`}
                        onDelete={() => unitsApi.remove(u.id)}
                        note={<p>Its empty departments, functions and teams are deleted with it. An SBU that still has employees or subscriptions cannot be deleted.</p>}
                      />
                    </span>
                  }
                >
                  <p className="mb-3 text-sm text-slate-600">
                    Head: <span className="font-medium text-slate-800">{headName(u.head_employee_id)}</span> · Monthly budget: {budget(u.monthly_budget_bdt)}
                  </p>
                  {u.departments.length === 0 ? (
                    <p className="text-sm text-slate-500">No departments yet.</p>
                  ) : (
                    <div className="-mx-4 overflow-x-auto">
                      <table className="min-w-full divide-y divide-slate-200 text-sm">
                        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                          <tr>
                            <th className="px-4 py-2">Department / function</th><th className="px-3 py-2">Head</th>
                            <th className="px-3 py-2 text-right">Monthly budget</th><th className="px-3 py-2" />
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {u.departments.map((d) => (
                            <Fragment key={d.id}>
                              <tr className="bg-white">
                                <td className="whitespace-nowrap px-4 py-2 font-medium text-slate-800">
                                  {d.name} {!d.active && <Badge tone="red">Inactive</Badge>}
                                </td>
                                <td className="whitespace-nowrap px-3 py-2">{headName(d.head_employee_id)}</td>
                                <td className="whitespace-nowrap px-3 py-2 text-right">{budget(d.monthly_budget_bdt)}</td>
                                <td className="px-3 py-2 text-right">
                                  <span className="inline-flex gap-1 whitespace-nowrap">
                                    <Button size="sm" variant="ghost" onClick={() => setTarget({ kind: 'function', unit: u, department: d, fn: null })}>Add function</Button>
                                    <Button size="sm" variant="ghost" onClick={() => setTarget({ kind: 'department', unit: u, department: d })}>Edit</Button>
                                    <DeleteButton what={`department ${d.name}`} onDelete={() => unitsApi.removeDepartment(d.id)} />
                                  </span>
                                </td>
                              </tr>
                              {(d.functions ?? []).map((f) => (
                                <tr key={`f${f.id}`} className="bg-slate-50/50">
                                  <td className="whitespace-nowrap py-2 pl-8 pr-4 text-slate-700">
                                    <span className="text-slate-400">↳</span> {f.name}
                                    <span className="ml-2 text-xs text-slate-500">{f.members} member(s)</span>
                                    {!f.active && <Badge tone="red">Inactive</Badge>}
                                  </td>
                                  <td className="whitespace-nowrap px-3 py-2">{f.head_name ?? headName(f.head_employee_id)}</td>
                                  <td className="whitespace-nowrap px-3 py-2 text-right">{budget(f.monthly_budget_bdt)}</td>
                                  <td className="px-3 py-2 text-right">
                                    <span className="inline-flex gap-1">
                                      <Button size="sm" variant="ghost" onClick={() => setTarget({ kind: 'function', unit: u, department: d, fn: f })}>Edit</Button>
                                      <DeleteButton what={`function ${f.name}`} onDelete={() => functionsApi.remove(f.id)} />
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <div className="mt-4 border-t border-slate-100 pt-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Teams (optional)</p>
                    {unitTeams.length === 0 ? (
                      <p className="text-sm text-slate-500">No teams. Add one only when a smaller team inside a function needs its own cost view.</p>
                    ) : (
                      <ul className="divide-y divide-slate-100">
                        {unitTeams.map((t) => (
                          <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                            <span>
                              <span className="font-medium text-slate-800">{t.name}</span> {!t.active && <Badge tone="red">Inactive</Badge>}
                              <span className="ml-2 text-slate-500">
                                {[t.department_name, t.function_name].filter(Boolean).join(' / ')}
                                {t.department_name ? ' · ' : ''}Leader: {t.lead_name ?? 'none'} · {t.members} member(s)
                              </span>
                            </span>
                            <span className="flex gap-1">
                              <Button size="sm" variant="ghost" onClick={() => setTeamTarget({ unit: u, team: t })}>Edit</Button>
                              <DeleteButton
                                what={`team ${t.name}`}
                                onDelete={() => teamsApi.remove(t.id)}
                                note={<p>Members keep their team name; only the team record goes.</p>}
                              />
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </QueryState>
      <OrgDialog target={target} onClose={() => setTarget(null)} employees={everyone.data ?? []} />
      <TeamDialog target={teamTarget} onClose={() => setTeamTarget(null)} employees={everyone.data ?? []} />
    </>
  );
}
