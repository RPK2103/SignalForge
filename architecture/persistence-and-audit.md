# SignalForge Persistence, History, Human Review and Audit Events

**Status:** Implemented (Phase 2, Prompt 5)
**Policy version:** v1
**Snapshot schema version:** 1
**Last verified:** 2026-07-22

---

## 1. Executive Summary

Phase 2 Prompt 5 adds a production persistence layer to SignalForge. The system durably stores catalog data, immutable assessment and simulation snapshots, append-only human reviews, and append-only audit events.

New `/api/v2` history endpoints compute readiness or simulation through the existing deterministic engines, persist complete snapshots in a single transaction, and return stored results on retrieval without recomputation.

Compute-only routes (`POST /api/v2/readiness/assess`, `POST /api/v2/simulations`) remain unchanged and continue to use the in-memory mock catalog. Persistence endpoints require a configured `DATABASE_URL`, migrated schema, and seeded catalog data.

Validation status:

| Area | Status |
|------|--------|
| SQLite (local dev and tests) | Fully validated |
| PostgreSQL schema compatibility | Reviewed (portable types, DDL, psycopg URL normalization) |
| Live PostgreSQL deployment | **Not tested** |
| Automated tests | **242 passed** (198 pre-persistence + 44 new) |

Alembic revision: `d573b27e3974` (`initial_persistence_schema`)

---

## 2. Scope and Non-Goals

### In scope

- SQLAlchemy 2.x ORM models separate from domain models
- Alembic migrations (no `create_all` production shortcut)
- Catalog, assessment, simulation, review, audit, and demo-scenario tables
- Immutable input and result snapshots with SHA-256 integrity hashes
- Queryable risk-finding and decision-trace projections
- Unit of Work with atomic commits
- Paginated assessment and simulation history APIs
- Append-only human reviews with bounded states
- Append-only audit events created in the same transaction as aggregates
- Idempotent seed command: `python -m app.db.seed`
- SQLite test fixtures and disposable-database migration tests
- Centralized persistence error mapping via `APIErrorResponse`

### Non-goals (deferred)

- AI leadership briefs
- Azure OpenAI integration in persistence paths
- Frontend history UI or API wiring
- Authentication and authorization
- Public audit-history API
- Docker or live PostgreSQL deployment validation
- Automatic migration or seeding at application startup
- Switching compute-only v2 routes to SQL catalog

---

## 3. Database Technology Choice

| Component | Choice |
|-----------|--------|
| ORM | SQLAlchemy 2.0.41 |
| Migrations | Alembic 1.16.2 |
| PostgreSQL driver | psycopg 3 (`psycopg[binary]==3.2.9`) |
| Local default | SQLite file (`sqlite:///./signalforge.db`) |
| Configuration | `DATABASE_URL` via pydantic-settings |

The application does not connect to the database at import time. Engine initialization is lazy through `init_engine()` when persistence dependencies are resolved.

---

## 4. Sync versus Async Decision

**Synchronous SQLAlchemy** is used throughout.

Rationale:

- Existing readiness and simulation orchestrators are synchronous
- Test suite uses synchronous `TestClient` and pytest fixtures
- FastAPI route handlers for persistence are synchronous `def` endpoints
- One request-scoped `Session` with explicit commit/rollback is simpler and predictable

Async SQLAlchemy sessions were not introduced. No hidden global mutable session is shared across requests.

---

## 5. Package Structure

```
backend/app/db/
    __init__.py
    base.py              # Declarative Base, constraint naming convention
    session.py           # Engine factory, URL normalization, session scope
    types.py             # PortableJSON (JSON/JSONB), new_uuid()
    unit_of_work.py      # UnitOfWork coordinating repositories
    seed.py              # Idempotent catalog and scenario seed command
    models/
        catalog.py       # Capabilities, engineers, projects, mappings
        assessment.py    # Assessments, risk findings, decision traces
        simulation.py    # Simulations
        review.py        # Human reviews
        audit.py         # Audit events
        scenario.py      # Demo scenarios
    repositories/
        sql_repositories.py   # SQLAlchemy repository implementations

backend/app/repositories/
    catalog_repository.py       # Existing catalog protocol
    mock_catalog_repository.py  # In-memory catalog (compute-only routes)
    persistence_repository.py   # Assessment/simulation/review/audit protocols

backend/app/services/persistence/
    assessment_persistence_service.py
    simulation_persistence_service.py
    review_persistence_service.py
    snapshot_service.py
    exceptions.py

backend/app/api/
    persistence_dependencies.py
    v2/assessments.py
    v2/simulation_records.py

backend/alembic/
    env.py
    versions/d573b27e3974_initial_persistence_schema.py
```

