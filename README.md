# SignalForge

**Predict. Simulate. Deliver.**

AI-native enterprise engineering **execution intelligence** for leaders who need
evidence-backed answers to:

> Can this team successfully deliver this initiative — and what risks threaten readiness?

SignalForge evaluates delivery-system risk, capability coverage, dependencies and
evidence. It is **not** intended to rank individual employees or automate
employment decisions.

**Microsoft has not endorsed this project.**

This README separates **IMPLEMENTED** capabilities from **POC CONFIGURATION**,
**PROPOSED**, and **DEFERRED** work. Detailed diligence lives under `docs/` and
`architecture/`.

---

## Product mission

Turn engineering capability, delivery evidence and initiative requirements into
explainable readiness decisions — with simulation, Delivery Graph findings,
honest prediction fallbacks, counterfactual scenarios, grounded Chief-of-Staff
briefs, human review, tenant isolation and observability.

## The enterprise problem

Leaders greenlight high-stakes work from fragmented signals (status decks,
spreadsheets, intuition). Capability gaps, dependency risk, ownership
concentration and key-person exposure surface too late.

## What SignalForge does

1. Assess initiative/team readiness (readiness ≠ confidence).
2. Inspect gaps, ownership concentration and decision traces.
3. Simulate team changes and persist immutable history + human review.
4. Build a Delivery Graph and review findings.
5. Run counterfactual scenarios (decision-support overlays).
6. Generate grounded Chief-of-Staff briefs with citations.
7. Operate behind default-deny authentication and tenant controls.

## Who it is for

- **Economic buyer:** CTO / VP Engineering
- **Operational buyer:** Engineering Operations / Program leadership
- **Users:** directors, managers, platform and architecture leaders
- **Reviewers:** security, data governance, enterprise architecture, procurement

See [`docs/pitch/buyer-personas.md`](docs/pitch/buyer-personas.md).

## Core capabilities (IMPLEMENTED)

| Area | Summary |
|---|---|
| Readiness intelligence | Deterministic policy_v1 readiness + confidence, gaps, key-person risk, traces |
| Simulation & review | Team simulate; immutable assessments; human review never rewrites scores |
| Connectors | GitHub REST polling; Jira/ADO descriptors only (not HTTP-implemented) |
| Delivery Graph | Relational projection/analysis/findings; rule-based confidence ≠ probability |
| Prediction | Feature snapshots + fallback `uncalibrated_score` (not a probability) |
| Scenarios | Overlay counterfactuals; 8 NovaBank stories after materialize |
| AI Chief of Staff | Grounded briefs; claims/citations; deterministic fallback |
| Security | Default-deny JWT, RBAC, audit, PostgreSQL FORCE RLS |
| Observability | Protected APIs + `/observability`; offline AI-quality gate |
| Executive briefing UI | Authenticated `/briefing` over live tenant APIs (no mock fallback) |

Full inventory:
[`architecture/phase-3-microsoft-poc-startup-pitch-readiness.md`](architecture/phase-3-microsoft-poc-startup-pitch-readiness.md).

## Architecture

FastAPI backend + Next.js frontend. Additive `/api/v2` (Phase 2 readiness) and
`/api/v3` (enterprise intelligence). Auth is default-deny: Bearer JWT required
for protected APIs; `X-SignalForge-Tenant-ID` is a **selector**, never
authentication. Alembic head: **`p3_observability_ai_quality`**.

## AI and prediction honesty

- AI does not change deterministic readiness scores.
- Briefs/CoS use provider abstraction with deterministic fallback.
- NovaBank prediction candidate is **unpromoted** / production-ineligible.
- Uncalibrated scores are **not** probabilities.
- Scenarios are **not** causal predictions.
- Mandatory tests do not call external LLMs.

## NovaBank enterprise demo

NovaBank is a **fictional** synthetic tenant (`novabank-enterprise-demo-v2`,
as_of `2026-07-31T18:00:00Z`) for demos and tests — not a real bank or customer.

```bash
cd backend
python -m app.demo novabank seed --json
python -m app.demo novabank materialize --json
python -m app.demo novabank validate
```

Canonical fresh inventory includes 14 initiatives, 24 projects, 48 engineer
profiles, 32 repositories, 8 scenarios; materialize builds graph findings and
8 Chief-of-Staff briefs. Walk the narrative at **`/briefing`** (authenticated).

Runbook: [`docs/poc/novabank-executive-demo-runbook.md`](docs/poc/novabank-executive-demo-runbook.md).

## Security and governance

Designed to support enterprise review: JWT modes including `entra_oidc`
verification, RBAC, audit, RLS on PostgreSQL, secret redaction, dependency
audits. **Not yet certified** (no SOC 2 / ISO 27001 / pen-test completion claim).
Interactive Entra/MSAL browser login is **INTEGRATION REQUIRED**. Questionnaire:
[`docs/poc/security-governance-questionnaire.md`](docs/poc/security-governance-questionnaire.md).

## Observability and AI quality

Local/in-process observability with optional OTel construct; protected
`/api/v3/observability/*` and `/observability` UI; offline AI-quality release
gate in CI. Production Azure Monitor export is **PROPOSED**, not validated.

## Microsoft enterprise POC

4–6 week evaluation blueprint (entry/exit criteria, success metrics, data
onboarding, Microsoft-aligned **proposed** hosting/identity map):
[`docs/poc/microsoft-enterprise-poc-blueprint.md`](docs/poc/microsoft-enterprise-poc-blueprint.md).

Azure Marketplace publishing, Teams, Power BI and Copilot Studio integrations
are **DEFERRED**. No Microsoft partnership or endorsement is claimed.

## Local development

