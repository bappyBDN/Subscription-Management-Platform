import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { reportsApi } from '@/api/reports';
import { useAuth } from '@/auth/AuthProvider';
import { DataTable, type Columns } from '@/components/DataTable';
import { useToast } from '@/components/Toast';
import { Button, Card, Field, Input, PageHeader, Select } from '@/components/ui';
import { fmtDate, fmtDateTime, label, money, monthStartIso, todayIso } from '@/lib/format';

const REPORTS: { id: string; label: string; adminOnly?: boolean; noRange?: boolean }[] = [
  { id: 'cost-summary', label: 'Cost summary by month' },
  { id: 'cost-by-employee', label: 'Cost by employee' },
  { id: 'requests', label: 'Requests and turnaround' },
  { id: 'register', label: 'Subscription register', adminOnly: true, noRange: true },
  { id: 'cost-by-tool', label: 'Cost by tool', adminOnly: true },
  { id: 'cost-by-unit', label: 'Cost by SBU', adminOnly: true },
  { id: 'cost-by-department', label: 'Cost by department', adminOnly: true },
  { id: 'credential-holders', label: 'Who holds which credential', adminOnly: true, noRange: true },
  { id: 'renewals', label: 'Renewals in the period', adminOnly: true },
];

const MONEY_BDT = /(_bdt|^amount)$/;
const DATE_KEY = /(date|since|until)$/;
const DATETIME_KEY = /_at$/;

type Row = Record<string, unknown>;

function renderCell(key: string, value: unknown, row: Row) {
  if (value === null || value === undefined || value === '') return '—';
  if (key === 'accrued_usd') return money(value as number, 'USD');
  if (key === 'cost_per_cycle' || (key === 'amount' && typeof row.currency === 'string')) return money(value as number, String(row.currency ?? 'BDT'));
  if (MONEY_BDT.test(key)) return money(value as number, 'BDT');
  if (DATETIME_KEY.test(key)) return fmtDateTime(String(value));
  if (DATE_KEY.test(key)) return fmtDate(String(value));
  if (key === 'status' || key === 'type' || key === 'billing_cycle' || key === 'delivered_by') return label(String(value));
  return String(value);
}

export default function Reports() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const available = REPORTS.filter((r) => isAdmin || !r.adminOnly);
  const [kind, setKind] = useState(available[0].id);
  const [from, setFrom] = useState(monthStartIso());
  const [to, setTo] = useState(todayIso());
  const [text, setText] = useState('');
  const [downloading, setDownloading] = useState(false);

  const validRange = !!from && !!to && from <= to;
  const query = useQuery({ queryKey: ['report', kind, from, to], queryFn: () => reportsApi.run(kind, from, to), enabled: validRange });
  const meta = REPORTS.find((r) => r.id === kind);

  // Unit / department / team / tool are filtered here: type any of them in the search box
  const rows = useMemo(() => {
    const all = query.data?.rows ?? [];
    const needle = text.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((row) => Object.values(row).some((v) => String(v ?? '').toLowerCase().includes(needle)));
  }, [query.data, text]);

  const columns = useMemo<Columns<Row>>(() => {
    const first = query.data?.rows[0];
    if (!first) return [];
    return Object.keys(first).map((key) => ({
      id: key,
      header: label(key),
      accessorFn: (row: Row) => {
        const v = row[key];
        return typeof v === 'string' && v !== '' && !Number.isNaN(Number(v)) && (MONEY_BDT.test(key) || key === 'cost_per_cycle') ? Number(v) : v;
      },
      cell: ({ row }: { row: { original: Row } }) => <span className="whitespace-nowrap">{renderCell(key, row.original[key], row.original)}</span>,
    }));
  }, [query.data]);

  const download = async () => {
    setDownloading(true);
    try {
      await reportsApi.download(kind, from, to);
    } catch (err) {
      toast.error(err);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle={isAdmin ? 'Organisation-wide.' : 'Your team only.'}
        actions={<Button loading={downloading} disabled={!validRange} onClick={download}>Export Excel</Button>}
      />
      <Card className="mb-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Report">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              {available.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </Select>
          </Field>
          <Field label="From" hint={meta?.noRange ? 'Not used by this report' : undefined}>
            <Input type="date" value={from} max={to} disabled={meta?.noRange} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="To" error={!validRange ? '"From" must be before "To"' : undefined}>
            <Input type="date" value={to} disabled={meta?.noRange} onChange={(e) => setTo(e.target.value)} />
          </Field>
          <Field label="Filter rows" hint="SBU, department, team, tool, name…">
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type to filter" />
          </Field>
        </div>
      </Card>
      <Card
        className="[&>div:last-child]:p-0"
        title={query.data ? `${meta?.label} · ${rows.length} row(s)${meta?.noRange ? '' : ` · ${fmtDate(query.data.from)} – ${fmtDate(query.data.to)}`}` : meta?.label}
      >
        <DataTable
          columns={columns}
          data={rows}
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => query.refetch()}
          pageSize={25}
          emptyTitle={text ? 'No rows match your filter' : 'No data for this period'}
        />
      </Card>
      {text && <p className="mt-2 text-xs text-slate-500">The Excel export contains every row of the report, not just the filtered ones.</p>}
    </>
  );
}
