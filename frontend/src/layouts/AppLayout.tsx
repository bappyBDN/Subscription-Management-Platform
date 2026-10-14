import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bell,
  BookUser,
  Building2,
  CheckSquare,
  ClipboardList,
  CreditCard,
  FileBarChart,
  FilePlus2,
  HandHelping,
  History,
  KeyRound,
  LayoutDashboard,
  Layers,
  LogOut,
  Menu,
  PackageCheck,
  Receipt,
  Settings as SettingsIcon,
  ShieldCheck,
  Store,
  Users as UsersIcon,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { authApi } from '@/api/auth';
import { handoverApi, requestsApi } from '@/api/requests';
import { notificationsApi } from '@/api/system';
import { useAuth, useMe, type Capability } from '@/auth/AuthProvider';
import { useToast } from '@/components/Toast';
import { Button, Dialog, Field, Input, cn } from '@/components/ui';
import { useAction } from '@/hooks';
import { fmtDateTime } from '@/lib/format';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  roles?: Capability[];
  end?: boolean;
  /** key into the sidebar's red counters */
  badge?: 'handover' | 'tasks';
}

const NAV: { heading?: string; items: NavItem[] }[] = [
  {
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/requests/new', label: 'New request', icon: FilePlus2, end: true },
      { to: '/requests', label: 'My requests', icon: ClipboardList, end: true },
      { to: '/my/subscriptions', label: 'My subscriptions', icon: KeyRound },
      { to: '/my/handover-tasks', label: 'Handover tasks', icon: HandHelping, badge: 'tasks' },
      { to: '/requests?scope=handover', label: 'Handovers', icon: PackageCheck, roles: ['dmd', 'delegate'], badge: 'handover' },
      { to: '/approvals', label: 'Approvals', icon: CheckSquare, roles: ['manager', 'dmd'] },
    ],
  },
  {
    heading: 'Register',
    items: [
      { to: '/subscriptions', label: 'Subscriptions', icon: Layers, roles: ['dmd', 'delegate'] },
      { to: '/charges', label: 'Card charges', icon: Receipt, roles: ['dmd', 'delegate'] },
      { to: '/reports', label: 'Reports', icon: FileBarChart, roles: ['manager', 'dmd', 'delegate'] },
    ],
  },
  {
    heading: 'Masters',
    items: [
      { to: '/masters/units', label: 'SBUs & departments', icon: Building2, roles: ['dmd', 'delegate'] },
      { to: '/masters/employees', label: 'Employees', icon: BookUser, roles: ['dmd', 'delegate'] },
      { to: '/masters/vendors', label: 'Tools & plans', icon: Store, roles: ['dmd', 'delegate'] },
      { to: '/masters/cards', label: 'Cards', icon: CreditCard, roles: ['dmd', 'delegate'] },
      { to: '/masters/users', label: 'Users & roles', icon: UsersIcon, roles: ['dmd', 'delegate'] },
    ],
  },
  {
    heading: 'System',
    items: [
      { to: '/settings', label: 'Settings', icon: SettingsIcon, roles: ['dmd'] },
      { to: '/audit', label: 'Audit log', icon: History, roles: ['dmd', 'delegate'] },
    ],
  },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { has, isAdmin } = useAuth();
  const location = useLocation();
  // "Handover tasks" is shown to admins always, to others only when they are a nominated collector
  const tasks = useQuery({ queryKey: ['handover-tasks'], queryFn: handoverApi.tasks, enabled: !isAdmin, refetchInterval: 60_000 });
  const showTasks = isAdmin || (tasks.data?.length ?? 0) > 0;
  // approved requests waiting in the handover pipeline (same query as the "Needs handover" tab)
  const handovers = useQuery({
    queryKey: ['requests', 'handover', ''],
    queryFn: () => requestsApi.list('handover'),
    enabled: isAdmin,
    refetchInterval: 60_000,
  });
  const counts = {
    handover: handovers.data?.length ?? 0,
    tasks: tasks.data?.filter((t) => !t.handed_over_at).length ?? 0,
  };
  const here = location.pathname + location.search;
  const queryLinks = NAV.flatMap((g) => g.items).filter((i) => i.to.includes('?')).map((i) => i.to);

  return (
    <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4" aria-label="Main">
      {NAV.map((group, i) => {
        const items = group.items.filter(
          (item) => (!item.roles || has(...item.roles)) && (item.to !== '/my/handover-tasks' || showTasks),
        );
        if (!items.length) return null;
        return (
          <div key={group.heading ?? i}>
            {group.heading && (
              <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{group.heading}</p>
            )}
            <ul className="space-y-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={onNavigate}
                    className={({ isActive }) => {
                      // links with a ?query are active only on that exact view, and then their plain path is not
                      const active = item.to.includes('?') ? here === item.to : isActive && !queryLinks.includes(here);
                      return cn(
                        'flex items-center gap-2.5 rounded-md px-2 py-2 text-sm font-medium',
                        active ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                      );
                    }}
                  >
                    <item.icon className="h-4 w-4 shrink-0" aria-hidden />
                    {item.label}
                    {item.badge && counts[item.badge] > 0 && (
                      <span
                        className="ml-auto min-w-[20px] rounded-full bg-red-600 px-1.5 text-center text-[11px] font-semibold leading-5 text-white"
                        aria-label={`${counts[item.badge]} waiting`}
                      >
                        {counts[item.badge] > 99 ? '99+' : counts[item.badge]}
                      </span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function NotificationBell() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const query = useQuery({ queryKey: ['notifications'], queryFn: notificationsApi.list, refetchInterval: 60_000 });

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] });
  const unread = query.data?.unread ?? 0;
  const items = query.data?.items ?? [];

  const openItem = async (id: number, link: string | null, isRead: boolean) => {
    setOpen(false);
    if (!isRead) {
      try {
        await notificationsApi.markRead(id);
      } finally {
        void refresh();
      }
    }
    if (link) navigate(link);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}
        className="relative rounded-md p-2 text-slate-600 hover:bg-slate-100"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute right-0.5 top-0.5 min-w-[18px] rounded-full bg-red-600 px-1 text-center text-[11px] font-semibold leading-[18px] text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[min(22rem,calc(100vw-1.5rem))] rounded-lg border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                className="text-xs font-medium text-indigo-600 hover:underline"
                onClick={async () => {
                  await notificationsApi.markAllRead();
                  void refresh();
                }}
              >
                Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
            {query.isLoading && <li className="px-3 py-4 text-sm text-slate-500">Loading…</li>}
            {query.error ? <li className="px-3 py-4 text-sm text-red-600">Could not load notifications</li> : null}
            {!query.isLoading && !query.error && items.length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-slate-500">No notifications yet</li>
            )}
            {items.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => openItem(n.id, n.link, !!n.read_at)}
                  className={cn('block w-full px-3 py-2 text-left hover:bg-slate-50', !n.read_at && 'bg-indigo-50/60')}
                >
                  <span className="block text-sm font-medium text-slate-800">{n.title}</span>
                  {n.body && <span className="mt-0.5 line-clamp-2 block text-xs text-slate-600">{n.body}</span>}
                  <span className="mt-0.5 block text-[11px] text-slate-400">{fmtDateTime(n.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ChangePasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const save = useAction(() => authApi.changePassword(current, next), {
    success: 'Password changed',
    onSuccess: () => {
      setCurrent('');
      setNext('');
      onClose();
    },
  });
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Change password"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            loading={save.isPending}
            onClick={() => (next.length < 8 ? toast.error('The new password needs at least 8 characters') : save.mutate(undefined))}
          >
            Change password
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Current password">
          <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password" hint="At least 8 characters">
          <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
      </div>
    </Dialog>
  );
}

export default function AppLayout() {
  const me = useMe();
  const { signOut, isDmd, isAdmin, isManager } = useAuth();
  const location = useLocation();
  const [drawer, setDrawer] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);

  useEffect(() => setDrawer(false), [location.pathname]);

  const roleLabel = isDmd ? 'DMD' : isAdmin ? 'Delegate' : isManager ? 'Manager' : 'Employee';
  const brand = (
    <div className="flex items-center gap-2 px-4 py-4">
      <ShieldCheck className="h-6 w-6 text-indigo-600" aria-hidden />
      <div>
        <p className="text-sm font-bold leading-tight text-slate-900">SMP</p>
        <p className="text-[11px] leading-tight text-slate-500">Subscription Management</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:flex">
      {/* desktop sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex lg:h-screen lg:sticky lg:top-0">
        {brand}
        <Sidebar />
      </aside>

      {/* mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 max-w-[85vw] flex-col bg-white shadow-xl">
            <div className="flex items-center justify-between pr-2">
              {brand}
              <button type="button" aria-label="Close menu" onClick={() => setDrawer(false)} className="rounded p-2 text-slate-500 hover:bg-slate-100">
                <X className="h-5 w-5" />
              </button>
            </div>
            <Sidebar onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 sm:px-6">
          <button type="button" aria-label="Open menu" onClick={() => setDrawer(true)} className="rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden">
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-sm font-semibold text-slate-900 lg:hidden">SMP</span>
          <div className="ml-auto flex items-center gap-1 sm:gap-2">
            <NotificationBell />
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium leading-tight text-slate-900">{me.name}</p>
              <p className="text-[11px] leading-tight text-slate-500">
                {me.emp_code} · {roleLabel}
              </p>
            </div>
            <button type="button" title="Change password" aria-label="Change password" onClick={() => setPasswordOpen(true)} className="rounded-md p-2 text-slate-600 hover:bg-slate-100">
              <KeyRound className="h-5 w-5" />
            </button>
            <button type="button" title="Sign out" aria-label="Sign out" onClick={signOut} className="rounded-md p-2 text-slate-600 hover:bg-slate-100">
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-3 py-4 sm:px-6 sm:py-6">
          <Outlet />
        </main>
      </div>
      <ChangePasswordDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} />
    </div>
  );
}