```bash
git clone https://github.com/RPK2103/SignalForge.git
cd SignalForge

cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m app.db.seed

cd ../frontend
npm ci
```

Backend `.env` (see `backend/.env.example`):

```env
DATABASE_URL=sqlite:///./signalforge.db
AI_ENABLED=false
AUTH_MODE=local_development
SIGNALFORGE_LOCAL_AUTH_SECRET=<at-least-32-chars>
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Frontend `.env.local`:

```env
NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL=http://127.0.0.1:8000
```

Run:

```bash
# backend
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# frontend
cd frontend
npm run dev
```

Mint a local JWT (never commit it):

```bash
cd backend
python -m app.security issue-dev-token --subject dev --tenant novabank --roles tenant_admin
```

Inject in the browser console (non-production only):

```js
window.__SIGNALFORGE_TEST_AUTH__ = { token: "<jwt>", tenantId: "novabank" };
```

Then open `/`, `/briefing`, or `/observability` and retry if needed. Token is
in-memory only and lost on reload.

## Testing

```bash
# backend
cd backend
python -m ruff format --check app tests
python -m ruff check app tests
python -m alembic heads
python -m alembic check
python -m pytest -rs

# frontend
cd frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
npx playwright test
```

Dependency gates: `pip check`, `pip_audit -r requirements.txt --strict`,
`npm audit --omit=dev`.

PostgreSQL RLS suites require `POSTGRES_TEST_URL` (or CI service container).
SQLite does **not** prove RLS.

Report **fresh** pass/skip counts from your run; do not reuse stale README
tables as proof.

## Deployment

Operator procedures (not a claim that production was executed):

- [`docs/deployment/production-deployment-runbook.md`](docs/deployment/production-deployment-runbook.md)
- [`docs/deployment/release-and-rollback.md`](docs/deployment/release-and-rollback.md)

Render blueprint: `render.yaml`. Azure hosting remains a POC option — see the
POC blueprint — and is **not** production-validated from this repository alone.

## Documentation index

| Area | Link |
|---|---|
| Prompt 10 package | [`architecture/phase-3-microsoft-poc-startup-pitch-readiness.md`](architecture/phase-3-microsoft-poc-startup-pitch-readiness.md) |
| POC blueprint | [`docs/poc/microsoft-enterprise-poc-blueprint.md`](docs/poc/microsoft-enterprise-poc-blueprint.md) |
| Success framework | [`docs/poc/poc-success-framework.md`](docs/poc/poc-success-framework.md) |
| Security questionnaire | [`docs/poc/security-governance-questionnaire.md`](docs/poc/security-governance-questionnaire.md) |
| Data onboarding | [`docs/poc/data-onboarding-plan.md`](docs/poc/data-onboarding-plan.md) |
| Demo runbook | [`docs/poc/novabank-executive-demo-runbook.md`](docs/poc/novabank-executive-demo-runbook.md) |
| Executive one-pager | [`docs/pitch/executive-one-pager.md`](docs/pitch/executive-one-pager.md) |
| Personas | [`docs/pitch/buyer-personas.md`](docs/pitch/buyer-personas.md) |
| ROI hypothesis | [`docs/pitch/roi-hypothesis-model.md`](docs/pitch/roi-hypothesis-model.md) |
| Competitive positioning | [`docs/pitch/competitive-positioning.md`](docs/pitch/competitive-positioning.md) |
| Pitch outline | [`docs/pitch/startup-pitch-outline.md`](docs/pitch/startup-pitch-outline.md) |
| Objections | [`docs/pitch/objections-and-responses.md`](docs/pitch/objections-and-responses.md) |
| Case study | [`docs/portfolio/signalforge-case-study.md`](docs/portfolio/signalforge-case-study.md) |
| Evidence index | [`docs/evidence/production-readiness-evidence-index.md`](docs/evidence/production-readiness-evidence-index.md) |
| Production deployment runbook | [`docs/deployment/production-deployment-runbook.md`](docs/deployment/production-deployment-runbook.md) |
| Release / rollback | [`docs/deployment/release-and-rollback.md`](docs/deployment/release-and-rollback.md) |
| Phase 3 roadmap | [`architecture/phase-3-enterprise-product-roadmap.md`](architecture/phase-3-enterprise-product-roadmap.md) |
| Agent / Cloud notes | [`AGENTS.md`](AGENTS.md) |

## Limitations

- No production/paid customer traction claimed; ROI is hypothesis-only.
- No Microsoft endorsement, partnership, certification, or Marketplace listing.
- NovaBank is synthetic / production-ineligible.
- Jira/ADO HTTP connectors, GitHub webhooks/OAuth, Teams, Power BI, Copilot Studio: deferred or not implemented.
- Interactive Entra login SPA not shipped.
- Secret vault integration recommended, not implemented in-app.
- No SOC 2 / ISO 27001 / formal pen-test / production DR validation claimed.

## Roadmap

Core engines of Phase 3 Prompts 1–9 are in product code, with residuals:
interactive Entra/MSAL SPA = **INTEGRATION REQUIRED**; NovaBank demo seed/reset =
CLI-only (no public mutation API); background workers, API rate limiting, scoped
API keys, and load-scale tests = **DEFERRED** or **NOT VALIDATED** as applicable.
Prompt 10 packages POC and pitch readiness. Further work is customer-driven POC
hardening and deferred integrations — not a new Phase 4 engine in this milestone.

## Disclaimer

SignalForge is decision-support software. Outputs can be wrong or incomplete.
Humans remain accountable for delivery decisions. Synthetic demos are not
customer evidence. Uncalibrated scores are not probabilities. Scenario overlays
are not causal predictions.
