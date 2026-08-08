# Data Onboarding Plan

## Principles

- Use **existing connector implementations** as source of truth.
- Unsupported sources are **PROPOSED CONNECTOR**, **MANUAL IMPORT**, or
  **DEFERRED** — never documented as implemented.
- Identity mapping and tenant boundaries are approved before backfill.
- NovaBank is synthetic and is not a customer onboarding path.

## Lifecycle

1. Source selection
2. Approved historical window
3. Source ownership assignment
4. Identity mapping (people, teams)
5. Tenant mapping
6. Repository mapping
7. Initiative / project / team mapping
8. Capability taxonomy alignment
9. Evidence normalization
10. Backfill
11. Incremental sync
12. Data-quality checks
13. Reconciliation
14. Deletion handling
15. Retention
16. Rollback plan
17. Sign-off

## Source-readiness matrix

| Source | Required fields | Optional fields | Authentication | Expected volume | Validation | Status |
|---|---|---|---|---|---|---|
| GitHub (REST polling) | org/repos, PR/issue/release identifiers, timestamps, actors | reviews detail depth | token or public unauthenticated mode | customer-specific | idempotent receipts, checkpoints, dead letters | **IMPLEMENTED** |
| GitHub webhooks / OAuth Apps | — | — | — | — | — | **DEFERRED** |
| Jira | issue key, project, status, assignee, updated | sprint links | — | — | — | **PROPOSED CONNECTOR** (descriptor only) |
| Azure DevOps | work item id, project, state, changed date | PR links | — | — | — | **PROPOSED CONNECTOR** (descriptor only) |
| Operator-assisted worksheet for missing systems | stable external ids + event_time | richer provenance | human-approved operator process (no shipped CSV/upload product surface) | bounded batches | checksum + reconciliation worksheet | **MANUAL IMPORT** (operational proposal — not an implemented product import API) |
| HR / performance systems | — | — | — | — | — | **DEFERRED** (out of product intent; not employee surveillance) |

## Identity mapping

| Mapping | Approach |
|---|---|
| People | Map source login/email → engineer_profile within tenant; unresolved identities tracked as a data-quality metric |
| Teams | Map source teams/projects → tenant teams; do not invent org structure |
| Repositories | Map provider + external_reference → repository rows |
| Initiatives/projects | Customer-owned mapping worksheet; SignalForge stores tenant-scoped entities |
| Capabilities | Align customer taxonomy to enterprise capability catalog; gaps documented |

## Evidence normalization

Normalized events become `EvidenceSignal` rows with provenance
(`source`, `source_record_id`, `event_time`, `observed_at`, hashing). Duplicates
remain auditable via receipts after content dedup.

## Backfill and incremental sync

- Backfill uses the approved historical window only.
- Incremental sync relies on connector checkpoints (GitHub IMPLEMENTED).
- No public HTTP sync-trigger endpoint; sync remains operator/CLI controlled
  unless a future authenticated operator API is approved.

## Quality checks and reconciliation

Use the POC success framework metrics: coverage, freshness, completeness,
duplicates, unresolved identities, missing ownership/dependency links.

Reconciliation workshops compare graph edges and initiative metadata against
engineering-manager ground truth.

## Deletion, retention, rollback, sign-off

| Topic | Guidance |
|---|---|
| Deletion | Customer-defined; soft-archive fields exist; hard-delete requires explicit approval |
| Retention | Customer policy; audit retention may exceed operational data retention |
| Rollback | Prefer forward-fix + re-ingest; retain manifests/receipts for audit |
| Sign-off | Data owner + security reviewer + SignalForge implementation owner |

## Explicit exclusions

- Do not onboard real employee performance ratings for ranking.
- Do not treat synthetic demo rows as production data.
- Do not claim Jira/ADO HTTP connectors are implemented.
