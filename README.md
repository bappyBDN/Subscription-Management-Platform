# SMP — Subscription Management Platform (BMD/AES)

One place to see every paid subscription (Claude, ChatGPT, DeepSeek and others) bought on DMD Sir's card, what it costs per day / week / month / year, and to request, approve and hand over access.

| Part | Stack | Status |
| --- | --- | --- |
| [`backend/`](backend/) | FastAPI · SQLAlchemy 2 · PostgreSQL | v1 (MVP) built |
| [`frontend/`](frontend/) | React 18 · Vite · TypeScript · Tailwind | v1 built (screens S01–S14) |

Specifications:

- [docs/BACKEND.md](docs/BACKEND.md) — API, data model, lifecycle, cost engine, security, jobs
- [docs/FRONTEND.md](docs/FRONTEND.md) — screens, navigation by role, UI rules, build order

## Main flow

1. **Employee** submits a request: tool, plan, duration, reason. Their ID, role, team and reporting manager are filled in automatically.
2. **Reporting manager** recommends, rejects or asks for more information.
3. **DMD Sir** approves, rejects, puts on hold or asks for info (can adjust plan/seats/duration).
4. **DMD Sir or a delegate** hands over access in one of three ways:
   - **Secure vault** — the credential is encrypted (AES-256-GCM); the employee reveals it once with an email OTP.
   - **Come to DMD Sir** — the employee proposes a date/time, DMD Sir confirms it.
   - **Via colleague** — a named colleague (e.g. "collect from Rahim vai") hands it over and marks it done.
5. **Employee** confirms receipt → the seat becomes active and its cost is tracked.

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env    # set DATABASE_URL, JWT_SECRET, VAULT_KEY
docker compose up --build
```

- App: http://localhost:5173 (nginx serves the React build and forwards `/api` to the backend)
- API docs: http://localhost:8000/docs

The backend creates any missing tables on start. For demo data (5 users, password `ChangeMe#2026`):

```bash
docker compose exec backend python -m scripts.seed
```

DMD Sir and delegate logins need an email OTP. With no `SMTP_HOST` set, the code is printed in the backend log:
`docker compose logs -f backend`.

## Without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set DATABASE_URL, JWT_SECRET, VAULT_KEY
python -m scripts.seed      # creates tables + demo data
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_URL=http://localhost:8000/api
npm run dev                 # http://localhost:5173
```