---

## 6. Dependency Direction

Required call chain:

```
API route
  → Pydantic request validation
  → persistence application service
  → Unit of Work
  → repository interfaces (Protocol)
  → SQLAlchemy repository implementations
  → Session
  → database
```

For compute-and-persist flows:

```
API route
  → persistence application service
  → SQL-backed catalog (via UnitOfWork)
  → ReadinessOrchestrator / SimulationOrchestrator (domain, DB-unaware)
  → snapshot_service (canonical JSON + hashes)
  → UnitOfWork (assessment/simulation + projections + audit)
  → single commit
```

Domain services (`ReadinessOrchestrator`, `SimulationOrchestrator`) do not import SQLAlchemy. ORM models never appear in API responses.

---

## 7. ORM/Domain Separation

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Domain models | `app/domain/` | Scoring, enums, simulation operations |
| Persistence DTOs | `app/domain/persistence_models.py` | Record shapes returned by repositories |
| API schemas | `app/schemas/api_v2.py` | Request/response contracts |
| ORM models | `app/db/models/` | Table mappings only |
| Repositories | `app/db/repositories/sql_repositories.py` | ORM ↔ DTO mapping |

SQLAlchemy models are never imported into domain modules. Lazy-loaded ORM relationships are not exposed through APIs.

---

## 8. Database Identity Model

| Identity | Type | Purpose |
|----------|------|---------|
| `capability_id`, `engineer_id`, `project_id`, `scenario_id` | Stable string PKs | Catalog and scenario references |
| `assessment_id` | 16-char SHA-256 prefix | Deterministic logical assessment fingerprint |
| `simulation_id` | 16-char SHA-256 prefix | Deterministic logical simulation fingerprint |
| `assessment_record_id` | UUID | Immutable persisted assessment execution |
| `simulation_record_id` | UUID | Immutable persisted simulation execution |
| `review_id` | UUID | Append-only human review row |
| `audit_event_id` | UUID | Append-only audit event row |

Record UUIDs are generated via `app.db.types.new_uuid()` at persistence time. They do not participate in score calculation.

---

## 9. Deterministic ID versus Record ID

**Deterministic IDs** (`assessment_id`, `simulation_id`) are built by `app/services/identifiers.py` from canonical request inputs and `policy_version`. Identical inputs produce identical fingerprints across compute-only and persistence paths.

**Record IDs** (`assessment_record_id`, `simulation_record_id`) identify each durable write. Repeated logical computations with the same deterministic ID create **distinct** record IDs when persisted separately.

Rules:

- Deterministic IDs appear in API responses unchanged from pre-persistence behavior
- Record IDs are never substituted for deterministic IDs in scoring
- History list endpoints expose both identifiers
- Filtering by `assessment_id` or `simulation_id` returns all matching persisted executions

Public identifier builders were extracted from private orchestrator helpers in pre-persistence cleanup (`build_assessment_id`, `build_simulation_id`).

---

## 10. Catalog Schema

Tables: `capabilities`, `engineers`, `engineer_capabilities`, `projects`, `project_requirements`

| Table | Key fields |
|-------|------------|
| `capabilities` | `capability_id` PK, name, description, category, schema_version, timestamps |
| `engineers` | `engineer_id` PK, name, role_title, experience_years, evidence flags, schema_version |
| `engineer_capabilities` | engineer + capability FKs, proficiency, evidence_sources JSON; unique `(engineer_id, capability_id)` |
| `projects` | `project_id` PK, name, description, schema_version |
| `project_requirements` | project + capability FKs, required_level, weight, critical; unique `(project_id, capability_id)` |

Catalog rows are mutable (descriptions and mappings may be updated by seed re-runs). Historical assessment and simulation snapshots are **not** updated when catalog rows change.

`SqlCatalogRepository` maps ORM rows to the existing domain catalog models consumed by readiness and simulation orchestrators. Parity with `MockCatalogRepository` is tested.

---

## 11. Assessment Schema

Table: `assessments`

| Column | Notes |
|--------|-------|
| `assessment_record_id` | UUID primary key |
| `assessment_id` | Deterministic fingerprint, indexed |
| `project_id` | FK → `projects.project_id` |
| `policy_version`, `schema_version` | Version tracking |
| `input_snapshot`, `result_snapshot` | Portable JSON |
| `input_snapshot_hash`, `result_snapshot_hash` | SHA-256 integrity |
| `readiness_score`, `confidence_score`, `confidence_level` | Query projections |
| `created_at` | UTC timestamp, indexed |
| `actor_reference`, `status` | Optional metadata |

