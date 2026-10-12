import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import { EmptyState, ErrorState, LoadingRows } from './shared';
import { Button, cn } from './ui';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Columns<T> = ColumnDef<T, any>[];

interface Props<T> {
  columns: Columns<T>;
  data: T[] | undefined;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyHint?: string;
  emptyAction?: ReactNode;
  onRowClick?: (row: T) => void;
  pageSize?: number;
  rowClassName?: (row: T) => string | undefined;
}

export function DataTable<T>({
  columns,
  data,
  isLoading,
  error,
  onRetry,
  emptyTitle = 'Nothing here yet',
  emptyHint,
  emptyAction,
  onRowClick,
  pageSize = 20,
  rowClassName,
}: Props<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  // The table caches each row's accessor values per data array. Columns often read lookups that load
  // later (subscription or employee names), so a new array is handed over whenever the columns change.
  const rows = useMemo(() => [...(data ?? [])], [data, columns]);
  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  if (isLoading) return <LoadingRows />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!data?.length) return <EmptyState title={emptyTitle} hint={emptyHint} action={emptyAction} />;

  const pages = table.getPageCount();
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sortable = header.column.getCanSort();
                  const dir = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500"
                    >
                      {header.isPlaceholder ? null : sortable ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className="inline-flex items-center gap-1 hover:text-slate-800"
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {dir === 'asc' ? (
                            <ArrowUp className="h-3 w-3" />
                          ) : dir === 'desc' ? (
                            <ArrowDown className="h-3 w-3" />
                          ) : (
                            <ChevronsUpDown className="h-3 w-3 opacity-40" />
                          )}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={cn(onRowClick && 'cursor-pointer hover:bg-slate-50', rowClassName?.(row.original))}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2 align-middle text-slate-700">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-between gap-2 border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {pages} · {data.length} rows
          </span>
          <span className="flex gap-1">
            <Button variant="secondary" size="sm" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>
              Previous
            </Button>
            <Button variant="secondary" size="sm" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>
              Next
            </Button>
          </span>
        </div>
      )}
    </div>
  );
}
