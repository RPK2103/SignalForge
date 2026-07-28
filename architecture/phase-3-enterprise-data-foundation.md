# Phase 3 — Prompt 1: Enterprise Domain, Multi-Tenant Data Foundation

This document describes the tenant-scoped enterprise data foundation introduced
in Phase 3 Prompt 1. It replaces the simplified Phase 2 catalog assumptions with
an extensible, provenance-aware model while preserving every existing Phase 2
flow. It is a **foundation** only: connectors, delivery-graph projections,
prediction and authentication are explicitly deferred (see
[Deferred controls](#10-deferred-security-controls-phase-3-prompt-7)).

> **Scope honesty.** This milestone does **not** implement production
> multi-tenancy, real connector ingestion, authentication, RBAC, Entra ID,
> PostgreSQL row-level security, graph intelligence, calibrated prediction, the
> full Prompt 9 demo scale, live PostgreSQL, or production deployment.

---

## 1. Enterprise domain model

Twenty foundational concepts are modeled as strictly-typed Pydantic DTOs
(`app/domain/enterprise_models.py`) and SQLAlchemy ORM tables
(`app/db/models/enterprise.py`, all prefixed `ent_`). ORM rows never leave the
repository layer — services and the API only ever see domain DTOs.

| Bounded context | Entities |
| --- | --- |
| Organization hierarchy | `Organization`, `BusinessUnit`, `Department`, `Team` |
| People | `EngineerProfile` (non-sensitive operational attributes only) |
| Capability catalog | `EnterpriseCapability`, `EnterpriseSkill`, `CapabilitySkillLink`, `EngineerCapabilityEvidence`, `EngineerSkillEvidence`, `CapabilityRequirement` |
| Initiative & project | `Initiative`, `EnterpriseProject` |
| Delivery | `Repository`, `Sprint`, `WorkItem`, `Incident`, `Deployment` |
| Relationships | `Dependency`, `Ownership`, `Availability` |
| Provenance & ingestion | `DataSource`, `IngestionRun`, `EvidenceSignal` |

Enums (`app/domain/enterprise_enums.py`) are pure, stable string values — never
LLM-generated. Deterministic, tenant-scoped identifiers are built by
`app/domain/enterprise_identifiers.py` (`build_entity_id(prefix, tenant_id,
*natural_key)` → `prefix_<sha256[:20]>`).

```mermaid
flowchart TD
    subgraph Tenant boundary (tenant_id)
      ORG[Organization] --> BU[BusinessUnit] --> DEPT[Department] --> TEAM[Team]
      TEAM --> ENG[EngineerProfile]
      ORG --> INIT[Initiative] --> PROJ[EnterpriseProject]
      TEAM --> PROJ
      TEAM --> REPO[Repository]
      PROJ --> WI[WorkItem] --> SPR[Sprint]
      REPO --> INC[Incident]
      REPO --> DEP[Deployment]
      CAP[EnterpriseCapability] --> SKILL[EnterpriseSkill]
      ENG --> CAP
      DS[DataSource] --> RUN[IngestionRun] --> SIG[EvidenceSignal]
      SIG -. subject_type+subject_id .-> REPO
    end
```

### Engineer profile — sensitive-attribute prohibition

`EngineerProfile` carries only non-sensitive operational status (display name,
role title, level, `employment_state`, region). A domain guard
(`FORBIDDEN_ENGINEER_FIELDS`) plus `extra="forbid"` on every DTO rejects any
attempt to attach gender, ethnicity, religion, health, political views, age,
salary, personality/surveillance scores, or private message content. This is
enforced by `tests/enterprise/test_domain.py`.

---

## 2. Tenant-boundary design

Shared-schema multi-tenancy: **every** tenant-owned row has a non-null
`tenant_id`. Access never depends on a caller remembering a filter — an explicit
immutable `TenantContext` (`app/domain/tenant_context.py`) is threaded through
every service and repository method.

- `tenant_id` is the **security boundary** (a lowercase slug, validated).
- `organization_id` is the enterprise aggregate id. **Cardinality: exactly one
  organization per tenant** (enforced by a `UniqueConstraint("tenant_id")` on
  `ent_organizations` and by `EnterpriseHierarchyService.create_organization`).

Repository guarantees (`app/db/repositories/enterprise_repositories.py`):

- every method requires `TenantContext`; reads/writes/updates are tenant-qualified;
- parent references are resolved within the same tenant — a cross-tenant
  association raises `CrossTenantAccessError` (HTTP 422) and writes nothing;
- tenant-qualified absence is indistinguishable from non-existence (no
  cross-tenant existence disclosure);
- composite uniqueness is tenant-scoped (e.g. slugs/codes/external refs are
  unique per tenant, never globally);
- deterministic pagination (`Page[T]`, bounded page size ≤ 100, stable
  `ORDER BY <pk>`).

This is a **data-boundary** mechanism only — not authentication or authorization.

---

## 3. Temporal-data semantics

All datetimes are timezone-aware UTC. The model distinguishes:

| Field | Meaning |
| --- | --- |
| `created_at` / `updated_at` | record lifecycle |
| `event_time` | when the source event occurred |
| `observed_at` | when the source exposed/reported it |
| `ingested_at` | when SignalForge accepted it |
| `valid_from` / `valid_to` | business-valid relationship interval |
| `archived_at` | soft archival of a mutable catalog entity |

Interval rules are validated both in domain DTOs and, where portable, as SQL
`CHECK` constraints: `valid_to > valid_from`, availability/sprint end strictly
after start, deployment completion not before start, incident resolution not
before start. Naive datetimes read back from SQLite are assumed UTC by the
interval validator so contracts stay UTC-consistent.

---

## 4. Provenance and evidence model

- **`DataSource`** — provider-neutral source registration. Credentials are a
  nullable, opaque `credential_reference` (e.g. `vault://…#deferred`); **no
  plaintext secrets and no fake encrypted secrets** are stored.
- **`IngestionRun`** — records run type, status, `started_at`/`completed_at`,
  cursor, counts, `error_category`, and a **sanitized** `error_summary`
  (obvious secret markers are redacted).
- **`EvidenceSignal`** — append-only. Carries source/subject references, the full
  temporal triplet (`event_time`/`observed_at`/`ingested_at`),
  `schema_version`/`processing_version`, `confidence`,
  `permission_classification`, canonical `payload`, and a canonical SHA-256
  `payload_hash` computed with the existing `snapshot_hash` utility (no
  duplicate hashing implementation).

**Deduplication** uses the tuple
`(tenant_id, data_source_id, source_record_id, signal_type, payload_hash)`,
enforced by `uq_ent_evidence_signals_dedup`. Appending an identical signal
returns the existing record (`created=False`) instead of overwriting it; a lost
insert race is caught and resolved to the committed record. Evidence is never
silently mutated through the supported application paths.

**Append-only enforcement level.** Append-only is enforced at the repository and
API layers (no update/delete methods or routes). It is **not** database-
enforced: a direct SQL `UPDATE`/`DELETE` against `ent_evidence_signals` remains
possible. Repeated exact duplicates keep the original `ingestion_run_id`; a
separate observation/receipt model for later-run provenance is deferred to
Prompt 2.

---

## 5. Phase 2 backward-compatibility strategy

Phase 2 tables (`capabilities`, `engineers`, `projects`) gained a **nullable**
`tenant_id` column, backfilled to the deterministic `legacy-default` tenant by
the migration. Phase 2 rows, snapshots, scores and history are never rewritten
or recomputed. `LegacyCompatibilityService.project_catalog(ctx)` exposes a
tenant-scoped **read** projection of the legacy catalog without touching the
originals. All Phase 2 v1/v2 endpoints and behaviors are unchanged; a full
regression run (387 backend tests) passes.

---

## 6. NovaBank foundational demo model

`app/db/enterprise_seed.py` seeds a fictional bank (`tenant_id = novabank`).
Deterministic ids, fictional names, **no** real/scraped/sensitive data. First
run creates **223** rows; a second run creates **0** (idempotent). Counts:

| Entity | Count | Entity | Count |
| --- | --- | --- | --- |
| organizations | 1 | sprints | 6 |
| business units | 2 | work items | 30 |
| departments | 4 | incidents | 4 |
| teams | 6 | deployments | 10 |
| engineers | 15 | dependencies | 6 |
| capabilities | 8 | ownership records | 8 |
| skills | 8 | availability records | 6 |
| capability-skill links | 9 | data sources | 3 |
| capability evidence | 30 | ingestion runs | 4 |
| initiatives | 5 | evidence signals | 40 |
| projects | 8 | | |
| repositories | 10 | **total** | **223** |

The dataset supports narrative scenarios: payment-modernization dependency risk,
Azure-migration capability shortage, fraud-detection ownership concentration on a
single engineer, and incident-driven capacity reduction.

Run it with `python -m app.db.enterprise_seed` (the Phase 2 `python -m
app.db.seed` demo data remains usable and independent).

---

## 7. Migration and backfill strategy

One additive revision: `p3_enterprise_foundation` (down-revision
`a1b2c3d4e5f6`), exactly one head. It creates the `ent_*` tables (indexes on
tenant-qualified access paths, foreign keys with explicit `ON DELETE` behavior,
`CHECK` constraints, and tenant-scoped composite unique constraints), adds the
nullable `tenant_id` columns to the three Phase 2 tables, and backfills them to
`legacy-default`. Validated on disposable SQLite:

- `alembic upgrade head` → OK, `alembic check` → no new operations;
- `alembic downgrade a1b2c3d4e5f6` → OK (Phase 2 tables preserved);
- re-`upgrade head` → OK.

DDL is PostgreSQL-compatible: offline Alembic SQL compilation against a
PostgreSQL dialect URL succeeds (no live server required). **no** production
`create_all`, **no** destructive rewrite of Phase 2 tables. Live PostgreSQL
execution was **not** performed in this pass and remains deferred.

---

## 8. API and contracts (v3)

Additive `/api/v3` routes (`app/api/v3/`) avoid any change to v2 contracts.
Tenant context is supplied by the `X-SignalForge-Tenant-ID` header — a **local
data-scoping mechanism, explicitly not authentication**. Missing/invalid context
is rejected (HTTP 400). Reads return 404 for tenant-qualified absence without
revealing cross-tenant existence; conflicts return 409; validation/cross-tenant
associations return 422. Collections are paginated with stable ordering and
bounded page sizes. Case-oriented write endpoints only (register data source,
start/complete ingestion run, append evidence) — no blanket CRUD. OpenAPI
generation includes all v3 routes and retains all v2 routes.

---

## 9. Known limitations

- Tenant isolation is a data boundary, not enforced identity/authorization.
- Header-based tenant selection is for local development only.
- SQLite for local/dev/test; offline PostgreSQL DDL compilation passed; live
  PostgreSQL execution is deferred.
- Polymorphic relationship endpoints (`Dependency`/`Ownership`/`Availability`
  and evidence `subject_id`) store opaque typed ids without FK validation of the
  target row. Cross-tenant *resolution* is rejected for FK-backed associations;
  an opaque foreign-tenant id string can still be stored as a dangling pointer
  under the caller's tenant and cannot be used to read the other tenant's row.
- No connectors, queues, delivery graph, prediction, or metrics emission.
- Evidence payload bound is enforced at the API layer using a conservative
  non-canonical JSON character-length check (≤ 16 384) that is always at least
  as strict as the canonical UTF-8 byte length used for hashing.

## 10. Deferred security controls (Phase 3 Prompt 7)

Authentication, authorization/RBAC, enterprise identity (Entra ID), PostgreSQL
row-level security, and secret-store integration are deliberately deferred. No
SOC 2 / ISO 27001 / GDPR / encryption-key-management claims are made.

Implemented foundational controls: tenant-qualified access with cross-tenant
negative tests, no plaintext connector secrets, no credentials in logs, bounded
input lengths, safe enum parsing, bounded evidence payloads (≤ 16 KB at the API
layer; hashing uses the canonical snapshot utility), permission-classification
enum, sanitized ingestion failure summaries, and safe canonical hashing.

---

## 11. Prompt 2 connector-readiness contract

Prompt 2 (connectors) will populate this foundation without schema churn:

1. A connector authenticates using a secret resolved from
   `DataSource.credential_reference` (secret store deferred to Prompt 7).
2. It opens an `IngestionRun` (`start_run`), streams provider records, and
   normalizes each into an `EvidenceSignal` with a canonical payload + hash.
3. It calls the idempotent `append_evidence` path — duplicates are deduplicated,
   never overwritten — then closes the run (`complete_run`) with counts and a
   sanitized error summary.
4. Downstream milestones (delivery graph, prediction) read append-only evidence
   by subject/source; they never mutate it.

Future (not yet implemented) metric points: ingestion count, deduplication
count, rejected cross-tenant access, and evidence freshness.
