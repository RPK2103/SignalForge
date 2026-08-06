# Phase 3 Prompt 9 — Realistic Enterprise Demo Tenant

**Status: IMPLEMENTED** (subject to independent audit)

## Disclaimer

NovaBank is a fictional composite organization created solely for controlled
product demonstration and testing. It is not affiliated with any real bank or
company. All engineers, evidence, outcomes and briefs are synthetic and
**production-ineligible**.

## Purpose

Provide a deterministic, enterprise-scale NovaBank dataset that exercises the
complete SignalForge product coherently: org structure, portfolio, execution
history, ownership/dependencies, graph, scenarios, Chief of Staff, security
audit and observability.

## What this is not (Prompt 10 / deferred)

| Claim | Status |
|---|---|
| Microsoft pitch package / endorsement | DEFERRED (Prompt 10) |
| Buyer presentation / ROI / pricing | DEFERRED (Prompt 10) |
| Real customer validation | NOT CLAIMED |
| Calibrated real-world probability | NOT CLAIMED |
| Production SLO attainment | UNVALIDATED |
| Employee performance intelligence | PROHIBITED |

## Dataset versions

| Field | Value |
|---|---|
| Dataset name | `novabank-enterprise-demo` |
| Dataset version | `novabank-enterprise-demo-v2` |
| Generator version | `novabank-generator-v1` |
| Schema compat | `p3_observability_ai_quality` (no new migration) |
| Temporal anchor (`AS_OF_AT`) | `2026-07-31T18:00:00Z` |
| Tenant ID | `novabank` (canonical; no competing tenant) |

## Exact inventory (target = realized on fresh DB)

| Entity | Count |
|---|---:|
| Organizations | 1 |
| Business units | 5 |
| Departments | 10 |
| Teams | 10 |
| Engineers | 48 |
| Capabilities | 18 |
| Skills | 16 |
| Initiatives | 14 |
| Projects | 24 |
| Repositories | 32 |
| Sprints | 30 |
| Work items | 480 |
| Pull requests | 220 |
| Deployments | 75 |
| Incidents | 32 |
| Dependencies | 58 |
| Ownership | 120 |
| Availability | 18 |
| Story scenarios | 8 |

## Organization model

Business units: Consumer Banking (`retail-banking`), Enterprise Platforms and
Cloud, Payments and Money Movement, Risk/Fraud/Compliance Technology, Data and
Customer Intelligence.

Ten engineering teams with asymmetric capacity: Cloud Foundation is
overcommitted; Fraud Decisioning has concentrated ownership on selected repos;
Customer Copilot carries freshness and AI-governance dependencies.

## Eight evidence-backed stories

1. Fraud-detection launch risk  
2. Payment-modernization dependency slip  
3. Azure-migration capability shortage  
4. Customer-copilot readiness  
5. Critical engineer role transition (continuity risk only — no blame)  
6. Incident-driven roadmap delay  
7. Concentrated repository ownership  
8. Cross-team platform bottleneck  

Findings must be derived from seeded evidence via existing services — not
hardcoded product conclusions.

## Determinism

- IDs via `build_entity_id` (SHA-256), never `uuid4` / process `hash()`
- Fixed UTC anchor; no `datetime.now()` in generation
- Manifest category hashes over sorted IDs; complete hash excludes own hash,
  created/reused counts and machine metadata
- Fresh Database A/B must produce identical manifest hashes

## Idempotency and transactions

- First seed creates canonical rows + audited `demo.dataset.seeded`
- Second identical seed creates zero canonical duplicates, same manifest hash
- Injected generation / audit failure rolls back; no false success telemetry
- Concurrent duplicate prevention relies on DB uniqueness (SQLite concurrency
  limited; PostgreSQL validated remotely via RLS suites)

## Compatibility with Prompt 1–8 seeds

Prompt 9 **extends** the existing NovaBank tenant. Foundational natural keys
are preserved. Missing Prompt 9 records are added. Existing immutable rows are
not deleted to reach counts. Incompatible stored manifests raise rather than
silently overwrite.

## Intelligence materialization

CLI `python -m app.demo novabank materialize` rebuilds the Delivery Graph,
executes story scenarios, and generates Chief of Staff briefs with
`DETERMINISTIC_FALLBACK`. Graph rebuild is mandatory: projection failure aborts
materialization, rolls back partial derived state, clears pending success
telemetry, and exits non-zero. Mandatory tests never call external LLMs or
connectors. Estimate wording: uncalibrated score; probability unavailable;
candidate not promoted; synthetic demonstration; decision-support only.

### Deterministic graph temporal semantics

- Canonical anchor: `AS_OF_AT = 2026-07-31T18:00:00Z`
- Closed intervals require `valid_from < valid_to`; open intervals use `valid_to IS NULL`
- Derived `team_owns_project_contributes_to_initiative` edges include the project
  id in the natural key so multi-project team/initiative fans do not collide
- Temporal edge closure refuses inverted historical snapshots (`valid_to <= valid_from`)
- NovaBank portfolio `created_at` / `planned_start` are seeded from
  `FOUNDATIONAL_BASE` / `dt_from_base` (no wall-clock generation timestamps)
- Canonical full-scale rebuild succeeds on SQLite; a second rebuild is idempotent
- Story 7 (concentrated repository ownership) produces a grounded
  deterministic-fallback Chief-of-Staff brief with citation binding

## Security and privacy

- Permission `demo.tenant.manage` (TENANT_ADMIN only; fail-closed audit)
- Explicit `internal_system_context`; `security=None` rejected
- No demo auth bypass, no public seed API, no destructive reset
- No private emails, sensitive attributes, employee ranking or blame
- Telemetry fail-open; required audit fail-closed
- Manifest stored as `EvidenceSignal` (no new migration / RLS table)

## CLI

```bash
python -m app.demo novabank seed --database-url ... --json
python -m app.demo novabank materialize --json
python -m app.demo novabank validate
python -m app.demo novabank manifest
python -m app.demo novabank report
```

## Migration result

**No migration required.** Alembic head remains `p3_observability_ai_quality`.

## Known limitations

- Synthetic only; not production-eligible
- Uncalibrated scores are not probabilities
- Scenario outputs are not causal claims
- Local PostgreSQL RLS requires `POSTGRES_TEST_URL`; remote CI enforces full
  canonical seed, materialization, and graph rebuild on PostgreSQL 16 with a
  non-superuser / `NOBYPASSRLS` application role
- Prompt 10 buyer/ROI materials are out of scope
- Production-scale performance and production SLO attainment are not claimed