Child projection tables (immutable relative to parent snapshot):

- `assessment_risk_findings` — finding_type, severity, capability_id, engineer_id, message
- `assessment_decision_traces` — step, component, label, value, contribution, sort_order

The `result_snapshot` JSON is the historical source of truth. Projections support listing and analytics; they do not replace stored snapshots.

---

## 12. Simulation Schema

Table: `simulations`

| Column | Notes |
|--------|-------|
| `simulation_record_id` | UUID primary key |
| `simulation_id` | Deterministic fingerprint, indexed |
| `project_id` | FK → `projects.project_id` |
| `operation_type` | add, remove, replace, compare |
| `policy_version`, `schema_version` | Version tracking |
| `input_snapshot` + hash | Normalized request |
| `baseline_snapshot` + hash | Full baseline readiness envelope |
| `proposed_snapshot` + hash | Full proposed readiness envelope |
| `result_snapshot` + hash | Complete simulation result |
| `readiness_delta`, `confidence_delta` | Query projections |
| `created_at` | UTC timestamp, indexed |

Each simulation stores four immutable snapshots. Retrieval deserializes stored JSON; it does not re-invoke the simulation engine.

---

## 13. Human Review Schema

Table: `human_reviews`

| Column | Notes |
|--------|-------|
| `review_id` | UUID primary key |
| `assessment_record_id` | FK → `assessments.assessment_record_id`, indexed |
| `state` | `accepted`, `overridden`, `needs_more_data` |
| `override_reason` | Required when state is `overridden` |
| `comment` | Required when state is `needs_more_data` |
| `reviewer_reference` | Optional actor reference |
| `created_at` | UTC timestamp |
| `schema_version` | Review record version |

Reviews are append-only. Latest state is derived from chronological ordering (`get_latest_for_assessment`). No UPDATE or DELETE APIs exist. Reviews never mutate assessment snapshots or scores.

---

## 14. Audit-Event Schema

Table: `audit_events`

| Column | Notes |
|--------|-------|
| `audit_event_id` | UUID primary key |
| `event_type` | `assessment_created`, `simulation_created`, `human_review_created` |
| `aggregate_type` | `assessment`, `simulation`, `human_review` |
| `aggregate_record_id` | UUID reference to aggregate |
| `actor_reference` | Optional |
| `event_version` | Event schema version (`1`) |
| `metadata` | Safe JSON (deterministic IDs, policy version, hashes — no secrets) |
| `payload_hash` | Optional integrity reference |
| `occurred_at` | UTC timestamp, indexed |

Composite index on `(aggregate_type, aggregate_record_id)`. Audit rows are append-only with no public update/delete surface.

---

## 15. Snapshot Model

Every persisted assessment stores:

- Normalized **input snapshot** (project_id, engineer_ids, policy_version, schema_version)
- Complete **result snapshot** (full `ReadinessAssessResponse` serialized)

Every persisted simulation stores:

- **Input snapshot** (project, baseline team, operation, policy_version)
- **Baseline assessment snapshot**
- **Proposed assessment snapshot**
- **Result snapshot** (full `SimulationResponse`)

Snapshot envelope structure:

```json
{
  "schema_version": "1",
  "policy_version": "v1",
  "data": { }
}
```

`SNAPSHOT_SCHEMA_VERSION = "1"` is defined in `app/domain/persistence_models.py`.

---

## 16. Snapshot Canonicalization

Implemented in `app/services/persistence/snapshot_service.py`:

- Pydantic models serialized with `model_dump(mode="json")`
- Enum values normalized to plain strings
- Dictionary keys sorted recursively for stable JSON
- Lists preserved in semantic order (decision traces keep `sort_order`)
- Engineer IDs normalized to lowercase trimmed unique sorted sets for input snapshots
- Original domain models are never mutated in place

Assessment input snapshots canonicalize `project_id` and `engineer_ids`. Simulation input snapshots include canonical operation payloads.

---

## 17. Snapshot Hashes

Hashes use SHA-256 over canonical JSON:

```python
json.dumps(normalized, sort_keys=True, separators=(",", ":"))
hashlib.sha256(...).hexdigest()
```

