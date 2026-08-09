# Production deployment runbook

Operator-oriented guide for deploying SignalForge. This document describes
procedures and evidence expectations. It does **not** claim that production
deployment has been executed or validated end-to-end in a customer environment.

> **DEPLOYMENT PROCEDURE — NOT YET PRODUCTION-VALIDATED** for cloud hosting,
> Entra interactive login, and customer-environment cutover steps below.
> Azure hosting appears in Microsoft POC materials as a **POC OPTION**, not as
> a validated production platform for this repository.

**Microsoft has not endorsed this project.**

Local authentication (`AUTH_MODE=local_development`) and
`window.__SIGNALFORGE_TEST_AUTH__` are **prohibited in production**.

---

## 1. Prerequisites

- Python 3.13 runtime (backend) and Node 22 (frontend build/runtime).
- PostgreSQL when tenant **FORCE RLS** must be proven (SQLite is not an RLS proof).
- Separate database principals for migrations vs application traffic (see §4).
- Secrets store or platform secret injection for production credentials (env vars
  today; Azure Key Vault is **PROPOSED**, not wired in-app).
- Ability to run Alembic as the migration role and start uvicorn without
  `--reload` as the application role.
- CI green on the release revision (see
  [`../evidence/production-readiness-evidence-index.md`](../evidence/production-readiness-evidence-index.md)).

---

## 2. Infrastructure assumptions

SignalForge ships as a **single FastAPI process** plus a **Next.js** frontend.
There is no Kubernetes or microservices requirement.

| Target | Status |
|---|---|
| Local / container (`backend/Dockerfile`) | Documented; local path exercised in development |
| Render blueprint (`render.yaml`) | Documented blueprint; treat cloud cutover as **DEPLOYMENT PROCEDURE — NOT YET PRODUCTION-VALIDATED** |
| Generic Linux container / VM | Same uvicorn + Next start commands |
| Azure Container Apps / App Service / Azure Database for PostgreSQL | **POC OPTION** in Microsoft POC docs — **NOT YET PRODUCTION-VALIDATED** |

Do not present Azure (or any cloud) as already production-proven from this repo alone.

---

## 3. Required environment variables

See also `backend/.env.example` and `frontend/.env.example`. **No real secrets
belong in git.**

### LOCAL DEVELOPMENT ONLY

| Variable | Notes |
|---|---|
| `AUTH_MODE=local_development` | Forbidden when `APP_ENV=production` |
| `SIGNALFORGE_LOCAL_AUTH_SECRET` | ≥32 characters; must be **absent** in production |
| `DOCS_ENABLED=true` | Allowed locally; must be `false` in production |
| `DATABASE_URL=sqlite:///./signalforge.db` | Convenient locally; not an RLS proof |
| `window.__SIGNALFORGE_TEST_AUTH__` | Browser console / Playwright only — never production |

### PRODUCTION REQUIRED

Fail-closed startup (see `backend/app/security/config.py`) expects:

| Variable | Notes |
|---|---|
| `APP_ENV=production` | Enables production validation |
| `AUTH_MODE=entra_oidc` | Only allowed production mode |
| `ENTRA_ISSUER` | OIDC issuer |
| `ENTRA_AUDIENCE` | API audience |
| `ENTRA_JWKS_URI` | JWKS endpoint |
| `ENTRA_ALLOWED_TENANT_IDS` | Comma-separated allowlist (at least one) |
| `DOCS_ENABLED=false` | OpenAPI/docs disabled |
| `TRUSTED_HOSTS` | Explicit non-wildcard hosts |
| `HSTS_ENABLED` | Prefer `true` behind HTTPS |
| `LOG_FORMAT=json` | Recommended for aggregation |
| `CORS_ORIGINS` | Explicit frontend origin(s); never `*` |
| `DATABASE_URL` | Application role connection string |

Optional observability knobs (`OBSERVABILITY_ENABLED`, `OTEL_*`, etc.) are
documented in `backend/.env.example`. Production Azure Monitor export remains
**PROPOSED / NOT VALIDATED** unless separately evidenced.

---

## 4. Migration role vs application role

| Role (default names) | Purpose |
|---|---|
| `signalforge_migrator` (`DB_MIGRATION_ROLE`) | Owns tables; runs `alembic upgrade head` |
| `signalforge_app` (`DB_APPLICATION_ROLE`) | Serves HTTP traffic; **NOSUPERUSER**, **NOBYPASSRLS**, not table owner |

**DEPLOYMENT PROCEDURE — NOT YET PRODUCTION-VALIDATED** in customer cloud:

1. Create both roles on PostgreSQL.
2. Run migrations with the migrator connection string.
3. Grant the app role DML only (no ownership, no bypass RLS).
4. Point the running API `DATABASE_URL` at the **application** role only.

Never serve the API as a superuser or table owner.

---

## 5. FORCE RLS validation

- Repository migrations enable/force RLS on tenant tables (PostgreSQL).
- Evidence path: `.github/workflows/security-ci.yml` `postgres-rls` job and
  `backend/tests/security_postgres`.
- SQLite success is **not** FORCE RLS proof.

**DEPLOYMENT PROCEDURE — NOT YET PRODUCTION-VALIDATED** on a target cloud DB:

