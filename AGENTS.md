# SignalForge Agent Instructions

Project:
SignalForge

Purpose:
AI-powered execution intelligence platform.

Rules:

- Build one feature at a time.
- Keep the MVP simple.
- Avoid overengineering.
- No authentication.
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

Auth is default-deny: every `/api/v2/*`, `/api/v3/*` and legacy root route requires a Bearer JWT (only `/`, `/health`, `/dashboard/*` are open). Mint a local dev token with `cd backend && .venv/bin/python -m app.security issue-dev-token --subject dev --tenant novabank --roles tenant_admin`. The frontend has NO login screen: the browser token lives in-memory only, read from `window.__SIGNALFORGE_TEST_AUTH__`. To drive the UI manually, load the page, set `window.__SIGNALFORGE_TEST_AUTH__ = {"token":"<jwt>","tenantId":"novabank"}` in the DevTools console, then click the catalog "Retry" button. The token is lost on page reload (re-inject each time).

Test gotcha: running the full backend suite with `backend/.env` present makes `tests/security/test_config_hardening.py::test_production_ready_config_passes` FAIL, because pydantic-settings loads `SIGNALFORGE_LOCAL_AUTH_SECRET` from `.env` and the test rejects a local secret under a production config. Run backend tests with that secret unset, e.g. `SIGNALFORGE_LOCAL_AUTH_SECRET= .venv/bin/python -m pytest tests -q`. CI is green because it has no `.env`.

