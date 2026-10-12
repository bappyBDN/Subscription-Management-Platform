# SMP Backend (FastAPI)

Full specification: [../docs/BACKEND.md](../docs/BACKEND.md).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Generate secrets for `.env`:

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"                       # JWT_SECRET
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"    # VAULT_KEY
```

> Keep `VAULT_KEY` safe and backed up separately from the database. Without it, stored credentials cannot be decrypted.

### Database

MySQL 8:

```sql
CREATE DATABASE smp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'smp'@'%' IDENTIFIED BY 'smp_password';
GRANT ALL ON smp.* TO 'smp'@'%';
```

Create the schema with Alembic (first time, generate the initial migration from the models):

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

or, for a quick local start, `python -m scripts.init_db`.

Demo data (units BMD and AES with departments and budgets; 6 users, password `ChangeMe#2026`): `python -m scripts.seed`

| Login | Role |
| --- | --- |
| `DMD001` | DMD Sir (needs email OTP) |
| `BMD010` | Delegate admin (needs email OTP) |
| `AES100` | Head of the AES unit and of AES / IT; manager of AES101 |
| `AES101` | Employee, AES / IT |
| `AES301` | Employee, AES / Finance |
| `BMD201` | Employee and head of BMD / Marketing |

With no `SMTP_HOST`, emails and OTP codes are printed to the server log.

## Run

```bash
uvicorn app.main:app --reload
```

Swagger UI: http://localhost:8000/docs

## Tests

```bash
pytest
```

- `tests/test_cost.py`, `test_workflow.py`, `test_crypto.py` — pure logic (cost engine, request state machine, vault)
- `tests/test_api_flow.py` — full request → approval → handover flows, permissions, OTP, lockout
- `tests/test_api_costs.py` — charges, dashboard, reports, Excel export, import, notifications, jobs
- `tests/test_api_v2.py` — unit/department access rule, proposals, cost allocation, payments, budgets, anomalies, savings

## Scheduled jobs

`python -m app.jobs <job>` — see the crontab in `app/jobs/__main__.py`.
Jobs: `daily-cost`, `expected-charges`, `expire-assignments`, `renewal-reminders`, `appointment-reminders`, `escalations`, `dmd-digest`.

## Layout

```
app/
  main.py            FastAPI app
  enums.py           statuses, roles, cycles
  core/              config, security (bcrypt, JWT, OTP hash), vault crypto, deps (auth + scoping)
  db/                SQLAlchemy base + session
  models/            tables
  schemas/           Pydantic request/response models
  services/          cost engine, workflow state machine, request/handover logic, notifications, audit
  api/routers/       auth, masters, subscriptions + charges, requests + handover, dashboard, reports, system
  jobs/              cron jobs
scripts/             init_db, seed
alembic/             migrations
tests/
```

## Import file formats

Create the units first (`POST /api/units`, e.g. `BMD`, `AES`). Departments named in the files are created automatically inside their unit.

**Employees** (`POST /api/employees/import`, .xlsx or .csv): `emp_code, name, designation, unit (code), department (name), team, manager_code, email, phone`

**Subscriptions** (`POST /api/subscriptions/import`): `vendor, plan_name, type, seats_total, cost_per_cycle, currency, billing_cycle, start_date, next_renewal_date, card_last4, account_email, unit (code), department (name), owner_scope, holder_codes`
(`owner_scope` = `unit` or `department` — defaults to `department` when a department is given; `holder_codes` = comma-separated employee codes who already use the subscription).

## Unit & department cost (v2)

See [../docs/V2.md](../docs/V2.md) for the allocation method and request/response examples. Quick start:

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/costs/units?from=2026-10-01&to=2026-10-31"
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/costs/units/2/departments"
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/reports/cost-by-department?format=xlsx" -o dept.xlsx
```
