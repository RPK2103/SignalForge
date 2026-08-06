# SignalForge Agent Instructions

Project:
SignalForge

Purpose:
AI-powered execution intelligence platform.

Rules:

- Build one feature at a time.
- Keep the MVP simple.
- Avoid overengineering.
- SignalForge currently has no interactive login screen in the development UI.
  The FastAPI backend is default-deny, and protected APIs require valid JWT
  authentication.
- No Kubernetes.
- No microservices.
- No unnecessary dependencies.

Frontend:

- Next.js
- TypeScript
- Tailwind
- shadcn/ui

Backend:

- FastAPI
- Pydantic

AI:

- Azure OpenAI

Priority:
Demo quality over technical complexity.

Output Preference:

When implementing features:

1. Explain files to create or modify.
2. Generate Cursor-ready prompts.
3. Keep code generation scoped.
4. Prefer mock data before integrations.
5. Prioritize demo value over production readiness.

## Cursor Cloud specific instructions

Two services: FastAPI backend (`backend/`, Python 3.13, venv at `backend/.venv`, port 8000) and Next.js frontend (`frontend/`, Node 22, port 3000). Standard install/lint/test/build/run commands are in `README.md` §27-34 and `.github/workflows/`. The update script already recreates `backend/.venv` and runs `pip install` + `npm ci`, so future agents only need the run/DB/env steps below.

Local env files (git-ignored; the update script does NOT create them — create if missing):
- `backend/.env`: `DATABASE_URL=sqlite:///./signalforge.db`, `AI_ENABLED=false`, `AUTH_MODE=local_development`, and `SIGNALFORGE_LOCAL_AUTH_SECRET=<>=32 chars>`. AI/Azure is optional (deterministic fallback when `AI_ENABLED=false`).
- `frontend/.env.local`: `NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL=http://127.0.0.1:8000`.

Database (SQLite is enough locally): from `backend/` run `.venv/bin/python -m alembic upgrade head`, then `.venv/bin/python -m app.db.seed` (Phase 2 catalog) and optionally `.venv/bin/python -m app.db.enterprise_seed` (NovaBank tenant). PostgreSQL is only needed to exercise RLS like CI; those `*_postgres` tests are skipped on SQLite.

Run: backend `cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`; frontend `cd frontend && npm run dev`.

Auth is default-deny: every `/api/v2/*`, `/api/v3/*` and legacy root route requires a Bearer JWT (only `/`, `/health`, `/dashboard/*` are open). Mint a local dev token with `cd backend && .venv/bin/python -m app.security issue-dev-token --subject dev --tenant novabank --roles tenant_admin`. The frontend has NO login screen: the browser token lives in-memory only, read from `window.__SIGNALFORGE_TEST_AUTH__`.

### `window.__SIGNALFORGE_TEST_AUTH__` non-production boundary

`window.__SIGNALFORGE_TEST_AUTH__` is permitted only for:

- local development;
- Cursor local or Cursor Cloud development workspaces;
- automated browser tests;
- disposable non-production environments.

It is prohibited to:

- use against staging;
- use against production;
- use against a customer environment;
- commit tokens;
- store tokens in source;
- store tokens in screenshots;
- print tokens in shared logs;
- reuse a locally minted token against another environment.

Only short-lived local-development tokens minted for the same local environment may be used.

To drive the UI manually in a permitted local environment, load the page, set `window.__SIGNALFORGE_TEST_AUTH__ = {"token":"<jwt>","tenantId":"novabank"}` in the DevTools console, then click the catalog "Retry" button. The token is lost on page reload (re-inject each time). Do not include real tokens or secret values in documentation, commits, or shared logs.

### Local `.env` test caveat

pydantic-settings loads the ignored `backend/.env`, so `SIGNALFORGE_LOCAL_AUTH_SECRET` can appear in the test process. Production-hardening tests intentionally reject local authentication configuration under production settings. The variable may be blanked only for that local test process.

PowerShell example:

```powershell
$previousSecret = $env:SIGNALFORGE_LOCAL_AUTH_SECRET

try {
    $env:SIGNALFORGE_LOCAL_AUTH_SECRET = ""
    .\.venv\Scripts\python.exe -m pytest tests -q
}
finally {
    if ($null -eq $previousSecret) {
        Remove-Item Env:SIGNALFORGE_LOCAL_AUTH_SECRET `
            -ErrorAction SilentlyContinue
    }
    else {
        $env:SIGNALFORGE_LOCAL_AUTH_SECRET = $previousSecret
    }
}
```

Explicit constraints:

- do not weaken or remove the production-hardening assertion;
- do not commit `backend/.env`;
- do not commit `frontend/.env.local`;
- do not globally blank required secrets in deployed environments;
- do not use development local-auth configuration in production.

CI is green because it has no `.env`.
