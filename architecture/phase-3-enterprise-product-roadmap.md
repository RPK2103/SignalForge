# SignalForge — Phase 3 Enterprise Product Roadmap

_Phase 3 turns the Phase 2 deterministic decision-support prototype into a
multi-tenant, connector-fed, observable enterprise product. Numbering restarts at
**Prompt 1** for Phase 3 (do not use global Prompt 9–18 numbering)._

## Ordering Principles (enforced)

1. Foundation before connectors.
2. Connectors before the delivery graph.
3. Evidence (graph) before prediction.
4. Prediction before continuous scenarios.
5. Grounded data before the AI Chief of Staff.
6. Security and scale before enterprise claims.
7. Observability before production-grade AI-quality claims.
8. Realistic tenant before the final pitch.

Each prompt below is scoped, sequential, and gated by its predecessor's
acceptance criteria.

---

## Phase 3 — Prompt 1
### Enterprise Domain, Multi-Tenant Data Foundation and Realistic Demo Model

- **Product goal:** Replace toy identities with a multi-tenant enterprise domain
  and a realistic synthetic demo tenant (NovaBank).
- **Business value:** Credible demos; the foundation every later capability
  depends on.
- **Architecture scope:** Tenant model, org hierarchy (business unit → dept →
  team), engineer/capability/initiative entities, provenance fields, seeded
  synthetic generator.
- **Data model:** `tenant`, `org_unit`, `team`, `engineer`, `capability`,
  `initiative`, `repository`, `work_item`, plus provenance columns
  (`source`, `source_record_id`, `event_time`, `ingestion_time`,
  `schema_version`, `processing_version`, `confidence`, `freshness`,
  `permission_classification`).
- **APIs:** Tenant-scoped CRUD/read for org, teams, engineers, initiatives.
- **Migrations:** New multi-tenant tables + `tenant_id` on existing snapshots;
  backfill demo tenant.
- **Tests:** Tenant isolation at the query layer; generator determinism; schema
  migration up/down.
- **Security:** Row-level tenant scoping in the persistence layer.
- **Observability:** Record counts and generation metrics per tenant.
- **Acceptance criteria:** NovaBank tenant seeds deterministically; all existing
  v2 flows work tenant-scoped; single Alembic head; check clean.
- **Dependencies:** Phase 2 complete.
- **Non-goals:** Real connectors, auth, prediction.
- **Suggested branch:** `feat/phase-3-domain-foundation`
- **Suggested commit subject:** `feat(domain): multi-tenant enterprise domain and NovaBank demo tenant`

---

## Phase 3 — Prompt 2
### Connector SDK and Ingestion Pipeline

- **Product goal:** A pluggable connector SDK + ingestion pipeline for consented
  and public sources.
- **Business value:** Real signals instead of synthetic-only data.
- **Architecture scope:** Connector interface, scheduler, normalization to the
  domain model, idempotent upserts keyed by `(source, source_record_id)`.
- **Data model:** `connector_config`, `ingestion_run`, `raw_event`, mapping
  tables; provenance on every row.
- **APIs:** Register/configure connectors; trigger/inspect ingestion runs.
- **Migrations:** Connector + ingestion tables.
- **Tests:** Connector contract tests with recorded fixtures (no live calls);
  idempotency; provenance completeness.
- **Security:** Per-tenant scoped credentials via secret store; least-privilege
  scopes; redaction in logs.
- **Observability:** Ingestion lag, run success/failure, record freshness.
- **Acceptance criteria:** A GitHub-org connector ingests fixture data into the
  domain model idempotently with full provenance.
- **Dependencies:** Prompt 1.
- **Non-goals:** Prediction, graph analytics.
- **Suggested branch:** `feat/phase-3-connector-sdk`
- **Suggested commit subject:** `feat(ingest): connector SDK and idempotent ingestion pipeline`

---

## Phase 3 — Prompt 3
### Delivery Graph

- **Product goal:** A queryable delivery graph linking teams, capabilities,
  initiatives, dependencies, work items and incidents.
