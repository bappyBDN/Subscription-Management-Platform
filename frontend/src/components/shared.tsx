import { AlertTriangle, Inbox } from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { errorMessage } from '@/api/client';
import { STATUS_LABEL, STATUS_TONE } from '@/lib/constants';
import { label, money } from '@/lib/format';
import type { Num } from '@/types';

import { useAction } from '@/hooks';

import { Badge, Button, Dialog, Skeleton, cn } from './ui';

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? 'slate'}>{STATUS_LABEL[status] ?? label(status)}</Badge>;
}

/** ৳ 12,345.00 — estimated values in italics with "est." */
export function MoneyText({
  amount,
  currency = 'BDT',
  estimated,
  className,
}: {
  amount: Num | null | undefined;
  currency?: string;
  estimated?: boolean;
  className?: string;
}) {
  return (
    <span className={cn('whitespace-nowrap tabular-nums', estimated && 'italic', className)}>
      {money(amount, currency)}
      {estimated && <span className="ml-1 text-xs font-normal text-slate-500">est.</span>}
    </span>
  );
}

export function CostCard({
  title,
  amount,
  currency,
  estimated,
  loading,
  children,
}: {
  title: string;
  amount?: Num | null;
  currency: string;
  estimated?: boolean;
  loading?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-32" />
      ) : (
        <p className="mt-1 text-2xl font-semibold text-slate-900">
          <MoneyText amount={amount} currency={currency} estimated={estimated} />
        </p>
      )}
      {children && <div className="mt-2 text-xs text-slate-500">{children}</div>}
    </div>
  );
}

export function StatCard({
  title,
  value,
  loading,
  children,
}: {
  title: string;
  value: ReactNode;
  loading?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      {loading ? <Skeleton className="mt-2 h-7 w-16" /> : <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>}
      {children && <div className="mt-2 text-xs text-slate-500">{children}</div>}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
      <Inbox className="h-8 w-8 text-slate-300" aria-hidden />
      <p className="mt-2 text-sm font-medium text-slate-700">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-xs text-slate-500">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
      <AlertTriangle className="h-8 w-8 text-red-400" aria-hidden />
      <p className="mt-2 text-sm font-medium text-slate-700">{errorMessage(error, 'Could not load this')}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

/** Loading / error / empty wrapper for non-table lists */
export function QueryState<T>({
  query,
  empty,
  isEmpty,
  children,
}: {
  query: { isLoading: boolean; error: unknown; data: T | undefined; refetch: () => unknown };
  empty?: ReactNode;
  isEmpty?: (data: T) => boolean;
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading) return <LoadingRows />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (query.data === undefined) return null;
  if (empty && isEmpty?.(query.data)) return <>{empty}</>;
  return <>{children(query.data)}</>;
}

/** Red "Delete" button with its own confirmation. The server refuses records that have history and says why. */
export function DeleteButton({ what, onDelete, onDeleted, label: text = 'Delete', size = 'sm', note }: {
  what: string;
  onDelete: () => Promise<unknown>;
  onDeleted?: () => void;
  label?: string;
  size?: 'sm' | 'md';
  note?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const remove = useAction(onDelete, {
    success: `${what} deleted`,
    onSuccess: () => {
      setOpen(false);
      onDeleted?.();
    },
  });
  return (
    <>
      <Button size={size} variant="ghost" className="text-red-700 hover:bg-red-50" onClick={() => setOpen(true)}>{text}</Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={`Delete ${what}?`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate(undefined)}>Delete permanently</Button>
          </>
        }
      >
        <div className="space-y-2 text-sm text-slate-700">
          <p><strong>{what}</strong> will be removed for good. This cannot be undone; the deletion is kept in the audit log.</p>
          {note}
          <p className="text-xs text-slate-500">
            Only records without history can be deleted. If it has requests, seats, charges or activity, you will be told what is in
            the way — deactivate it instead.
          </p>
        </div>
      </Dialog>
    </>
  );
}

