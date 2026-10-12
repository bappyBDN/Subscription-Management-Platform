import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { useState } from 'react';

import { employeesApi } from '@/api/masters';
import { useDebounced } from '@/hooks';
import type { Employee } from '@/types';

import { Input } from './ui';

/** Search any active employee by name or code (DMD / delegate only — uses the directory endpoint). */
export function EmployeeSearch({
  value,
  onChange,
  placeholder = 'Type a name or employee code…',
}: {
  value: Pick<Employee, 'id' | 'name' | 'emp_code'> | null;
  onChange: (employee: Employee | null) => void;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const q = useDebounced(text.trim());
  const results = useQuery({
    queryKey: ['employee-directory', q],
    queryFn: () => employeesApi.directory(q),
    enabled: q.length >= 2 && !value,
  });

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm">
        <span>
          <span className="font-medium">{value.name}</span> <span className="text-slate-500">({value.emp_code})</span>
        </span>
        <button type="button" aria-label="Clear" className="rounded p-0.5 text-slate-500 hover:bg-slate-200" onClick={() => onChange(null)}>
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} />
      {q.length >= 2 && (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-slate-200 bg-white text-sm shadow-lg">
          {results.isLoading && <li className="px-3 py-2 text-slate-500">Searching…</li>}
          {results.error ? <li className="px-3 py-2 text-red-600">Search failed</li> : null}
          {results.data?.length === 0 && <li className="px-3 py-2 text-slate-500">No active employee matches</li>}
          {results.data?.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left hover:bg-indigo-50"
                onClick={() => {
                  onChange(e);
                  setText('');
                }}
              >
                <span className="font-medium">{e.name}</span>{' '}
                <span className="text-slate-500">
                  {e.emp_code} · {e.team ?? e.department ?? e.unit}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