- **Business value:** Turns raw signals into structured, explainable evidence.
- **Architecture scope:** Graph model over relational storage; dependency and
  ownership edges; capability coverage derived from evidence.
- **Data model:** `graph_node`, `graph_edge` (typed), materialized coverage views.
- **APIs:** Graph queries (dependencies, ownership concentration, coverage).
- **Migrations:** Graph tables + indices.
- **Tests:** Graph construction from ingested fixtures; coverage correctness;
  cycle detection.
- **Security:** Tenant-scoped graph queries.
- **Observability:** Graph size, edge freshness, coverage completeness.
- **Acceptance criteria:** Readiness inputs are derived from the graph (not mock
  data) for the demo tenant.
- **Dependencies:** Prompt 2.
- **Non-goals:** ML prediction.
- **Suggested branch:** `feat/phase-3-delivery-graph`
- **Suggested commit subject:** `feat(graph): delivery graph over ingested evidence`

---

## Phase 3 — Prompt 4
### Delivery Prediction Engine

- **Product goal:** Calibrated delivery-risk/likelihood prediction from
  historical delivery data.
- **Business value:** Moves from deterministic policy scores to evidence-based,
  calibrated prediction.
- **Architecture scope:** Feature extraction from the graph, model training +
  versioning, calibration, backtesting harness.
- **Data model:** `feature_snapshot`, `model_version`, `prediction`,
  `calibration_metric`.
- **APIs:** Predict for an initiative/team; return calibrated probability +
  intervals + feature attributions.
- **Migrations:** Prediction/model tables.
- **Tests:** Backtesting on held-out history; calibration (reliability) tests;
  attribution stability.
- **Security:** No leakage across tenants in features/models.
- **Observability:** Prediction drift, calibration error, feature freshness.
- **Acceptance criteria:** Backtested, calibrated predictions with documented
  metrics; deterministic policy retained as fallback/baseline.
- **Dependencies:** Prompt 3.
- **Non-goals:** Continuous/streaming scenarios.
- **Suggested branch:** `feat/phase-3-prediction-engine`
- **Suggested commit subject:** `feat(predict): calibrated delivery prediction engine with backtesting`

---

## Phase 3 — Prompt 5
### Continuous Scenario Intelligence

- **Product goal:** Continuously updated simulations and what-if scenarios as new
  signals arrive.
- **Business value:** Always-current delivery-risk visibility, not point-in-time.
- **Architecture scope:** Incremental recompute on ingestion events; scenario
  templates; change notifications.
- **Data model:** `scenario`, `scenario_result`, `scenario_subscription`.
- **APIs:** Define/subscribe scenarios; stream/poll scenario deltas.
- **Migrations:** Scenario tables.
- **Tests:** Incremental recompute correctness vs full recompute; delta accuracy.
- **Security:** Tenant-scoped scenario execution.
- **Observability:** Recompute latency, scenario freshness, delta rate.
- **Acceptance criteria:** New ingested data updates affected scenarios and
  predictions automatically for the demo tenant.
- **Dependencies:** Prompt 4.
- **Non-goals:** AI narrative layer.
- **Suggested branch:** `feat/phase-3-continuous-scenarios`
- **Suggested commit subject:** `feat(scenarios): continuous scenario intelligence on ingestion events`

---

## Phase 3 — Prompt 6
### AI Chief of Staff for Engineering

- **Product goal:** A grounded conversational/briefing layer over predictions,
  scenarios and the graph.
- **Business value:** Leadership can ask delivery questions and get grounded,
  cited answers and proactive briefs.
