# SMP Frontend Specification (React)

Subscription Management Platform for BMD/AES — web client.
It consumes the API described in [BACKEND.md](./BACKEND.md). Screens and stories come from the PRD.

---

## 1. Stack

| Concern | Choice |
| --- | --- |
| Build | Vite + React 18 + TypeScript |
| Routing | React Router v6 |
| Server state | TanStack Query (React Query) |
| HTTP | Axios instance with bearer token + 401 → logout interceptor |
| Forms | React Hook Form + Zod schemas |
| UI kit | Tailwind CSS + shadcn/ui components (Button, Dialog, Table, Tabs, Badge, Toast) |
| Charts | Recharts |
| Tables | TanStack Table (sorting, filters, pagination) |
| Dates | date-fns, displayed in Asia/Dhaka |
| Tests | Vitest + React Testing Library; Playwright for the main flow |

## 2. Folder structure

```
frontend/
├── src/
│   ├── main.tsx, App.tsx
│   ├── api/            # axios client + one module per backend router
│   ├── auth/           # AuthProvider, useAuth, RequireRole
│   ├── components/     # shared UI: StatusBadge, MoneyText, CostCard, DataTable, EmptyState
│   ├── layouts/        # AppLayout (sidebar + topbar + notification bell)
│   ├── pages/          # one folder per screen (S01–S14)
│   ├── hooks/          # useDashboard, useRequests, ...
│   ├── lib/            # formatters (BDT, USD, dates), constants (statuses, roles)
│   └── types/          # API types mirrored from backend schemas
├── .env.example        # VITE_API_URL=http://localhost:8000/api
└── package.json
```

## 3. Roles and navigation

`/auth/me` returns `roles` and `is_manager`. The sidebar shows only allowed items:

| Menu item | Route | Employee | Manager | Delegate | DMD |
| --- | --- | --- | --- | --- | --- |
| Dashboard | `/` | own | team | org | org |
| New request | `/requests/new` | ✓ | ✓ | ✓ | ✓ |
| My requests | `/requests` | ✓ | ✓ | ✓ | ✓ |
| My subscriptions | `/my/subscriptions` | ✓ | ✓ | ✓ | ✓ |
| Handover tasks | `/my/handover-tasks` | if nominated | if nominated | ✓ | ✓ |
| Approvals | `/approvals` | — | ✓ | — | ✓ |
| Subscriptions | `/subscriptions` | — | — | ✓ | ✓ |
| Card charges | `/charges` | — | — | ✓ | ✓ |
| Reports | `/reports` | — | team | ✓ | ✓ |
| Masters | `/masters/employees`, `/vendors`, `/cards`, `/users` | — | — | ✓ | ✓ |
| Settings · Audit log | `/settings`, `/audit` | — | — | audit | ✓ |

`<RequireRole roles={[...]}>` guards each route; the backend enforces the same rules.

## 4. Screens

### S01 Login (`/login`)
- Employee code or email + password.
- If the response has `otp_required`, show a 6-digit OTP step (resend after 60 s).
- Lockout message after 5 failed attempts.

### S02 Dashboard (`/`)
DMD / delegate view:
- **Row 1 — cost cards:** Today · This week · This month (progress bar vs budget) · This year (with run-rate). Toggle **Accrued / Paid** and **BDT / USD**. Estimated values carry an "est." tag.
- **Row 2 — status cards:** Active subscriptions (seats used/total) · Pending approvals (oldest days, link to `/approvals`) · Renewals in 7 days · Pending handovers.
- **Charts:** daily spend line (30 days), monthly bars (12 months), spend by tool (horizontal bar), spend by unit/department (bar).
- **Table:** next 10 renewals.

Manager view: same widgets filtered to the team. Employee view: "My tools" cards + "My open requests".

### S03 New request (`/requests/new`)
Four sections in one page:
1. **Your details** — read-only card from `/auth/me` (name, ID, designation, department, team, unit, reporting manager).
2. **What you need** — tool (searchable select from `/vendors`, plus "Other" → name + URL), plan (from vendor plans, editable), request type, seats, duration (1/3/6/12 months/open), needed-from date.
3. **Why** — reason (min 30 characters, counter shown), expected use.
4. **Cost preview** — calls `POST /requests/estimate` on change; shows monthly and yearly in BDT and USD.

If `/subscriptions/shared-seats?vendor_id=` returns free seats, show a banner: *"There is a free seat on <plan>. Request the shared seat instead?"*.
Submit → toast with the request number → redirect to the request detail.