1. Migrate to head as migrator.
2. Confirm policies exist and FORCE RLS is on for tenant tables.
3. Connect as `signalforge_app` and verify cross-tenant reads return empty /
   denied (reuse security_postgres patterns or equivalent smoke queries).

---

## 6. Backend deployment

Production process must use uvicorn **without** `--reload`.

Reference images/commands:

- Container: [`backend/Dockerfile`](../../backend/Dockerfile) —
  `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`
- Render: [`render.yaml`](../../render.yaml) —
  `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Suggested sequence (**DEPLOYMENT PROCEDURE — NOT YET PRODUCTION-VALIDATED**):

1. Install deps (`pip install -r requirements.txt`).
2. Set production env vars (Entra, CORS, trusted hosts, `DOCS_ENABLED=false`).
3. Run migrations as migrator: `python -m alembic upgrade head`.
4. Start API as app role with the Dockerfile/Render start command (no `--reload`).

---

## 7. Frontend deployment

```bash
cd frontend
npm ci
npm run build
npm start
```

Set `NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL` to the **production API origin**
(build-time public URL). Do **not** put JWTs or secrets in frontend env files.

Interactive Entra/MSAL browser login is **INTEGRATION REQUIRED** (no shipped
login SPA). `window.__SIGNALFORGE_TEST_AUTH__` is local/test only.

---

## 8. Health verification

```http
GET /health
```

- Liveness only: process is up.
- Must **not** return tenant data, auth decisions, or secrets.
- Suitable for load-balancer / Render `healthCheckPath: /health`.

Protected APIs remain default-deny and are out of scope for this probe.

---

## 9. Authentication verification

**DEPLOYMENT PROCEDURE — NOT YET PRODUCTION-VALIDATED** for live Entra:

1. Confirm startup succeeds only with `AUTH_MODE=entra_oidc` and complete
   `ENTRA_*` settings; local mode / local secret must fail closed.
2. Unauthenticated `GET /api/v3/...` → `401`.
3. Valid Entra bearer for an allowed tenant → authorized routes succeed per RBAC.
4. Token for a disallowed tenant / wrong audience → rejected.
5. Confirm `SIGNALFORGE_LOCAL_AUTH_SECRET` is unset and
   `__SIGNALFORGE_TEST_AUTH__` is unused.

---

## 10. Tenant-isolation smoke test

After auth works:

1. As tenant A, list a tenant-scoped resource; capture an id.
2. As tenant B (or forged tenant header with A’s token constraints), confirm
   A’s rows are not readable/writable.
3. On PostgreSQL, repeat under the **application** role to exercise FORCE RLS
   (CI `security_postgres` is the automated analogue).

---

## 11. NovaBank optional demo seed

NovaBank is a **synthetic / fictional** demo tenant. Seed and materialize are
**CLI only** — there is **no** public HTTP reset/seed mutation API.

```bash
cd backend
python -m app.db.enterprise_seed   # foundational enterprise seed (as applicable)
python -m app.demo novabank materialize --json
```

Do not expose demo reset over the network. Do not treat NovaBank rows as
customer evidence.

---

## 12. Observability verification

1. With a valid token and `observability.*` permissions, hit
   `/api/v3/observability/*` and/or open `/observability`.
2. Confirm structured logs when `LOG_FORMAT=json`.
3. Optional OTLP export (`OTEL_EXPORTER_MODE=otlp`) is configuration-dependent and
   **NOT YET PRODUCTION-VALIDATED** for Azure Monitor unless separately proven.

---

## 13. Rollback

See [`release-and-rollback.md`](release-and-rollback.md).

High level:

1. Redeploy the previous known-good application revision (image / build).
2. Keep database forward-compatible when possible.
3. Do **not** run automatic destructive `alembic downgrade` when data-loss risk
   exists (see §14).

---

## 14. Database rollback considerations

- Prefer expand/contract migrations and application rollback without schema
  downgrade.
- **No automatic destructive downgrade.** Operators must assess data-loss risk
  before any `alembic downgrade`.
- If a downgrade is required, take a backup first, run only on a rehearsed path,
  and document the decision in release evidence.

---

## 15. Incident response

Minimum operator loop (customer IR process still required):

1. **Detect** — health failures, auth error spikes, audit denials, error rate.
2. **Contain** — revoke/rotate credentials; disable AI provider if needed
   (`AI_ENABLED=false`); scale to last known-good revision.
3. **Diagnose** — correlate JSON logs, security audit events, observability APIs
   (authorized readers only). Never paste bearer tokens into tickets or shared logs.
4. **Recover** — fix forward or roll back application per §13–14.
5. **Evidence** — capture revision SHAs, config snapshots (secret-free), and
   timeline in the release evidence pack.

Automated SIEM / on-call orchestration is **DEFERRED**.

---

## 16. Release evidence capture

Treat this as **PRODUCTION-READINESS EVIDENCE**, not production certification.

Capture at minimum:

- Git SHA / image digest deployed
- Migration revision (`alembic current` / heads)
- Secret-free startup config snapshot
- Health check result
- Auth smoke (401 without token; Entra success path when configured)
- Tenant-isolation smoke result
- Link to CI runs for the revision
- Pointer to this runbook and [`release-and-rollback.md`](release-and-rollback.md)

Index: [`../evidence/production-readiness-evidence-index.md`](../evidence/production-readiness-evidence-index.md).
