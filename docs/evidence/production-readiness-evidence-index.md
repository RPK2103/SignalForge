# Production-Readiness Evidence Index

Maps claims to repository proof. A test proves **only** what it asserts.
This index is **PRODUCTION-READINESS EVIDENCE**, not production certification.
No row below claims that a customer production cutover was executed.

Operator procedures:
[`../deployment/production-deployment-runbook.md`](../deployment/production-deployment-runbook.md),
[`../deployment/release-and-rollback.md`](../deployment/release-and-rollback.md).

| Claim | Evidence | Verification command / check | Status |
|---|---|---|---|
| Default-deny API | `backend/app/security/middleware.py`, E2E 401 tests | `npx playwright test` auth cases; pytest security | IMPLEMENTED |
| JWT authentication | `app/security/jwt_verifier.py`, modes in config | `pytest tests/security` | IMPLEMENTED |
| Permission coverage | `app/security/permissions.py`, `coverage.py` | `pytest tests/security` | IMPLEMENTED |
| Tenant isolation (app) | TenantContext + service queries | enterprise/security tests | IMPLEMENTED |
| FORCE RLS | Alembic security migration + `security_postgres` | CI Postgres job / `POSTGRES_TEST_URL` | IMPLEMENTED on PG |
| Non-superuser app role / app role isolation | RLS CI role setup; `DB_APPLICATION_ROLE` | security-ci workflow; migrator vs app role docs | IMPLEMENTED in CI |
| Audit behavior / security audit | `SecurityAuditService`, audit API | `pytest tests/security` | IMPLEMENTED |
| Observability | `app/observability`, `/api/v3/observability` | `pytest tests/observability` | IMPLEMENTED (local) |
| AI-quality gates | offline evaluate CLI + CI | observability-ci / evaluate-ai-quality | IMPLEMENTED |
| Deterministic NovaBank generation | `app/demo/novabank`, demo tests | `pytest tests/demo`; demo-tenant-ci | IMPLEMENTED |
| Graph determinism | projection rebuild idempotency tests | demo/graph tests | IMPLEMENTED |
| Scenario determinism | scenario result hashing / demo materialize | `pytest tests/scenarios` + demo | IMPLEMENTED |
| Citation binding | CoS citation validation | `pytest tests/chief_of_staff` | IMPLEMENTED |
| Idempotency (seed/ingest) | demo seed second-run; connector receipts | demo + connector tests | IMPLEMENTED |
| Migration integrity / migration process | single Alembic head; migrator role | `alembic heads`; `alembic check`; `alembic upgrade head` | IMPLEMENTED |
| Production startup command | `backend/Dockerfile`, `render.yaml` (uvicorn, no `--reload`) | Inspect CMD / `startCommand` | DOCUMENTED |
| Frontend build command | `frontend/package.json` | `npm ci && npm run build && npm start` | DOCUMENTED |
| Health check | `GET /health` (liveness only) | `curl` / Render `healthCheckPath` | IMPLEMENTED |
| RLS tests | `backend/tests/security_postgres` | security-ci `postgres-rls` job | IMPLEMENTED on PG |
| Dependency audits | pip-audit, npm audit --omit=dev | CI security + local | IMPLEMENTED |
| CI workflow | `.github/workflows/*` (incl. backend-ci on docs paths) | GitHub Actions | IMPLEMENTED |
| Rollback documentation | `docs/deployment/release-and-rollback.md` | Review runbook; no automatic destructive downgrade | DOCUMENTED |
| Backend tests | `backend/tests` | `pytest -rs` | IMPLEMENTED |
| Frontend tests | Vitest | `npm test -- --run` | IMPLEMENTED |
| E2E tests | Playwright | `npx playwright test` | IMPLEMENTED |
| Executive briefing UI | `frontend/src/app/briefing` | Vitest + Playwright briefing | IMPLEMENTED (Prompt 10) |
| Microsoft endorsement | — | — | **NOT CLAIMED** |
| SOC 2 / ISO / pen-test done | — | — | **NOT CLAIMED** |
| Production customers / ROI | — | — | **NOT CLAIMED** |
| Calibrated NovaBank probability | prediction registry gates | prediction tests show unpromoted | **NOT CLAIMED** |
| Causal scenario outcomes | scenario docs + UI labels | runbook disclaimers (not causal prediction) | **NOT CLAIMED** |

## How to use

During diligence, re-run verification commands on the evaluated revision.
Update counts in README/case study only from fresh runs.
Treat “DOCUMENTED” rows as procedure evidence, not proof of a live production
deployment.