Each persisted aggregate stores hashes alongside snapshots. On retrieval, `verify_snapshot_hash()` recomputes and compares. Mismatch raises `SnapshotIntegrityError` (HTTP 500, `error_type: snapshot_integrity_error`) without exposing raw stored JSON.

API list responses return summary fields only. Detail responses include hashes and deserialized results.

---

## 18. Historical Immutability

Historical retrieval **never** calls `ReadinessOrchestrator` or `SimulationOrchestrator`.

`GET /api/v2/assessments/{assessment_record_id}` and `GET /api/v2/simulation-records/{simulation_record_id}`:

1. Load stored row by record UUID
2. Verify snapshot hashes
3. Deserialize stored snapshot JSON into existing API response models
4. Return stored result

Tests prove that modifying current catalog rows (engineer capabilities, project requirements) does not change retrieved historical records. New assessments or simulations after catalog changes reflect updated catalog data.

Human reviews do not alter stored assessment snapshot hashes.

---

## 19. Risk and Trace Projections

When an assessment is persisted, risk findings and decision-trace entries are written to child tables in the same transaction as the parent assessment row.

Projections are derived from the computed result at write time. They enable indexed querying and list summaries. They are not updated when catalog data changes and do not replace the immutable `result_snapshot`.

If projection insertion fails, the Unit of Work rolls back the entire assessment write including audit events.

---

## 20. Transaction Boundaries

| Operation | Atomic units |
|-----------|--------------|
| Assessment persist | assessment row + input/result snapshots + risk projections + trace projections + `assessment_created` audit event |
| Simulation persist | simulation row + four snapshots + `simulation_created` audit event |
| Human review | review row + `human_review_created` audit event |

Repositories do **not** call `commit()`. The Unit of Work owns commit and rollback. Partial writes are not committed.

Persistence API dependencies create one session per request via `get_db_session()`, wrapped in a `UnitOfWork`.

---

## 21. Unit of Work

`app/db/unit_of_work.py`:

```python
class UnitOfWork:
    catalog: CatalogRepository       # SqlCatalogRepository
    assessments: AssessmentRepository
    simulations: SimulationRepository
    reviews: HumanReviewRepository
    audit_events: AuditEventRepository

    def execute(callback) -> T:  # commit on success, rollback on exception
```

Application services pass a callback to `execute()` for atomic multi-repository writes. Read paths use repository methods directly without committing.

---

## 22. Rollback Behavior

On any exception inside `UnitOfWork.execute()`:

1. `session.rollback()` is invoked
2. No partial parent or child rows remain visible to other sessions
3. No audit event is committed
4. Session is closed when the request completes

Test fixtures use disposable SQLite databases with transaction rollback between tests where appropriate. Migration downgrade tests run only against temporary database files.

---

## 23. API Contracts

### Compute-only (unchanged)

| Method | Path | Catalog source |
|--------|------|----------------|
| POST | `/api/v2/readiness/assess` | Mock catalog |
| POST | `/api/v2/simulations` | Mock catalog |

### Assessment history

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v2/assessments` | Compute + persist assessment |
| GET | `/api/v2/assessments` | Paginated history (summary items) |
| GET | `/api/v2/assessments/{assessment_record_id}` | Stored snapshot + reviews |
| POST | `/api/v2/assessments/{assessment_record_id}/reviews` | Append human review |

### Simulation history

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v2/simulation-records` | Compute + persist simulation |
| GET | `/api/v2/simulation-records` | Paginated history |
| GET | `/api/v2/simulation-records/{simulation_record_id}` | Stored snapshots + result |

`simulation-records` is used instead of overloading `/api/v2/simulations` so the existing compute-only contract remains stable.

POST persistence routes require `Content-Type: application/json` (or structured `application/*+json`) via `require_json_content_type`.

OpenAPI tags: `Assessment History`, `Simulation History`.

---

## 24. Pagination

Offset/limit pagination on list endpoints:

| Parameter | Default | Maximum |
|-----------|---------|---------|
| `limit` | 20 | 100 |
| `offset` | 0 | — |

Ordering: newest first by `created_at`, then by record UUID for stable ties.

Assessment list filters: `project_id`, `assessment_id` (deterministic), `review_state`.

Simulation list filters: `project_id`, `simulation_id` (deterministic).

Response wrappers: `PaginatedAssessmentList`, `PaginatedSimulationList` with `items`, `total`, `limit`, `offset`.

---

## 25. Error Behavior

Persistence exceptions map to centralized `APIErrorResponse`:

