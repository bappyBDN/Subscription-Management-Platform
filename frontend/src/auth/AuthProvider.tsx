import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { authApi } from '@/api/auth';
import { setUnauthorizedHandler, tokenStore } from '@/api/client';
import { EmptyState, ErrorState } from '@/components/shared';
import { Skeleton } from '@/components/ui';
import type { Me } from '@/types';

export type Capability = 'dmd' | 'delegate' | 'manager' | 'employee';

interface AuthState {
  token: string | null;
  me: Me | undefined;
  isLoading: boolean;
  error: unknown;
  isDmd: boolean;
  isAdmin: boolean; // DMD Sir or a delegate
  isManager: boolean;
  has: (...allowed: Capability[]) => boolean;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [token, setToken] = useState<string | null>(tokenStore.get());

  const signOut = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    qc.clear();
  }, [qc]);

  const signIn = useCallback(
    (value: string) => {
      qc.clear();
      tokenStore.set(value);
      setToken(value);
    },
    [qc],
  );

  useEffect(() => {
    setUnauthorizedHandler(signOut);
    return () => setUnauthorizedHandler(null);
  }, [signOut]);

  const meQuery = useQuery({ queryKey: ['me'], queryFn: authApi.me, enabled: !!token, staleTime: 5 * 60_000 });

  const value = useMemo<AuthState>(() => {
    const me = token ? meQuery.data : undefined;
    const roles = me?.roles ?? [];
    const isDmd = roles.includes('dmd');
    const isAdmin = isDmd || roles.includes('delegate');
    const isManager = !!me?.is_manager;
    const caps: Record<Capability, boolean> = {
      dmd: isDmd,
      delegate: roles.includes('delegate'),
      manager: isManager,
      employee: !!me,
    };
    return {
      token,
      me,
      isLoading: !!token && meQuery.isLoading,
      error: meQuery.error,
      isDmd,
      isAdmin,
      isManager,
      has: (...allowed) => allowed.some((c) => caps[c]),
      signIn,
      signOut,
    };
  }, [token, meQuery.data, meQuery.isLoading, meQuery.error, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

/** The signed-in user; only use below <RequireAuth>. */
export function useMe(): Me {
  const { me } = useAuth();
  if (!me) throw new Error('useMe used outside a signed-in route');
  return me;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { token, me, isLoading, error } = useAuth();
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (isLoading) {
    return (
      <div className="mx-auto max-w-md space-y-3 p-8">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (error || !me) return <ErrorState error={error} onRetry={() => window.location.reload()} />;
  return <>{children}</>;
}

/** Guards a route; the backend enforces the same rules. */
export function RequireRole({ roles, children }: { roles: Capability[]; children: ReactNode }) {
  const { has } = useAuth();
  if (!has(...roles)) {
    return <EmptyState title="You do not have access to this page" hint="Ask DMD Sir's office if you think you should." />;
  }
  return <>{children}</>;
}
