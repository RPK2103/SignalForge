# Phase 3 Prompt 10 — Microsoft POC and Startup Pitch Readiness

**Status:** Implemented (documentation + executive briefing packaging)  
**Branch intent:** `feat/phase-3-microsoft-poc-startup-pitch-readiness`  
**Alembic head (unchanged):** `p3_observability_ai_quality`  
**Prerequisite:** Prompt 9 merge `1913d71aa00c15d8bf7c415efdb3f50a1b4bb697`

This package packages SignalForge for enterprise evaluation and startup
communication. It does **not** add Phase 4 product engines.

## Claim discipline

Every artifact in this package must distinguish:

| Label | Meaning |
|---|---|
| **IMPLEMENTED** | Present in code, APIs, tests, or validated workflows |
| **POC CONFIGURATION** | Implemented capability requiring customer-environment setup |
| **INTEGRATION REQUIRED** | Customer/product work still required before the capability is usable (e.g. interactive Entra SPA) |
| **PROPOSED** | Plausible Microsoft/customer integration path, not shipped |
| **DEFERRED** | Explicitly out of Prompt 10 / later roadmap |
| **NOT VALIDATED** | Hypothesis or illustrative assumption only |

Prohibited without repository proof: Microsoft endorsement/partnership/
certification/Marketplace availability; production or paid customers;
invented ROI, traction, TAM, testimonials, model accuracy, or causal
scenario outcomes.

NovaBank is **fictional / synthetic / production-ineligible**.

## Documentation index

### POC evaluation

| Document | Purpose |
|---|---|
| [Microsoft enterprise POC blueprint](../docs/poc/microsoft-enterprise-poc-blueprint.md) | 4–6 week POC lifecycle, stakeholders, entry/exit |
| [POC success framework](../docs/poc/poc-success-framework.md) | Measurable evaluation metrics (no fabricated values) |
| [Security & governance questionnaire](../docs/poc/security-governance-questionnaire.md) | Enterprise security review package |
| [Data onboarding plan](../docs/poc/data-onboarding-plan.md) | Source readiness and identity mapping |
| [NovaBank executive demo runbook](../docs/poc/novabank-executive-demo-runbook.md) | 3 / 7 / 15 minute demos |

### Pitch and buyer package

| Document | Purpose |
|---|---|
| [Executive one-pager](../docs/pitch/executive-one-pager.md) | Concise product narrative |
| [Buyer personas](../docs/pitch/buyer-personas.md) | Economic/operational buyers, users, reviewers |
| [ROI hypothesis model](../docs/pitch/roi-hypothesis-model.md) | Formulas and illustrative assumptions only |
| [Competitive positioning](../docs/pitch/competitive-positioning.md) | Category differentiation without absolutes |
| [Startup pitch outline](../docs/pitch/startup-pitch-outline.md) | 12-slide Markdown source of truth |
| [Objections and responses](../docs/pitch/objections-and-responses.md) | Honest objection handling |

### Portfolio and evidence

| Document | Purpose |
|---|---|
| [SignalForge case study](../docs/portfolio/signalforge-case-study.md) | Portfolio-ready engineering case study |
| [Production-readiness evidence index](../docs/evidence/production-readiness-evidence-index.md) | Claim → repository proof mapping |

### Product entry

| Document | Purpose |
|---|---|
| [README](../README.md) | Primary product entry point |
| This file | Prompt 10 architecture boundary and index |

## Capability inventory (evidence-backed summary)

| Capability | Status | Evidence |
|---|---|---|
| Engineer/team capability analysis | IMPLEMENTED / Demo-ready | v2 readiness APIs, UI |
| Initiative/project readiness | IMPLEMENTED / Demo-ready | assessments + NovaBank v3 |
| Delivery-risk analysis | IMPLEMENTED / Demo-ready | key-person risk, graph findings |
| Capability-gap analysis | IMPLEMENTED | skill_gap / coverage services |
| Project fit | IMPLEMENTED | fit recommender + UI |
| Connector ingestion | IMPLEMENTED (GitHub) / DEFERRED (Jira/ADO HTTP) | `backend/app/connectors/` |
| Evidence assembly | IMPLEMENTED | EvidenceSignal + CoS packages |
| Delivery Graph | IMPLEMENTED / Demo-ready | `/api/v3/delivery-graph/*` + CLI |
| Deterministic features | IMPLEMENTED | `delivery_features_v1`, policy_v1 |
| Prediction + fallback | IMPLEMENTED | scorecard fallback; NovaBank unpromoted |
| Counterfactual scenarios | IMPLEMENTED / Demo-ready | 8 kinds; read API + CLI |
| AI Chief of Staff | IMPLEMENTED / Demo-ready | read API; CLI generate |
| Review workflow | IMPLEMENTED | assessment + CoS reviews |
| Enterprise security | IMPLEMENTED foundation / POC CONFIG for Entra login | JWT/RBAC/RLS/audit |
| Tenant isolation | IMPLEMENTED (app + PG RLS) | SQLite ≠ RLS proof |
| Audit logs | IMPLEMENTED | `ent_security_audit_events` |
| Observability | IMPLEMENTED local / POC CONFIG for Azure Monitor | `/observability` |
| AI-quality controls | IMPLEMENTED | offline gate in CI |
| NovaBank demo tenant | Demo-ready | Prompt 9 generator + CI |
| Executive briefing UI | IMPLEMENTED (Prompt 10) | `/briefing` (authenticated, generic) |
| Microsoft Marketplace / Teams / Power BI / Copilot Studio | DEFERRED | not implemented |
| Billing / CRM / public anonymous demo | DEFERRED / prohibited | not implemented |

## Product changes in Prompt 10

- Documentation package listed above.
- Generic authenticated **Executive briefing** page (`/briefing`) consuming
  existing `/api/v3` read APIs (no new backend endpoint; no migration).
- Shared primary navigation across readiness, briefing, observability.
- Documentation contract tests and extended Playwright coverage.

## Explicit non-goals

- New prediction algorithms, connectors, or domain engines.
- Binary PowerPoint as source of truth.
- Public demo seed/reset endpoints.
- Authentication bypass or weakened RLS/audit.
- Fabricated traction, ROI, or Microsoft endorsement.

## Microsoft-aligned reference architecture (summary)

See the POC blueprint for the full current-vs-proposed table. Short form:

| Area | Current | Microsoft POC option | Status |
|---|---|---|---|
| App hosting | Local / Render guidance | Azure Container Apps or App Service | PROPOSED |
| Data | SQLite local; PostgreSQL for RLS | Azure Database for PostgreSQL | POC CONFIGURATION |
| Identity | JWT (`entra_oidc` verifier exists; no MSAL SPA) | Microsoft Entra ID interactive login | INTEGRATION REQUIRED |
| Secrets | Env / local | Azure Key Vault | PROPOSED |
| Observability | In-process + optional OTel construct | Azure Monitor / App Insights | PROPOSED |
| AI | Deterministic fallback + provider abstraction | Azure OpenAI when approved | CONFIGURATION |
| Collaboration analytics | SignalForge UI | Teams / Power BI / Copilot | DEFERRED |

**Microsoft has not endorsed this project.**

## Validation expectation

Independent audit must re-run Prompt 10 acceptance gates. This package remains
unstaged until that audit completes. Do not treat packaging as production
certification.