| Exception | HTTP | `error_type` |
|-----------|------|--------------|
| `RecordNotFoundError` | 404 | `record_not_found` |
| `DatabaseUnavailableError` | 503 | `database_unavailable` |
| `PersistenceConflictError` | 409 | `persistence_conflict` |
| `SnapshotIntegrityError` | 500 | `snapshot_integrity_error` |
| `PersistenceValidationError` | 422 | `validation_error` |
| Unsupported Content-Type | 415 | `unsupported_media_type` |

SQL statements, driver errors, connection strings, and stack traces are not exposed to clients. Missing `DATABASE_URL` when calling persistence endpoints returns 503.

Pydantic validation on review requests enforces state-specific field requirements before persistence.

---

## 26. Migration Commands

Run from `backend/` with `DATABASE_URL` set:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic heads
```

Disposable test-only downgrade:

```bash
python -m alembic downgrade base
python -m alembic upgrade head
```

**Do not** run `downgrade base` against developer or deployment databases.

| Property | Value |
|----------|-------|
| Revision ID | `d573b27e3974` |
| Description | `initial_persistence_schema` |
| Head count | 1 |
| Tables created | 13 (+ `alembic_version`) |

Application startup does **not** run migrations automatically.

---

## 27. Seed Command

```bash
cd backend
python -m app.db.seed
```

Requirements:

- Migrated schema must exist (`alembic upgrade head`)
- Does **not** call `create_all`
- Does **not** run at application startup

Idempotent behavior:

- First run inserts catalog, requirements, and scenarios
- Subsequent runs create no duplicate rows
- Stable IDs unchanged
- Mutable catalog descriptions may update on re-seed
- Historical snapshots untouched

Seed prints a concise summary (counts created/updated). No secrets are logged.

---

## 28. Seed Scenarios

Eight named demo scenarios in `demo_scenarios`:

| Scenario ID | Name | Type |
|-------------|------|------|
| `azure_ai_migration` | Azure AI Migration | readiness |
| `cloud_modernization` | Cloud Modernization | readiness |
| `legacy_backend_refactor` | Legacy Backend Refactor | readiness |
| `data_platform_migration` | Data Platform Migration | readiness |
| `genai_assistant_build` | GenAI Assistant Build | readiness |
| `critical_engineer_exit` | Critical Engineer Exit | simulation (Kavi removal) |
| `understaffed_team` | Understaffed Team | readiness |
| `balanced_team` | Balanced Team | simulation |

Scenarios store project reference, baseline engineer IDs, and optional simulation operation JSON. Precomputed scores are **not** seeded.

---

## 29. SQLite Support

SQLite is the validated local and test database.

Configuration (`app/db/session.py`):

- `check_same_thread=False` for test and request-scoped sessions
- `PRAGMA foreign_keys=ON` on connect
- Default URL: `sqlite:///./signalforge.db`

Tests use:

- Temporary file databases for migration lifecycle tests
- In-memory or isolated file databases for repository and API tests
- No writes to developer `signalforge.db` during pytest

Full upgrade, seed, API, and e2e flows pass against SQLite.

---

## 30. PostgreSQL Compatibility

Compatibility reviewed without live PostgreSQL connection:

| Area | Approach |
|------|----------|
| Driver | psycopg 3 via `postgresql+psycopg://` URL normalization |
| URL aliases | `postgres://` rewritten to `postgresql://` |
| JSON columns | `PortableJSON` → JSONB on PostgreSQL, JSON on SQLite |
| UUID columns | Native `Uuid()` type |
| Constraints | Named PK/FK/unique constraints in migration |
| DDL | Alembic migration manually reviewed for portable SQL |

**Live PostgreSQL deployment validation is deferred.** Do not claim production PostgreSQL testing until a live instance is exercised end-to-end.

---

## 31. Security Considerations

- No authentication or authorization on persistence endpoints (MVP policy)
- Audit metadata excludes secrets, database URLs, API keys, and stack traces
- Snapshot and error responses do not expose raw connection strings
- `DATABASE_URL` credentials are not logged at startup or in seed output
- Historical data is readable by any caller with API access — acceptable for demo; tighten before production
- Human review `override_reason` and `comment` are stored as provided; no PII scrubbing in this phase

---

## 32. Test Strategy

**242 tests total** — 198 pre-persistence baseline preserved, **44 new** persistence tests.

