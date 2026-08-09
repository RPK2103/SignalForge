# Release and rollback

Companion to [`production-deployment-runbook.md`](production-deployment-runbook.md).
Cloud cutover steps below are **DEPLOYMENT PROCEDURE — NOT YET PRODUCTION-VALIDATED**.
This is **PRODUCTION-READINESS EVIDENCE** guidance, not production certification.

**Microsoft has not endorsed this project.**

---

## Pre-deploy

1. Confirm CI green on the release SHA (backend, frontend, security/RLS, audits).
2. Review migration scripts for expand/contract safety; note any irreversible steps.
3. Verify production secrets are present in the host secret store (not in git):
   `AUTH_MODE=entra_oidc`, `ENTRA_*`, `DATABASE_URL` (app role), `CORS_ORIGINS`,
   `TRUSTED_HOSTS`, `DOCS_ENABLED=false`. Local auth secret must be absent.
4. Take a database backup / snapshot before schema changes.
5. Confirm rollback revision (previous image/build) is still pullable.
6. Freeze demo/seed CLIs on live tenant data paths — NovaBank seed is
   synthetic-only and must not overwrite real tenant data.

---

## Deploy

1. Deploy database migrations as **migrator** role:
   `python -m alembic upgrade head`
2. Deploy backend using production start (no `--reload`):
   - Container: `backend/Dockerfile` uvicorn CMD
   - Render: `render.yaml` `startCommand`
3. Deploy frontend: `npm ci && npm run build && npm start` with
   `NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL` pointing at the API.
4. Warm health: `GET /health` (liveness only).
5. Do not enable `AUTH_MODE=local_development` or
   `window.__SIGNALFORGE_TEST_AUTH__` in production.

---

## Post-deploy

1. Authentication smoke: unauthenticated API → `401`; valid Entra token path when
   configured (**INTEGRATION REQUIRED** for interactive MSAL SPA).
2. Tenant-isolation smoke (application role / FORCE RLS on PostgreSQL).
3. Observability surfaces reachable for authorized roles.
4. Capture release evidence (SHA, migration head, secret-free config, check results)
   per the production deployment runbook §16.
5. Update the evidence index links if verification commands or statuses changed.

---

## Rollback

### Application rollback

1. Redeploy the previous known-good backend image/build and frontend build.
2. Re-check `GET /health` and auth smoke.
3. Leave the database at a forward-compatible revision whenever the prior app
   can run against the newer schema.

### Database rollback

- **No automatic Alembic downgrade** when data-loss risk exists.
- Prefer fixing forward with a new migration.
- If a schema downgrade is unavoidable:
  1. Restore from the pre-deploy backup, **or**
  2. Run a rehearsed, manually approved `alembic downgrade <revision>` only after
     explicit data-loss assessment and change control.
- Never script unsupervised destructive downgrade into the default deploy path.

### Incident-driven rollback

Follow containment in the production deployment runbook §15, then application
rollback above. Record the timeline in release evidence.
