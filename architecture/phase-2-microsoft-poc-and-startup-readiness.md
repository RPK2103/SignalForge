# SignalForge — Microsoft POC & Startup Due-Diligence Readiness

_An honest, evidence-based assessment of where SignalForge stands at the end of
Phase 2, and the smallest credible path to a Microsoft POC and startup pitch._

> No Microsoft endorsement is claimed. No funding-readiness is claimed. Every
> strength below is backed by Phase 2 command/repository evidence; every gap is a
> real, uncompleted item.

---

## 1. Current Strengths (evidenced)

| Strength | Evidence |
| --- | --- |
| Deterministic decision support | Policy-versioned scoring; `pytest` 323 passed |
| Readiness vs confidence separation | Distinct scores in API + UI (Phase 8: 74 / 85) |
| Explainability | Decision traces returned + rendered |
| Team simulation | add/remove/replace/compare with deltas (Phase 8: -51 readiness) |
| Immutable snapshots | Persisted assessment/simulation records with hashes |
| Human review | Reviews recorded without altering scores (verified) |
| Grounded Leadership Briefs | Grounding validation + deterministic fallback (`ai_disabled`) |
| Typed frontend | TypeScript, lint/typecheck/build green; 23 Vitest tests |
| CI + E2E | 4 GitHub Actions workflows; Playwright 22-step E2E passing |
| Clean engineering hygiene | Ruff green, single Alembic head, idempotent seed |

## 2. Current Gaps (real, uncompleted)

- Real customer discovery / interviews.
- Real connectors (GitHub / Jira / Azure DevOps) — currently synthetic mock data.
- Historical delivery data for training/backtesting.
- Calibrated prediction (Phase 2 uses deterministic policy scores, not ML).
- Tenant isolation / multi-tenancy.
- Authentication, RBAC, Entra ID.
- Production observability (OpenTelemetry, SLOs, alerts).
- Public deployment validation (deferred; no live URL tested).
- Pilot evidence and measurable ROI.

---

## 3. Smallest Credible Microsoft POC

Scope deliberately minimal but end-to-end:

1. **One engineering organization** (a consented customer or an internal team).
2. **One or two evidence sources** (e.g. a GitHub org + Azure DevOps project),
   read-only, least-privilege.
3. **A few selected initiatives** with known target dates.
4. **Capability-dependency analysis** derived from real evidence.
5. **Delivery-risk visibility**: readiness + confidence per initiative.
6. **Scenario simulation**: add/remove/replace a key engineer; show the delta.
7. **A weekly grounded Leadership Brief** summarizing risk and change.
8. **Measurable success criteria**, agreed up front, e.g.:
   - Leaders rate delivery-risk visibility ≥ 4/5 usefulness.
   - ≥ 2 real delivery risks surfaced before they materialized.
   - Simulation influenced ≥ 1 staffing/scope decision.
   - Weekly brief adopted by the leadership team for the pilot duration.

POC hosting target: Azure (App Service/Container Apps + Azure Database for
PostgreSQL + optional Azure OpenAI), with AI kept behind the grounded-fallback
boundary already implemented.

## 4. What the POC Deliberately Excludes

Full multi-tenant SaaS, self-serve onboarding, broad connector coverage, and
calibrated ML prediction. Those are Phase 3 roadmap items (Prompts 1–8) and are
not required to prove the core decision-support value.

---

## 5. Startup Due-Diligence Assessment

**Credible as:** an explainable engineering-execution decision-support prototype
with strong engineering hygiene (tests, CI, E2E, migrations, security audits).

**Not yet fundable on outcomes.** Missing, specifically:

- Pilot evidence with real users.
- Customer interviews establishing willingness to pay.
- Historical backtesting demonstrating predictive value + calibration.
- Production security evidence (auth, isolation, threat model).
- Measured ROI (time saved, risks caught, decisions improved).

**Path to fundability** is the above artifacts — produced via the Microsoft POC
and Phase 3 roadmap — not additional features. Do **not** claim funding readiness
until pilot evidence, customer interviews, historical backtesting, ROI evidence
and production security evidence exist.
