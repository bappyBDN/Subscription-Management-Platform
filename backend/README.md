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

Local PostgreSQL (14+). In `psql -U postgres`:

```sql
CREATE USER smp WITH PASSWORD 'smp_password';
CREATE DATABASE smp OWNER smp ENCODING 'UTF8';
```

`DATABASE_URL` in `.env` then is `postgresql+psycopg://smp:smp_password@localhost:5432/smp`.

Create the schema with Alembic (first time, generate the initial migration from the models):

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

or, for a quick local start, `python -m scripts.init_db`.

Demo data (5 users, password `ChangeMe#2026`): `python -m scripts.seed`

| Login | Role |
| --- | --- |
| `DMD001` | DMD Sir (needs email OTP) |
| `BMD010` | Delegate admin (needs email OTP) |
| `AES100` | Manager of AES101 |
| `AES101` | Employee |
| `BMD201` | Employee |

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

**Employees** (`POST /api/employees/import`, .xlsx or .csv): `emp_code, name, designation, department, team, unit, manager_code, email, phone`

**Subscriptions** (`POST /api/subscriptions/import`): `vendor, plan_name, type, seats_total, cost_per_cycle, currency, billing_cycle, start_date, next_renewal_date, card_last4, account_email, unit, department, holder_codes`
(`holder_codes` = comma-separated employee codes who already use the subscription).
