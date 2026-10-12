# SMP Backend Specification (FastAPI)

Subscription Management Platform for BMD/AES — backend service.
Source documents: the BRD and PRD for this system. This file turns them into an implementation spec for the FastAPI service in `/backend`.

---

## 1. Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.11+ |
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.0 (sync, typed `Mapped[...]` models) |
| Database | PostgreSQL 14+ via psycopg 3; SQLite for tests |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | JWT (PyJWT) bearer tokens + email OTP for 2FA and vault reveal |
| Password hashing | bcrypt |
| Vault encryption | AES-256-GCM (`cryptography`), key from env, never in DB |
| Excel import/export | openpyxl |
| Jobs | CLI commands run by cron (`python -m app.jobs <job>`) |
| Tests | pytest + FastAPI TestClient |

## 2. Folder structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, routers, CORS
│   ├── core/
│   │   ├── config.py           # Settings from .env
│   │   ├── security.py         # password hashing, JWT
│   │   ├── crypto.py           # AES-GCM vault encrypt/decrypt
│   │   └── deps.py             # get_db, current user, role guards
│   ├── db/
│   │   ├── base.py             # DeclarativeBase
│   │   └── session.py          # engine + SessionLocal
│   ├── models/                 # SQLAlchemy models (one file per area)
│   ├── schemas/                # Pydantic request/response models
│   ├── services/
│   │   ├── cost.py             # pure cost engine (accrued / paid)
│   │   ├── workflow.py         # request state machine (pure)
│   │   ├── audit.py            # audit log writer
│   │   ├── notify.py           # in-app + email notifications
│   │   ├── otp.py              # OTP issue / verify
│   │   └── mailer.py           # SMTP (console fallback in dev)
│   ├── api/routers/            # one router per module
│   └── jobs/                   # cron jobs
├── alembic/                    # migrations
├── tests/
├── scripts/seed.py             # demo data
├── requirements.txt
└── .env.example
```

## 3. Roles and scoping

Roles are stored on `users.roles` as a comma list: `dmd`, `delegate`, `employee`. **Manager** is not stored — a user is a manager for every employee whose `manager_id` points to them.

| Role | Scope rule enforced in queries |
| --- | --- |
| `dmd` | Everything |
| `delegate` | Everything except final approval; vault reveal only if `users.can_reveal_vault = 1` |
| manager (derived) | Requests and costs of direct reports + self |
| `employee` | Own requests, subscriptions, handovers |
| nominated collector | Only the handover tasks where `collector_id` = self |

Every router checks scope server-side; IDs in URLs are never trusted.

## 4. Data model

All tables have `id` (PK), `created_at`, `updated_at`. Money is `DECIMAL(12,2)`, FX rate `DECIMAL(10,4)`.

| Table | Purpose / key columns |
| --- | --- |
| `employees` | `emp_code` (unique), name, designation, department, team, `unit` (BMD/AES), `manager_id` → employees, email, phone, `status` (active/inactive) |
| `users` | `employee_id` (unique), `password_hash`, `roles`, `can_reveal_vault`, `is_active`, `failed_logins`, `locked_until`, `last_login_at` |
| `otp_codes` | `user_id`, `purpose` (login / reveal), `code_hash`, `ref_id`, `expires_at`, `used_at`, `attempts` |
| `vendors` | name (unique), category, website, active |
| `vendor_plans` | `vendor_id`, plan_name, default_cost, currency, billing_cycle |
| `cards` | label, holder_name, `last4` (exactly 4 digits), active |
| `subscriptions` | vendor_id, plan_name, type, seats_total, cost_per_cycle, currency, billing_cycle, start_date, next_renewal_date, card_id, account_email, unit, department, status, cancelled_on, notes |
| `assignments` | subscription_id, employee_id, request_id, start_date, end_date, status (active / revoke_pending / revoked) |
| `card_charges` | subscription_id, card_id, charge_date, amount_original, currency, fx_rate, bank_fee_bdt, amount_bdt (computed), reference, is_expected, reconciled |
| `requests` | req_no (`SMP-YYYY-NNNN`), employee_id, `snapshot` (JSON of name/code/role/team/unit/manager at submit), type, vendor_id, other_tool_name, other_tool_url, plan_name, seats, duration_months, needed_from, reason, expected_use, est_cost_bdt, status, subscription_id, decided_by_dmd_at |
| `approvals` | request_id, step (manager / dmd), approver_id, decision, comment |
| `handovers` | request_id, method (vault / appointment / colleague), secret_ciphertext, secret_nonce, login_email, login_url, notes, proposed_at, confirmed_at, location, collector_id, collector_note, due_date, handed_over_at, received_at |
| `notifications` | user_id, type, title, body, link, read_at |
| `audit_logs` | user_id, action, entity, entity_id, before_json, after_json, ip — insert only |
| `settings` | key (PK), value |
| `daily_cost` | subscription_id, cost_date, amount_bdt (unique pair) — snapshot filled by a nightly job |

## 5. Request lifecycle

Statuses: `pending_manager`, `pending_dmd`, `on_hold`, `info_needed`, `rejected`, `withdrawn`, `approved`, `handover_pending`, `active`, `ended`.

| From | Action | Actor | To |
| --- | --- | --- | --- |
| — | submit | requester | `pending_manager` (or `pending_dmd` if the requester has no manager) |
| `pending_manager` | recommend | manager / dmd | `pending_dmd` |
| `pending_manager` | reject | manager / dmd | `rejected` |
| `pending_manager` | info | manager / dmd | `info_needed` |
| `pending_manager` | override (approve, reason required) | dmd, if setting `allow_urgent_override` | `approved` |
| `pending_dmd` | approve / reject / hold / info | dmd | `approved` / `rejected` / `on_hold` / `info_needed` |
| `on_hold` | resume / approve / reject | dmd | `pending_dmd` / `approved` / `rejected` |
| `info_needed` | resubmit (may edit) | requester | `pending_manager` |
| any before `approved` | withdraw | requester | `withdrawn` |
| `approved` (type new / upgrade) | set handover | dmd / delegate | `handover_pending` |
| `approved` (type renewal) | auto on approval | — | `active` (assignment end date extended) |
| `approved` (type cancel) | auto on approval | — | `ended` (assignment ended) |
| `handover_pending` | requester confirms receipt | requester | `active` (assignment created) |
| `active` | cancel / expiry / exit | dmd / delegate / job | `ended` |

The transition table lives in `services/workflow.py` as pure data; routers call `workflow.transition(status, action, actor_role)` and get the next status or a `WorkflowError`.

## 6. Cost engine (`services/cost.py`)

- `amount_bdt = amount_original × fx_rate + bank_fee_bdt` (rounded to 2 dp).
- **Accrued view** — for every day a subscription is active:
  - monthly: last actual BDT charge on or before that day ÷ days in that month;
  - yearly: last actual BDT charge ÷ days in that year (365/366);
  - usage / one-time: the charge amount on its charge date only;
  - no charge yet → estimate `cost_per_cycle × default_fx_rate` (flagged `estimated`).
- **Paid view** — sum of actual (non-expected) charges by charge date.
- Periods: today; week from `week_start` (default Saturday); month; year from `year_start_month` (default January). Month projection = MTD ÷ days elapsed × days in month. Run rate = today's daily total × 365.
- Per-employee cost = subscription daily cost ÷ active assignments that day; remainder reported as "Unassigned".

The engine takes plain dataclasses, not ORM objects, so it is unit-tested without a database.

## 7. Security

- Passwords: bcrypt. Lockout after 5 failed logins for 15 minutes.
- Login: `POST /auth/login`. Users with `dmd` or `delegate` role get `otp_required: true` and a short-lived `otp_token`; `POST /auth/verify-otp` returns the access token. Others get the access token directly.
- JWT access token: 8 hours, HS256, secret from env.
- Vault: AES-256-GCM, 32-byte key from `VAULT_KEY` (base64), random 12-byte nonce per secret. Ciphertext never returned by any list/detail endpoint.
- Reveal: `POST /handovers/{id}/reveal-otp` sends a 6-digit code (5-minute expiry, 5 attempts); `POST /handovers/{id}/reveal` with the code returns the secret once; every reveal is audit-logged with IP.
- Card data: `last4` must match `^\d{4}$`; free-text fields reject any run of 13–19 digits.
- CORS restricted to `FRONTEND_ORIGIN`.

## 8. API endpoints

Prefix `/api`. All JSON. Auth = `Authorization: Bearer <token>` except login.

### Auth
| Method | Path | Who |
| --- | --- | --- |
| POST | `/auth/login` | public |
| POST | `/auth/verify-otp` | public (with otp_token) |
| GET | `/auth/me` | any |
| POST | `/auth/change-password` | any |

### Masters
| Method | Path | Who |
| --- | --- | --- |
| GET/POST | `/employees` | dmd, delegate (GET: managers see team) |
| PATCH | `/employees/{id}` | dmd, delegate — setting `inactive` or changing team/manager marks assignments `revoke_pending` |
| POST | `/employees/import` | dmd, delegate (xlsx/csv) |
| GET/POST/PATCH | `/users`, `/users/{id}` | dmd (delegate: create employee users only) |
| GET/POST/PATCH | `/vendors`, `/vendors/{id}`, `/vendors/{id}/plans` | read: any; write: dmd, delegate |
| GET/POST/PATCH | `/cards`, `/cards/{id}` | dmd, delegate |
| GET/PUT | `/settings` | dmd |

### Subscriptions and charges
| Method | Path | Who |
| --- | --- | --- |
| GET/POST | `/subscriptions` | dmd, delegate |
| GET/PATCH | `/subscriptions/{id}` | dmd, delegate |
| POST | `/subscriptions/{id}/cancel` | dmd, delegate |
| POST | `/subscriptions/{id}/assignments` | dmd, delegate |
| DELETE | `/subscriptions/{id}/assignments/{aid}` | dmd, delegate |
| POST | `/subscriptions/import` | dmd, delegate |
| GET | `/subscriptions/shared-seats?vendor_id=` | any (free seats for the request form) |
| GET | `/my/subscriptions` | any |
| GET/POST | `/charges` | dmd, delegate |
| PATCH/DELETE | `/charges/{id}` | dmd, delegate |

### Requests and approvals
| Method | Path | Who |
| --- | --- | --- |
| POST | `/requests` | any |
| GET | `/requests?scope=mine|team|pending|all&status=` | scoped |
| GET | `/requests/{id}` | requester, their manager, dmd, delegate |
| PATCH | `/requests/{id}` | requester while `info_needed` |
| POST | `/requests/{id}/resubmit` | requester |
| POST | `/requests/{id}/withdraw` | requester |
| POST | `/requests/{id}/decision` | manager / dmd per lifecycle |
| POST | `/requests/bulk-approve` | dmd |
| GET | `/requests/{id}/cost-estimate` · `POST /requests/estimate` | any |

### Handover
| Method | Path | Who |
| --- | --- | --- |
| POST | `/requests/{id}/handover` | dmd, delegate |
| GET | `/handovers/{id}` | requester, collector, dmd, delegate |
| GET | `/my/handover-tasks` | nominated collector |
| POST | `/handovers/{id}/propose-slot` | requester |
| POST | `/handovers/{id}/confirm-slot` | dmd, delegate |
| POST | `/handovers/{id}/handed-over` | collector, dmd, delegate |
| POST | `/handovers/{id}/reveal-otp` | requester, dmd, delegate with permission |
| POST | `/handovers/{id}/reveal` | same |
| POST | `/handovers/{id}/received` | requester |
| POST | `/handovers/{id}/rotate` | dmd, delegate — replace secret, notify holders |

### Dashboard and reports
| Method | Path | Who |
| --- | --- | --- |
| GET | `/dashboard/summary?view=accrued|paid&currency=BDT|USD` | scoped |
| GET | `/dashboard/series?days=30` | scoped |
| GET | `/dashboard/monthly?months=12` | scoped |
| GET | `/dashboard/by-tool`, `/dashboard/by-department`, `/dashboard/top-employees` | dmd, delegate (manager: team) |
| GET | `/dashboard/renewals?days=30` | dmd, delegate |
| GET | `/reports/{type}?from=&to=&format=json|xlsx` | dmd, delegate (manager: team) |

Report types: `register`, `cost-summary`, `cost-by-tool`, `cost-by-department`, `cost-by-employee`, `requests`, `credential-holders`, `renewals`.

### Notifications and audit
| Method | Path | Who |
| --- | --- | --- |
| GET | `/notifications` | any (own) |
| POST | `/notifications/{id}/read`, `/notifications/read-all` | any |
| GET | `/audit-logs` | dmd, delegate |

## 9. Jobs

Run with `python -m app.jobs <name>`; schedule with cron (times Asia/Dhaka).

| Job | Cron | Action |
| --- | --- | --- |
| `daily-cost` | `15 0 * * *` | Write yesterday's accrued cost per subscription to `daily_cost` |
| `expected-charges` | `30 0 * * *` | Create `is_expected` charges for renewals due today; roll `next_renewal_date` forward |
| `renewal-reminders` | `0 9 * * *` | Notify dmd + delegates about renewals in 7 days and 1 day |
| `appointment-reminders` | `*/15 * * * *` | Remind both sides 1 hour before a confirmed slot |
| `escalations` | `0 10 * * *` | Remind approvers about steps older than `approval_sla_days` |
| `dmd-digest` | `0 18 * * *` | Email DMD: spend today, pending approvals, pending handovers |

## 10. Settings keys

| Key | Default |
| --- | --- |
| `week_start` | `sat` |
| `year_start_month` | `1` |
| `monthly_budget_bdt` | `0` (no budget) |
| `default_fx_rate_usd` | `122.00` |
| `approval_sla_days` | `2` |
| `allow_urgent_override` | `true` |

## 11. Running locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set DATABASE_URL, JWT_SECRET, VAULT_KEY
alembic upgrade head            # or: python -m scripts.init_db for a quick start
python -m scripts.seed          # demo users, vendors, subscriptions
uvicorn app.main:app --reload
pytest
```

Swagger UI: `http://localhost:8000/docs`.
