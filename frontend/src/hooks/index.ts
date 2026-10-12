import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { cardsApi, employeesApi, vendorsApi } from '@/api/masters';
import { requestsApi } from '@/api/requests';
import { subscriptionsApi } from '@/api/subscriptions';
import { useToast } from '@/components/Toast';

export function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** Mutation that toasts the result and refreshes every list on success. */
export function useAction<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  options: { success?: string | ((result: TResult) => string); onSuccess?: (result: TResult) => void } = {},
) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      const text = typeof options.success === 'function' ? options.success(result) : options.success;
      if (text) toast.success(text);
      void qc.invalidateQueries();
      options.onSuccess?.(result);
    },
    onError: (err) => toast.error(err),
  });
}

export const useVendors = (includeInactive = false) =>
  useQuery({ queryKey: ['vendors', includeInactive], queryFn: () => vendorsApi.list(includeInactive) });

export const useCards = () => useQuery({ queryKey: ['cards'], queryFn: cardsApi.list });

export const useAllEmployees = () =>
  useQuery({ queryKey: ['employees', 'all'], queryFn: () => employeesApi.list({ status: 'all' }) });

export const useRequest = (id: number) =>
  useQuery({ queryKey: ['request', id], queryFn: () => requestsApi.get(id), enabled: Number.isFinite(id) });

export const useMySubscriptions = () => useQuery({ queryKey: ['my-subscriptions'], queryFn: subscriptionsApi.mine });

export const useSubscriptions = (filters: Record<string, unknown> = {}, enabled = true) =>
  useQuery({ queryKey: ['subscriptions', filters], queryFn: () => subscriptionsApi.list(filters), enabled });
