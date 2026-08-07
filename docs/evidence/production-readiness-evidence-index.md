# Production-Readiness Evidence Index

Maps claims to repository proof. A test proves **only** what it asserts.

| Claim | Evidence | Verification command / check | Status |
|---|---|---|---|
| Default-deny API | `backend/app/security/middleware.py`, E2E 401 tests | `npx playwright test` auth cases; pytest security | IMPLEMENTED |
| JWT authentication | `app/security/jwt_verifier.py`, modes in config | `pytest tests/security` | IMPLEMENTED |
| Permission coverage | `app/security/permissions.py`, `coverage.py` | `pytest tests/security` | IMPLEMENTED |
| Tenant isolation (app) | TenantContext + service queries | enterprise/security tests | IMPLEMENTED |
| FORCE RLS | Alembic security migration + `security_postgres` | CI Postgres job / `POSTGRES_TEST_URL` | IMPLEMENTED on PG |
| Non-superuser app role | RLS CI role setup | security-ci workflow | IMPLEMENTED in CI |
| Audit behavior | `SecurityAuditService`, audit API | `pytest tests/security` | IMPLEMENTED |
| Observability | `app/observability`, `/api/v3/observability` | `pytest tests/observability` | IMPLEMENTED (local) |
| AI-quality gates | offline evaluate CLI + CI | observability-ci / evaluate-ai-quality | IMPLEMENTED |
| Deterministic NovaBank generation | `app/demo/novabank`, demo tests | `pytest tests/demo`; demo-tenant-ci | IMPLEMENTED |
| Graph determinism | projection rebuild idempotency tests | demo/graph tests | IMPLEMENTED |
| Scenario determinism | scenario result hashing / demo materialize | `pytest tests/scenarios` + demo | IMPLEMENTED |
| Citation binding | CoS citation validation | `pytest tests/chief_of_staff` | IMPLEMENTED |
| Idempotency (seed/ingest) | demo seed second-run; connector receipts | demo + connector tests | IMPLEMENTED |
| Migration integrity | single Alembic head | `alembic heads`; `alembic check` | IMPLEMENTED |
| Backend tests | `backend/tests` | `pytest -rs` | IMPLEMENTED |
| Frontend tests | Vitest | `npm test -- --run` | IMPLEMENTED |
| E2E tests | Playwright | `npx playwright test` | IMPLEMENTED |
| Dependency audits | pip-audit, npm audit --omit=dev | CI security + local | IMPLEMENTED |
| CI workflows | `.github/workflows/*` | GitHub Actions | IMPLEMENTED |
| Executive briefing UI | `frontend/src/app/briefing` | Vitest + Playwright briefing | IMPLEMENTED (Prompt 10) |
| Microsoft endorsement | — | — | **NOT CLAIMED** |
| SOC 2 / ISO / pen-test done | — | — | **NOT CLAIMED** |
| Production customers / ROI | — | — | **NOT CLAIMED** |
| Calibrated NovaBank probability | prediction registry gates | prediction tests show unpromoted | **NOT CLAIMED** |
| Causal scenario outcomes | scenario docs + UI labels | runbook disclaimers | **NOT CLAIMED** |

## How to use

During diligence, re-run verification commands on the evaluated revision.
Update counts in README/case study only from fresh runs.
