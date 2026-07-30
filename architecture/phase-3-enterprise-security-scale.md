# Phase 3 — Enterprise Security and Scale (Prompt 7)

This document describes the enterprise security foundation added in Prompt 7:
verified request identity, authenticated tenant selection, deny-by-default RBAC,
service-layer authorization, PostgreSQL row-level security (RLS), append-only
security auditing, production-safe configuration, and bounded high-volume reads.

> **Scope honesty.** Prompt 7 establishes a security *foundation*. It is **not**
> a penetration test, SOC 2 / ISO 27001 certification, Microsoft endorsement, or
> a completed zero-trust architecture. See [Security limitations](#security-limitations).

---

## 1. Threat model and trust boundaries

| Boundary | Before Prompt 7 | After Prompt 7 |
| --- | --- | --- |
| Caller identity | none — the `X-SignalForge-Tenant-ID` header was trusted context | verified bearer principal (Entra JWT / signed dev-JWT) |
| Tenant selection | header value trusted directly | header is a *selector*; membership proven by an active `SecurityPrincipal` row or a signed claim |
| Authorization | none | deny-by-default RBAC enforced at the **service layer** and API |
| DB isolation | application/repository predicates only | repository predicates **plus** PostgreSQL RLS (defense in depth) |
| Auditability | none for authz | append-only `ent_security_audit_events` |

**In-scope threats:** unauthenticated access, forged tenant headers, cross-tenant
IDOR (ORM and direct SQL), algorithm-confusion / `alg:none`, expired/forged
tokens, privilege escalation via unknown roles/permissions, pooled-connection
tenant leakage, secret leakage into audit logs, misconfigured production startup.

**Out of scope (deferred / documented):** SCIM, Entra group sync, distributed
rate limiting, WAF, SIEM, automated incident response, key-rotation
orchestration, customer-managed keys, cross-region replication.

---

## 2. Identity flow

```
Browser / service
  │  Authorization: Bearer <JWT>       X-SignalForge-Tenant-ID: <tenant>
  ▼
AuthenticationMiddleware               (DEFAULT-DENY: every path except the public
  │  verifies signature/claims             allowlist requires a verified principal)
  │  -> AuthenticatedPrincipal on request.state
  ▼
get_security_context                   (selects tenant, sets RLS GUC transaction-locally)
  │  SecurityContextResolver -> roles + effective permissions
  ▼
require_permission(<Permission>)       (deny-by-default; audits denials)
  ▼
Service layer                          (sensitive-mutation services re-check via
                                        AuthorizationService — see §6 for exact coverage)
```

**Public route allowlist (the only unauthenticated paths):**

| Path | Public? | Notes |
| --- | --- | --- |
| `/` | always | liveness banner |
| `/health` | always | health check |
| `/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect` | dev/test only | gated by `DOCS_ENABLED`; **unregistered and unreachable in production** |
| `/dashboard/*` | always (static) | SPA assets; the SPA then authenticates its API calls with a bearer token |

Authentication is **default-deny**: the middleware is configured with an explicit
public allowlist (`app/main.py`) and everything else — `/api/v2`, `/api/v3`, **and
every legacy root route** (`/analyze`, `/project-fit`, `/assess-risk`,
`/recommend-team`, `/generate-insight`, `/simulate`, `/success-prediction`,
`/copilot`) — requires a verified principal. There is no prefix allowlist that a
future route can silently bypass. `OPTIONS`/CORS preflight carries no credentials
and is allowed through.

---

## 3. Authentication modes

| Mode | Where | Verifier | Notes |
| --- | --- | --- | --- |
| `entra_oidc` | production | `EntraJwtVerifier` (RS256/384/512) | JWKS-backed asymmetric verification |
| `local_development` | developer machines | `SymmetricJwtVerifier` (HS256) | signed short-lived dev JWTs; **rejected in production** |
| `test` | pytest / Playwright | `SymmetricJwtVerifier` (HS256) | isolated issuer/audience/secret; **impossible in production** |

Fail-closed rules (enforced in `SecuritySettings.validate_for_environment` and
`validate_startup_security`, called at app import):

- production **must** use `entra_oidc`;
- production requires `ENTRA_ISSUER`, `ENTRA_AUDIENCE`, `ENTRA_JWKS_URI`, at least
  one `ENTRA_ALLOWED_TENANT_IDS`;
- production must have `DOCS_ENABLED=false`, explicit non-wildcard `TRUSTED_HOSTS`,
  and **no** `SIGNALFORGE_LOCAL_AUTH_SECRET`;
- wildcard CORS origin (`*`) is rejected in every environment (the API sends no
  credentials, but wildcard-with-credentials is structurally impossible here).

### Entra JWT validation

`EntraJwtVerifier` validates: signature, explicit algorithm allowlist (never
`none`, never symmetric), issuer, audience, `exp`, `nbf`, `iat`, tenant (`tid`)
against the configured allowlist, stable subject (`sub`), key id (`kid`), and a
configurable clock skew. Oversized tokens are rejected before parsing.

### Bounded JWKS caching

`BoundedJwksCache` fetches signing keys with a configurable TTL, refreshes on an
unknown `kid` (key rotation), bounds the response size and request timeout, and
maps provider failures to safe categories (`jwks_unavailable`, `jwks_malformed`).
No raw token or full JWKS payload is ever logged. Unit tests use a fake JWKS
client and locally generated RSA keys — **no network access**.

### Local development authentication

`local_development` mode issues signed short-lived HS256 JWTs via the CLI:

```
python -m app.security issue-dev-token --subject dev --tenant novabank --roles tenant_admin
```

The signing secret comes only from `SIGNALFORGE_LOCAL_AUTH_SECRET` (no default,
minimum 32 chars). There is **no public API endpoint** that issues tokens, and
the secret/token is never placed in a `NEXT_PUBLIC_*` variable.

---

## 4. Tenant selection

1. A verified principal is established first.
2. The selected tenant comes from `X-SignalForge-Tenant-ID` or an unambiguous
   token claim. The header is a **selector only** — it never grants membership.
3. In `entra_oidc` mode, membership is proven by an **active** `SecurityPrincipal`
   row in the selected tenant; roles come from `RoleAssignment`.
4. In `local_development`/`test` mode, membership and roles come from signed
   claims (a `*` membership wildcard is used by the broad regression token).
5. Foreign and nonexistent tenants are externally indistinguishable (both surface
   as access-denied / 404), so tenant existence cannot be probed.

CLI/batch work uses an explicit `internal_system_context`, which is auditable and
still passes through `AuthorizationService` for permission-sensitive operations.

---

## 5. RBAC — role/permission matrix

Single versioned matrix in `app/security/permissions.py`
(`PERMISSION_MATRIX_VERSION`). Deny-by-default: unknown role → nothing, unknown
permission → denied, expired assignment → nothing, deactivated principal →
nothing, multiple roles → deterministic set-union.

| Role | Permissions |
| --- | --- |
| `tenant_admin` | all enterprise/connectors/graph/predictions/scenarios/chief_of_staff read+write, `predictions.promote`, and all `security.*` |
| `executive_reader` | `enterprise.read`, `graph.read`, `predictions.read`, `scenarios.read`, `chief_of_staff.read` |
| `engineering_leader` | `enterprise.read`, `connectors.read`, `graph.read`, `predictions.read`, `scenarios.read`, `scenarios.run`, `chief_of_staff.read` |
| `intelligence_analyst` | `enterprise.read`, `graph.read`, `predictions.read`, `predictions.validate`, `scenarios.read`, `chief_of_staff.read` |
| `integration_operator` | `enterprise.read`, `connectors.read`, `connectors.sync`, `connectors.manage`, `graph.read`, `graph.rebuild` |
| `security_auditor` | `security.audit.read`, `enterprise.read` |

`predictions.promote` and `security.*` administration are restricted to
`tenant_admin`. There is intentionally **no** employee-ranking / surveillance
permission.

---

## 6. Route and service-layer authorization

`AuthorizationService.require(context, permission, resource_tenant_id)` (and the
None-safe `require_context(context, permission)`) is a pure function of the passed
context — it consults no hidden global, so a **direct service call without a
context fails closed**. Tests call the services directly to prove route bypass is
impossible.

### 6.1 Route-permission tables

**Legacy root routes** (deterministic compute; authenticated + RBAC-gated in
`app/main.py`):

| Route | Permission |
| --- | --- |
| `/analyze`, `/project-fit`, `/assess-risk`, `/recommend-team` | `enterprise.read` |
| `/success-prediction` | `predictions.read` |
| `/simulate` | `scenarios.run` |
| `/generate-insight`, `/copilot` | `chief_of_staff.generate` |

These legacy routes are authenticated and route-RBAC-gated. Pure deterministic
compute functions receive no security dependency; authorization is at the route
entry point only (they persist nothing).

**`/api/v2`** (route RBAC in `app/api/v2/router.py` + per-route in
`assessments.py` / `simulation_records.py`):

| Operation | Route | Permission | Service re-check |
| --- | --- | --- | --- |
| Readiness assess / capabilities / catalog / engineers / projects | `GET/POST /api/v2/readiness/*`, `/api/v2/capabilities`, `/api/v2/catalog/*` | `enterprise.read` | n/a (stateless compute) |
| List/get assessments | `GET /api/v2/assessments*` | `enterprise.read` | — |
| Create assessment | `POST /api/v2/assessments` | `enterprise.manage` | `AssessmentPersistenceService.create_assessment` |
| List simulations | `GET /api/v2/simulations`, `/api/v2/simulation-records*` | `scenarios.read` | — |
| Run/persist simulation | `POST /api/v2/simulations/simulate`, `POST /api/v2/simulation-records` | `scenarios.run` | `SimulationPersistenceService.create_simulation` |
| List leadership briefs | `GET /api/v2/assessments/{id}/leadership-briefs` | `chief_of_staff.read` | — |
| Generate leadership brief | `POST /api/v2/assessments/{id}/leadership-brief` | `chief_of_staff.generate` | `LeadershipBriefPersistenceService.generate_leadership_brief` |
| Append brief human review | `POST /api/v2/assessments/{id}/leadership-brief/reviews` | `chief_of_staff.review` | `HumanReviewPersistenceService.add_review` |

**`/api/v3` enterprise ingestion / connectors** (route RBAC + service re-check):

| Operation | Route | Permission | Service re-check |
| --- | --- | --- | --- |
| Register data source | `POST /api/v3/data-sources` | `connectors.manage` | `IngestionService.register_data_source` |
| Start ingestion run | `POST /api/v3/ingestion-runs` | `connectors.sync` | `IngestionService.start_run` |
| Complete ingestion run | `POST /api/v3/ingestion-runs/{id}/complete` | `connectors.sync` | `IngestionService.complete_run` |
| Append evidence signal | `POST /api/v3/evidence-signals` | `connectors.sync` | `IngestionService.append_evidence` |
| Connector/ingestion reads | `GET /api/v3/...` | `connectors.read` / baseline read | — |
| Security audit read | `GET /api/v3/security/audit-events` | `security.audit.read` | `SecurityAdministrationService.read_audit` |
| Role / identity-provider administration | `POST/DELETE/PUT /api/v3/security/*` | `security.roles.manage` / `security.identity_providers.manage` | `SecurityAdministrationService` |

**Design decision — ingestion write mapping.** Registering or reconfiguring a
data source is *connector configuration* (`connectors.manage`); starting/completing
runs and appending normalized evidence is *ingestion execution*
(`connectors.sync`). Neither is a generic `enterprise.read`. This grants ingestion
write access to `tenant_admin` and `integration_operator` only; read-only roles
(`executive_reader`, `security_auditor`, `intelligence_analyst`) cannot write.

### 6.2 Application-service authorization boundary

Every reachable sensitive **mutation/generation** re-checks authorization at its
application-service entry point (not just the route), taking a non-optional
`SecurityContext` and calling `AuthorizationService`. Covered services:

- `IngestionService` — `register_data_source` (`connectors.manage`),
  `start_run` / `complete_run` / `append_evidence` (`connectors.sync`);
- `AssessmentPersistenceService.create_assessment` (`enterprise.manage`);
- `SimulationPersistenceService.create_simulation` (`scenarios.run`);
- `LeadershipBriefPersistenceService.generate_leadership_brief` (`chief_of_staff.generate`);
- `HumanReviewPersistenceService.add_review` (`chief_of_staff.review`);
- `SecurityAdministrationService` — all `security.*` administration + audit read.

A permission-coverage audit (`app/security/coverage.py`, enforced by
`tests/security/test_permission_coverage.py`) inventories every sensitive
permission and cross-checks its classification against **live route introspection**
and the admin-service source, so a dropped route dependency or an unenforced
sensitive permission fails the test.

### 6.3 CLI/service-only and deferred operations

The v3 **predictions**, **delivery-graph** and **scenarios** routers are
**read-only over HTTP**. Model training/validation/promotion (`predictions.*`),
graph rebuild (`graph.rebuild`) and scenario-watch mutation
(`scenarios.manage_watches`) have **no HTTP mutation route** and execute only
inside trusted internal batch/CLI processes — there is no unsecured HTTP call
path. Adding an explicit service-layer permission gate to these Prompt 4/5
execution services is tracked as **deferred** follow-up (it is outside the Prompt 7
broken-access-control remediation, which concerns reachable routes). These are
recorded as `DEFERRED` in the permission-coverage registry.

---

## 7. PostgreSQL row-level security

RLS is **PostgreSQL-only** defense in depth on top of the tenant-scoped
repository layer.

- **Protected tables:** every table with a NOT NULL `tenant_id` (derived
  deterministically from ORM metadata by `tenant_rls_tables`) — all `ent_*`
  tenant tables plus the new `ent_identity_providers`, `ent_security_principals`,
  `ent_role_assignments`. This is ~45 tables (see the migration's generated DDL).
- **Policy:** `tenant_id = current_setting('signalforge.current_tenant_id', true)`
  for `USING` and `WITH CHECK`.
- **FORCE ROW LEVEL SECURITY** is applied so the table owner cannot bypass
  isolation via ownership.
- **Audit table:** `ent_security_audit_events` keeps a nullable tenant only for
  pre-tenant authentication failures; its policy additionally requires
  `tenant_id IS NOT NULL`, so global rows are never tenant-visible.
- **Transaction-local context:** the tenant GUC is set with `set_config(..., true)`
  so a pooled connection never retains another request's tenant and a rollback
  clears it automatically. Missing context → `current_setting` is NULL →
  `tenant_id = NULL` is NULL → no rows match (**fail closed**).

### PostgreSQL role assumptions

| Role | Purpose | Privileges |
| --- | --- | --- |
| `signalforge_migrator` (migration/owner) | runs migrations, owns tables | full DDL |
| `signalforge_app` (application) | serves requests | `SELECT/INSERT/UPDATE/DELETE` only; **NOSUPERUSER**, **NOBYPASSRLS**, not the table owner |

The application role must never be a superuser and must never bypass RLS.

### SQLite behavior

SQLite does **not** enforce RLS. On SQLite the RLS helpers are no-ops and tenant
isolation relies entirely on the repository/service layer. **SQLite test success
is not proof of RLS.** RLS is proven only by the mandatory PostgreSQL CI job.

---

## 7a. PostgreSQL migration-chain portability

The Phase 3 migrations were authored and previously only executed on SQLite,
which hid three cross-dialect defects that block a clean PostgreSQL migration.
**No production PostgreSQL deployment has ever been claimed**, so these are
portability corrections to not-yet-production-validated migrations, not a rewrite
of released history.

| Defect | Fix | File(s) changed |
| --- | --- | --- |
| Revision ids exceed the default `alembic_version.version_num VARCHAR(32)` (e.g. `p3_continuous_scenario_intelligence` = 35 chars). SQLite ignores VARCHAR length; PostgreSQL rejects the insert. | Widen `version_num` to `VARCHAR(128)` via Alembic's documented `DefaultImpl.version_table_impl` hook (public since 1.14) for new DBs (online + offline `--sql`), plus an in-place widener for an existing narrower PostgreSQL column that never recreates/truncates the table. Revision ids are **not** renamed. | `app/db/alembic_version_table.py`, `alembic/env.py` |
| Boolean check compared a `Boolean` column to the integer `1` (`production_eligible = 1`), invalid on PostgreSQL. | Portable bare-boolean predicate `NOT (data_scope = 'synthetic' AND production_eligible)` (same semantics). | `alembic/versions/p3_delivery_prediction.py` |
| Numeric `sa.text("0")` server default and `training_eligible = 0` check on a `Boolean` column, invalid on PostgreSQL. | `server_default=sa.false()` (renders `0` on SQLite, `false` on PostgreSQL) and `NOT training_eligible` (same semantics). | `alembic/versions/p3_continuous_scenario_intelligence.py` |

**Cross-dialect evidence.** SQLite upgrades base→head, downgrades to
`p3_ai_chief_of_staff`, re-upgrades, and `alembic check` reports no drift. Offline
PostgreSQL `--sql` emits `version_num VARCHAR(128)`, `BOOLEAN DEFAULT false`, and
`CHECK (NOT ...)` (asserted by `tests/migrations/test_migration_portability.py`).
On a live disposable PostgreSQL 16, migrations reach head as a **non-superuser
owner**, `version_num` is `VARCHAR(128)`, RLS is enabled+forced with all tenant
policies created, and the full `tests/security_postgres` RLS suite passes as the
restricted non-superuser application role. (Local live *downgrade* on PostgreSQL
was validated only on SQLite in this environment; the RLS drop/create DDL is
symmetric and exercised by the enable/force path.)

---

## 8. Database and scale safeguards

`get_engine` applies production-safe PostgreSQL settings (ignored on SQLite):
pool size, max overflow, pool timeout, pool recycle, pool pre-ping, connection
timeout, application name, and a transaction-local `statement_timeout`.

Bounded reads: strict pagination maximums (audit page ≤ 100, role history ≤ 200),
stable ordering, keyset/cursor pagination over a monotonic `sequence_no` for
audit history, and bounded JWT/JWKS caches. Concurrency tests assert tenant
context does not leak across connections.

---

## 9. Security audit events

Append-only `ent_security_audit_events` (`SecurityAuditEventRepository` exposes no
update/delete). Stable action taxonomy (`SecurityAuditAction`) covers
authentication failures, authorization denials, role-assignment create/revoke,
identity-provider changes, connector configure/sync, graph rebuild, prediction
train/validate/promote, scenario execute/watch mutation, and Chief-of-Staff
generate/review.

- **Redaction:** identifiers are SHA-256 hashed; metadata is passed through
  `sanitize_metadata`, which drops secret-like keys and redacts token/JWT/`Bearer`
  values and bounds size. No bearer token, raw header, or secret is ever stored.
- **Fail-closed policy:** for `security.roles.manage`,
  `security.identity_providers.manage`, and `predictions.promote`, a failed audit
  write raises `AuditWriteError` and rolls back the mutation. Lower-risk
  operations log best-effort.
- **Access control:** audit reads require `security.audit.read` (auditor / admin).

---

## 10. Frontend authentication boundary

- Central access-token provider (`src/lib/api/auth.ts`): token lives **in memory**
  only (never localStorage, never `NEXT_PUBLIC_*`, never hardcoded).
- The API client attaches `Authorization: Bearer <token>` and the selected
  `X-SignalForge-Tenant-ID` on every request.
- 401 → `unauthorized` (signed-out) and 403 → `forbidden` (access-denied) are
  explicit categories with distinct messaging.
- **Local/test:** Playwright injects a short-lived signed dev-JWT via
  `window.__SIGNALFORGE_TEST_AUTH__` before the app loads. This seam is inert in
  production (the global is never set) and the backend rejects the dev/test modes
  in production regardless.

### Remaining production deployment steps (Entra browser login)

Full interactive Entra sign-in is deployment-specific and cannot be validated
locally. To finish it: register the SPA + API app registrations, wire an MSAL (or
equivalent) adapter into `setTokenProvider`, configure `ENTRA_ISSUER`,
`ENTRA_AUDIENCE`, `ENTRA_JWKS_URI`, `ENTRA_ALLOWED_TENANT_IDS`, and provision the
PostgreSQL `signalforge_app` / `signalforge_migrator` roles.

---

## 11. CI PostgreSQL validation

`.github/workflows/security-ci.yml` adds a **mandatory** `postgres-rls` job with a
PostgreSQL 16 service container. It creates a **non-superuser** `signalforge_app`
role, runs migrations as the privileged role, grants the app role table
privileges (no ownership), verifies the app role is not a superuser, and runs
`tests/security_postgres` + `tests/security` with `POSTGRES_TEST_URL` always set —
so the RLS tests are **never silently skipped** in CI.

Locally the PostgreSQL RLS suite is deferred (skipped) when `POSTGRES_TEST_URL` is
unset; it is collected and runs mandatorily in CI.

> No commit/push occurs during implementation, so remote CI has **not** yet been
> executed for this branch. Remote CI validation remains pending until release.

---

## 12. Deployment configuration

Required production environment: `APP_ENV=production`, `AUTH_MODE=entra_oidc`,
`ENTRA_ISSUER`, `ENTRA_AUDIENCE`, `ENTRA_JWKS_URI`, `ENTRA_ALLOWED_TENANT_IDS`,
explicit `CORS_ORIGINS`, explicit `TRUSTED_HOSTS`, `DOCS_ENABLED=false`,
`HSTS_ENABLED=true` (behind HTTPS), and separate PostgreSQL migration/application
roles. `SIGNALFORGE_LOCAL_AUTH_SECRET` must be **absent**.

Azure Key Vault is documented as a deployment integration; it is **not**
implemented in code (secrets are resolved from environment variables).

---

## Security limitations

- **Authentication:** interactive Entra browser login requires deployment-specific
  wiring not validated locally; only the provider boundary + local/test adapter
  are implemented.
- **RLS:** proven on PostgreSQL — locally on a disposable PostgreSQL 16 instance
  (migration to head as a non-superuser owner + the full `tests/security_postgres`
  isolation suite as the restricted app role) and mandatorily in CI. SQLite
  provides no RLS. Remote CI has not yet run for this branch (no push permitted
  during implementation). The live *downgrade→re-upgrade* cycle was validated on
  SQLite; on PostgreSQL only the upgrade + RLS creation/isolation were run locally.
- **Deferred service-layer gates:** model training/validation/promotion, graph
  rebuild and scenario-watch mutation have **no HTTP route** and run only via
  trusted internal batch/CLI; an explicit service-layer permission gate for these
  Prompt 4/5 execution services is deferred (documented `DEFERRED` in the
  permission-coverage registry). No unsecured HTTP call path exists.
- **Local validation:** the PostgreSQL RLS suite is deferred locally when no test
  database is available.
- **Scale:** bounded to safe DB/request behavior — no Redis, no distributed rate
  limiting, no queues/workers/sharding, no cross-region replication. No
  "millions of users" claim is made.
- **Frontend:** minimal boundary only — no account/profile pages, invitations,
  role-management UI, or SCIM UI.
- **Deferred (Prompt 8+):** observability platform, SIEM integration, automated
  incident response, key-rotation orchestration.
- **Evidence not obtained:** no penetration test, no SOC 2 / ISO 27001
  certification, no Microsoft endorsement, no customer security approval.