| Suite | Path | Focus |
|-------|------|-------|
| Migrations | `tests/persistence/test_migrations.py` | Upgrade, single head, downgrade/re-upgrade, `alembic check` drift |
| Catalog | `tests/persistence/test_catalog_repository.py` | SQL/mock parity |
| Assessments | `tests/persistence/test_assessment_repository.py` | CRUD, filters, distinct record IDs |
| Simulations | `tests/persistence/test_simulation_repository.py` | Snapshots, list, deterministic ID |
| Reviews | `tests/persistence/test_reviews.py` | Append-only, validation |
| Audit | `tests/persistence/test_audit_events.py` | Event creation, linkage |
| Snapshots | `tests/persistence/test_snapshots.py` | Hashing, immutability after catalog change |
| Seed | `tests/persistence/test_seed.py` | Idempotency |
| Assessment API | `tests/api/test_assessment_history_api.py` | HTTP contracts, Content-Type |
| Simulation API | `tests/api/test_simulation_history_api.py` | HTTP contracts, Content-Type |
| E2E flow | `tests/e2e/test_persistence_v2_flow.py` | Cross-layer assessment → review → simulation → immutability |

Pre-persistence intelligence, readiness API, simulation API, and e2e suites remain green.

Warnings: 1 pre-existing Starlette/httpx deprecation; 2 httpx content upload deprecations in Content-Type tests.

---

## 33. Live Validation Results

Validated via pytest suites and optional script `backend/scripts/live_persistence_validation.py`:

1. Set disposable `DATABASE_URL` (temporary SQLite file)
2. `python -m alembic upgrade head`
3. `python -m app.db.seed`
4. Start Uvicorn (`python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`)
5. POST/GET assessment and simulation-record flows
6. POST human reviews
7. Validate 404/415 error paths
8. Stop server and delete temporary database

Script uses httpx against local Uvicorn. No secrets or machine-specific absolute paths.

---

## 34. Known Limitations

- Compute-only v2 routes still use `MockCatalogRepository`; SQL catalog is only used by persistence endpoints
- No public audit query API (repository-level inspection in tests only)
- No cursor-based pagination (offset/limit only)
- No soft delete or archival for assessments or simulations
- `DATABASE_URL` must be set explicitly for persistence endpoints; default applies when unset but persistence dependency checks configuration
- Live PostgreSQL not validated
- No connection pooling tuning documented for production
- Frontend does not consume history APIs

---

## 35. Deferred AI Integration

Persistence paths do not invoke Azure OpenAI. Audit events, snapshots, and reviews contain no AI-generated fields. AI leadership briefs remain a future phase.

Existing AI routes (`/generate-insight`, `/copilot`) are unaffected and remain separate from persistence.

---

## 36. Deferred Frontend Integration

The Next.js frontend was not modified. No history UI, review workflow UI, or `DATABASE_URL`-dependent client wiring was added. Frontend integration belongs to a later phase after API stabilization.

The legacy static dashboard at `/dashboard` continues to call unversioned MVP routes only.

---

## 37. Deployment Migration Procedure

Recommended first-time persistence deployment:

1. Provision PostgreSQL (or use SQLite for demo-only deployments)
2. Set `DATABASE_URL` in platform environment (Render, Docker, local `.env`)
3. Deploy application code including Alembic migration `d573b27e3974`
4. Run migrations **before** serving traffic:
   ```bash
   cd backend && python -m alembic upgrade head
   ```
5. Run seed once per environment:
   ```bash
   cd backend && python -m app.db.seed
   ```
6. Verify `/health` and persistence endpoints
7. Confirm compute-only routes still respond without requiring seeded data for mock-catalog operation

Migrations are **not** executed automatically on app boot. CI should run pytest including persistence suites.

`render.yaml` documents backend deployment; add `DATABASE_URL` in Render dashboard for persistence-enabled environments.

---

## 38. Rollback Considerations

### Application rollback

Deploying a previous application version without persistence endpoints is safe for compute-only consumers. Legacy and v2 compute routes do not depend on the database.

If rolling back **after** persistence data exists:

- Historical records remain in the database but are inaccessible until a persistence-capable version is restored
- No automatic data migration on downgrade

### Schema rollback

`alembic downgrade base` drops all persistence tables including assessments, simulations, reviews, and audit events. **This is destructive.** Use only on disposable databases.

Production rollback procedure:

1. Prefer forward-fix (new migration) over schema downgrade
2. If downgrade is required, backup database first
3. Never run `downgrade base` against production without explicit approval and backup

### Seed rollback

Seed command is non-destructive to historical snapshots. Re-running seed updates catalog rows idempotently; it does not delete assessments or simulations.

---

*End of persistence and audit architecture.*