### S04 My requests (`/requests`, `/requests/:id`)
- List: number, tool, type, status badge, submitted date, last update.
- Detail: request info, timeline of approvals and comments, handover panel (see S05), actions: **Withdraw** (before approval), **Edit & resubmit** (when `info_needed`).

### S05 My subscriptions (`/my/subscriptions`)
Cards per active tool: plan, renewal date, handover method.
- Vault: **Reveal credential** → OTP dialog → secret shown for 60 s with copy button and countdown, then hidden.
- Appointment: propose date/time (if not confirmed), show confirmed slot and location.
- Colleague: collector name + note.
- **I received access** button while status is `handover_pending`.
- **Request renewal** / **Cancel** buttons prefill S03.

### S06 Approvals inbox (`/approvals`)
- Tabs: *Waiting for me* · *On hold* (DMD) · *Decided by me*.
- Columns: number, employee (name, ID, team), tool/plan, monthly cost, waiting days (red when > SLA).
- DMD: checkbox column + **Bulk approve**.
- Mobile layout: cards with Approve / Reject buttons — two taps from a notification link.

### S07 Request decision (`/approvals/:id`)
Left: requester card, request details, reason, cost estimate, requester's current tools, timeline.
Right panel: buttons for the current step (Recommend / Reject / Ask info for managers; Approve / Reject / Hold / Ask info / Resume for DMD). Reject and Ask info require a comment. DMD can edit plan, seats and duration before Approve. Urgent override (manager step skipped) asks for a reason.

### S08 Handover setup (`/requests/:id/handover`)
Shown to DMD/delegate after approval. Pick or create the subscription (existing seat or new), then three tabs:

| Tab | Fields |
| --- | --- |
| A · Secure vault | login email, password / API key (masked input with show toggle), login URL, notes |
| B · Come to DMD Sir | requester's proposed slot (read-only), confirm or set date/time, location, note |
| C · Via colleague | collector (employee search), note to requester, note to collector, due date |

### S09 Handover tasks (`/my/handover-tasks`)
For nominated collectors: requester, tool, note, due date, **Mark handed over**.

### S10 Subscription register (`/subscriptions`, `/subscriptions/:id`)
- Filters: status, vendor, unit, department, "renewal within N days".
- Columns: tool, plan, type, seats used/total, cost/cycle, currency, cycle, next renewal, card (•••• last4), status.
- Row actions: edit, assign user, record charge, cancel.
- **Import** (xlsx/csv) with a preview table and error rows before saving.
- Detail page: assignments, charges history, linked requests.

### S11 Card charges (`/charges`)
List with filters (month, card, subscription, expected/actual, reconciled). Form: date, subscription, card, amount, currency, FX rate (prefilled), bank fee — **BDT total computed live** and read-only. Receipt upload.

### S12 Reports (`/reports`)
Report picker + filters (date range, unit, department, team, vendor). Table preview, **Export Excel** button (`format=xlsx`).

### S13 Masters (`/masters/*`)
CRUD tables for employees (with import and "mark inactive"), users/roles, vendors + plans, cards.

### S14 Settings & audit (`/settings`, `/audit`)
Settings form (week start, year start month, monthly budget, default FX rate, approval SLA, urgent override). Audit log table with user, action, entity, time, IP; filters by user/action/date.

## 5. Shared UI rules

- **Status badge colours:** pending_* = amber, on_hold = grey, info_needed = blue, rejected/withdrawn = red, approved/handover_pending = indigo, active = green, ended = slate.
- **Money:** `৳ 12,345.00` for BDT, `$ 20.00` for USD; estimated values in italics with "est.".
- **Dates:** `12 Oct 2026`; datetimes `12 Oct 2026, 3:30 PM` (Asia/Dhaka).
- Secrets are never kept in React Query cache or localStorage; the reveal response lives in component state and is cleared on unmount or after 60 s.
- Access token kept in memory + `sessionStorage` (not `localStorage`); logout clears both.
- Every list has empty, loading (skeleton) and error states.
- Responsive down to 360 px; the approvals inbox and dashboard are mobile-first for DMD Sir.

## 6. Notifications

Bell icon in the top bar polls `/notifications` every 60 s; unread count badge; clicking an item opens its `link` and marks it read.

## 7. Build order

1. Auth (login + OTP), layout, role-aware navigation.
2. Request form → my requests → approvals inbox → decision page.
3. Handover setup, my subscriptions (reveal, propose slot, confirm receipt), handover tasks.
4. Subscription register, card charges, masters.
5. Dashboard and reports.
6. Settings, audit log, polish, Playwright test of the full flow.

## 8. Running locally

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_URL=http://localhost:8000/api
npm run dev              # http://localhost:5173
```