- **Architecture scope:** Retrieval over the graph/evidence, strict grounding +
  citation, deterministic fallback (extending Phase 2's brief boundary).
- **Data model:** `conversation`, `message`, `grounding_citation`.
- **APIs:** Ask/answer with citations; scheduled briefs.
- **Migrations:** Conversation tables.
- **Tests:** Grounding/citation validation; fallback on grounding failure;
  no-hallucination checks against fixtures.
- **Security:** Tenant-scoped retrieval; no cross-tenant context; no
  prompt/evidence logging.
- **Observability:** Fallback rate, grounding-failure rate, answer latency.
- **Acceptance criteria:** Every AI answer is grounded + cited or deterministically
  refused/fallback; provenance recorded.
- **Dependencies:** Prompt 5 (grounded data first).
- **Non-goals:** Enterprise auth/scale (next).
- **Suggested branch:** `feat/phase-3-ai-chief-of-staff`
- **Suggested commit subject:** `feat(ai): grounded AI chief of staff with citations and fallback`

---

## Phase 3 — Prompt 7
### Enterprise Security and Scale

- **Product goal:** Authentication, RBAC, tenant isolation and horizontal scale.
- **Business value:** Required before any enterprise/production claim.
- **Architecture scope:** AuthN (incl. Entra ID/OIDC verifier), RBAC, hardened
  tenant isolation, connection pooling. Background workers and distributed rate
  limiting remain **DEFERRED** (not delivered as runtime scale features).
- **Data model:** `user`, `role`, `permission`, `membership`, audit logs.
- **APIs:** Bearer JWT verification + RBAC on protected routes; admin/role
  management surfaces as implemented. Scoped API keys = **DEFERRED** (not shipped).
  Interactive Entra/MSAL SPA login = **INTEGRATION REQUIRED** (verifier exists;
  browser login not shipped).
- **Migrations:** Auth/RBAC tables; PostgreSQL FORCE RLS path.
- **Tests:** AuthZ matrix; cross-tenant isolation (app + PG RLS in CI). Load/scale
  tests = **NOT VALIDATED** / **DEFERRED**.
- **Security:** Threat-model foundation; env-based secrets; audit logging.
  Secret-vault integration remains recommended / **PROPOSED**, not in-app.
- **Observability:** Auth failures, authz denials, tenant-scoped metrics (with
  Prompt 8 surfaces).
- **Acceptance criteria (original intent vs delivery):** Enforced RBAC + tenant
  isolation with tests = delivered foundation. “Entra ID login working” means
  production `entra_oidc` JWT verification path — interactive browser login is
  **INTEGRATION REQUIRED**. Documented scale limits without claiming distributed
  workers/rate limits.
- **Dependencies:** Prompt 6.
- **Non-goals:** New product features.
- **Suggested branch:** `feat/phase-3-security-scale`
- **Suggested commit subject:** `feat(security): authentication, RBAC, tenant isolation and scale`

**Delivery status (Prompt 10):** Security foundation (JWT modes, RBAC, audit,
PostgreSQL FORCE RLS in CI) is **IMPLEMENTED**. Interactive Entra/MSAL SPA,
background workers, API rate limiting, and scoped API keys are **not** fully
delivered — label as **INTEGRATION REQUIRED** / **DEFERRED** / **NOT VALIDATED**
as above. See
[`phase-3-enterprise-security-scale.md`](phase-3-enterprise-security-scale.md).

---

## Phase 3 — Prompt 8
### Observability and AI Quality

- **Product goal:** Production observability + AI-quality monitoring.
- **Business value:** Required before production-grade AI-quality claims.
- **Architecture scope:** OpenTelemetry traces/metrics/logs, SLOs, alerting,
  AI-quality evaluation harness.
- **Data model:** `slo`, `alert`, `ai_eval_run`, quality metrics.
- **APIs:** Metrics/health/SLO endpoints; eval triggers.
- **Migrations:** Eval/SLO tables.
- **Tests:** Instrumentation coverage; SLO computation; eval regression.
- **Security:** No sensitive data in telemetry.
- **Observability:** API latency, error rates, connector lag, data freshness,
  provider latency, fallback rate, grounding-failure rate, prediction drift,
  calibration; SLOs + alerts.
- **Acceptance criteria:** Dashboards + alerts for the above; AI-quality eval
  gates in CI.
- **Dependencies:** Prompt 7.
- **Non-goals:** Demo tenant polish.
- **Suggested branch:** `feat/phase-3-observability-ai-quality`
- **Suggested commit subject:** `feat(observability): OpenTelemetry, SLOs and AI-quality monitoring`

---

## Phase 3 — Prompt 9
### Realistic Enterprise Demo Tenant

- **Product goal:** A polished, end-to-end realistic demo tenant exercising all
  capabilities.
- **Business value:** A compelling, trustworthy demo for POC/pitch.
- **Architecture scope:** Rich NovaBank dataset across connectors (fixture-fed),
  curated initiatives, scenarios and briefs.
- **Data model:** Reuses Prompts 1–8; adds curated demo fixtures.
- **APIs:** Read APIs reused; demo seed/materialize/reset are **CLI only**.
  No public HTTP demo mutation/reset API (intentionally withheld).
- **Migrations:** None beyond fixtures.
- **Tests:** Demo/E2E coverage and CLI idempotency for seed/materialize paths.
- **Security:** Demo tenant isolated; synthetic-only / fictional data;
  production-ineligible.
- **Observability:** Demo dashboards populated via existing surfaces.
- **Acceptance criteria:** A scripted, reproducible end-to-end demo runs green
  via CLI + authenticated UI — not via a public reset API.
- **Dependencies:** Prompt 8.
- **Non-goals:** Pitch materials (next).
- **Suggested branch:** `feat/phase-3-realistic-demo-tenant`
- **Suggested commit subject:** `feat(demo): realistic NovaBank enterprise demo tenant`

**Delivery status (Prompt 10):** NovaBank generator, materialize CLI, and demo
CI are **IMPLEMENTED** (synthetic tenant). Demo configuration/reset **HTTP**
APIs are **not** delivered — operators use CLI only. Do not read earlier
“demo configuration/reset endpoints” wording as a shipped public mutation API.

---

## Phase 3 — Prompt 10
### Microsoft POC and Startup Pitch Readiness

- **Product goal:** Package a credible Microsoft POC and startup pitch backed by
  repository evidence — without fabricating traction or endorsement.
- **Business value:** Convert the implemented product into an evaluable enterprise
  POC motion and honest startup narrative.
- **Architecture scope:** Documentation package under `docs/poc`, `docs/pitch`,
  `docs/portfolio`, `docs/evidence`; Microsoft-aligned **proposed** reference
  architecture; generic authenticated executive briefing UI (`/briefing`) over
  existing `/api/v3` read APIs.
- **Data model:** **No new tables.** Alembic head remains
  `p3_observability_ai_quality`.
- **APIs:** **No new endpoints** unless existing read APIs cannot support the
  briefing experience (Prompt 10 uses existing routes).
- **Migrations:** None (default).
- **Tests:** Documentation contract tests; executive briefing unit + Playwright
  coverage; full regression suites.
- **Security:** Questionnaire + evidence index; no auth bypass; no public demo
  mutation API.
- **Observability:** Reuses Prompt 8 surfaces; no fake pilot dashboards.
- **Acceptance criteria:** POC blueprint with entry/exit and multi-metric success
  framework; ROI labelled hypothesis; NovaBank labelled fictional; no Microsoft
  endorsement claim; independent audit still required before commit.
- **Dependencies:** Prompt 9.
- **Non-goals:** Claiming Microsoft endorsement; inventing customers/ROI;
  Marketplace publishing; Phase 4 engines; binary PPTX as source of truth.
- **Suggested branch:** `feat/phase-3-microsoft-poc-startup-pitch-readiness`
- **Suggested commit subject:** `feat(poc): Microsoft POC packaging and startup pitch readiness`

**Delivery note:** Prompt 10 is implemented as documentation + briefing packaging
on the feature branch above. See
[`architecture/phase-3-microsoft-poc-startup-pitch-readiness.md`](phase-3-microsoft-poc-startup-pitch-readiness.md).

---

## Non-Goals for All of Phase 3 (until evidenced)

- No claim of Microsoft endorsement.
- No funding-readiness claim without pilots, interviews, backtesting, ROI and
  production security evidence.
- No claim of real customers or compliance certification without artifacts.
