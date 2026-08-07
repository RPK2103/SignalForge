# SignalForge Portfolio Case Study

Portfolio engineering case study for SignalForge Phase 2–3. Uses **verified
repository measurements only**. No production-customer adoption is claimed.

## 1. Problem

Engineering leaders lack evidence-backed answers to delivery readiness questions
across capability, dependency, ownership, and availability risk.

## 2. Target users

CTO/VP Engineering, engineering operations/program leaders, directors/managers,
platform and architecture leaders; security and data-governance reviewers.

## 3. Why it matters

Late discovery of delivery-system risk is expensive. Fragmented tools answer
activity and status, not grounded readiness.

## 4. Product thesis

Deterministic intelligence first; AI explains with citations; humans review;
tenant isolation is mandatory for enterprise trust.

## 5. Architecture

Monolith FastAPI + Next.js; shared-schema multi-tenancy; relational Delivery
Graph (no graph DB); connector SDK with GitHub polling implemented; v2 readiness
APIs + v3 enterprise intelligence APIs.

## 6. AI and deterministic intelligence

Readiness/confidence from versioned policy. Leadership briefs and Chief of Staff
support Azure OpenAI providers with deterministic fallback and grounding
validation. Mandatory tests do not call live LLMs.

## 7. Delivery Graph

Tenant-scoped projection/analysis with findings (concentration, dependency,
availability blast radius, cycles, etc.) and evidence references.

## 8. Prediction honesty

Feature snapshots + logistic/Platt path + uncalibrated scorecard fallback.
NovaBank candidate remains unpromoted / production-ineligible. Uncalibrated
scores are not probabilities.

## 9. Scenario intelligence

Immutable definitions/versions; overlay-only execution; watches; eight NovaBank
story scenarios after materialize.

## 10. AI Chief of Staff

Bounded intents; evidence packages; claims/citations; append-only reviews;
quality summary.

## 11. Security and tenant isolation

Default-deny JWT; RBAC matrix; audit; PostgreSQL FORCE RLS with non-superuser
app role. Local development auth is not production auth.

## 12. Observability and AI quality

Provider boundary, HTTP semantics, offline AI-quality release gate, SLOs/alerts
(internal), `/observability` UI.

## 13. NovaBank demo

Fictional tenant `novabank-enterprise-demo-v2`, as_of `2026-07-31T18:00:00Z`.
Canonical inventory includes 14 initiatives, 24 projects, 48 engineers,
32 repos, 8 scenarios; materialize produces graph findings and 8 CoS briefs.
Prompt 10 adds authenticated `/briefing` navigation for the executive narrative.

## 14. Testing and CI

Verified at Prompt 9 post-merge baseline (re-validate on Prompt 10 audit):

- Backend: 991 passed, 24 environment-gated skips (typical local)  
- Frontend unit: 34 passed (Prompt 9); Prompt 10 adds briefing tests  
- Playwright: 6 passed (Prompt 9); Prompt 10 extends briefing coverage  
- Remote PostgreSQL RLS suite: 24 passed  
- pip-audit / npm production audit: 0 vulnerabilities (Prompt 9 baseline)  
- Workflows: backend, frontend, e2e, security, observability, demo-tenant  

*Prompt 10 validation must report fresh counts — do not reuse these blindly.*

## 15. Technical challenges solved

Default-deny over legacy routes; RLS portability; estimate-kind honesty across
prediction/scenarios/CoS; deterministic demo materialization; offline AI-quality
gate without live providers.

## 16. Measured engineering results

Use CI and local validation outputs only (test counts, audit zeros, graph node/
edge/finding counts from materialize/validate, manifest determinism). No
invented customer ROI.

## 17. Limitations

No Microsoft endorsement; no Marketplace; no SOC2/ISO claim; no production DR
validation claim; Jira/ADO HTTP connectors deferred; interactive Entra SPA not
shipped; synthetic demo ≠ real-world accuracy.

## 18. Future roadmap

Customer POC hardening, connector expansion as required, Entra interactive
login, production observability export — without weakening security gates.
Phase 4 features are out of Prompt 10 scope.
