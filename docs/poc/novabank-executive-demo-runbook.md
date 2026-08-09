# NovaBank Executive Demo Runbook

**NovaBank is fictional.** All data is synthetic and production-ineligible.
Uncalibrated scores are **not** probabilities. Scenario results are
decision-support overlays, **not** causal predictions.
**Microsoft has not endorsed this project.**

Auth reminder (local/dev only): mint a short-lived JWT and inject
`window.__SIGNALFORGE_TEST_AUTH__ = { token, tenantId: "novabank" }`, then open
the UI. Never commit tokens. Prefer the Executive briefing page for Phase 3
narrative; readiness dashboard remains the Phase 2 assessment flow.

Discover records through the UI/API by **name** — do not hardcode generated IDs.

## Product surfaces

| Step | Screen / endpoint |
|---|---|
| Portfolio | `/briefing` → organization + demo summary counts |
| Findings | `/briefing` → Delivery Graph findings list |
| Initiatives | `/briefing` → Initiatives |
| Scenarios | `/briefing` → scenario select + detail |
| Chief of Staff | `/briefing` → brief select + claims/citations |
| Observability | `/observability` |
| Phase 2 readiness | `/` (catalog assess/review/brief/simulate) |
| APIs (fallback) | `/api/v3/demo/summary`, `/api/v3/initiatives`, `/api/v3/delivery-graph/*`, `/api/v3/scenarios/*`, `/api/v3/chief-of-staff/*` |

Prerequisites: `python -m app.demo novabank seed` and
`python -m app.demo novabank materialize` (deterministic fallback).

---

## 7-minute executive flow (default)

| # | Navigation | Expected live data | Executive message | Technical proof | Fallback | Avoid claiming | Transition |
|---|---|---|---|---|---|---|---|
| 1 | `/briefing` | Org NovaBank; initiative/project/engineer/repo counts | “This is a synthetic enterprise portfolio we use to demonstrate delivery intelligence.” | Demo summary tiles | If empty: seed not run — say so | Real bank / real customer | Open findings |
| 2 | Findings list | Ownership concentration / dependency findings | “We surface delivery-system risks with explanations.” | Finding title + severity | Empty findings → materialize | Causal certainty | Select fraud-related initiative by name |
| 3 | Initiatives | Fraud-detection (or similarly named) initiative | “Leaders ask: can this launch succeed given capability and dependency risk?” | Initiative row | Paginate to find name | Guaranteed launch failure | Open scenarios |
| 4 | Scenario: payment / dependency | Scenario definition + run result | “If a critical dependency slips, overlays show affected initiatives.” | estimate_kind labelled uncalibrated | No run → explain materialize | Causal prediction | Next scenario |
| 5 | Scenario: Azure capability shortage | Scenario kind + affected counts | “Capability shortage is first-class, not a spreadsheet afterthought.” | Affected critical initiative count | Same | Probability language | Role-transition scenario |
| 6 | Scenario: critical engineer transition | Result delta | “We model availability risk on the delivery system — we do not rank employees.” | Disclaimer on page | Same | Surveillance / HR scoring | Open CoS brief |
| 7 | CoS brief | Claims labelled Evidence/Inference/Recommendation + citations | “Briefs are grounded; unsupported claims are rejected or labelled.” | Citations list | Empty briefs → materialize | Autonomous agent / endorsement | Optional `/observability` |

---

## 3-minute version

1. `/briefing` portfolio + synthetic banner (30s)
2. One high-severity finding (45s)
3. One scenario with uncalibrated-score honesty (60s)
4. One CoS brief with Evidence + Citation (45s)

Skip deep initiative pagination and observability.

---

## 15-minute technical version

Add after the 7-minute flow:

8. Payment-modernization dependency path narrative (findings + scenario).
9. Customer Copilot readiness initiative (capability framing; not M365 product).
10. Incident-driven roadmap delay scenario.
11. Concentrated repository ownership finding detail.
12. Cross-team platform bottleneck discussion.
13. Citation validation walkthrough on a brief.
14. `/observability` — request health, SLO states, AI-quality gate (local).
15. Security one-liner: default-deny JWT, tenant selector ≠ auth, RLS on PostgreSQL.

API fallback (developer-assisted): use OpenAPI or curl with bearer token; still
discover IDs from list endpoints.

---

## Claims to avoid in every variant

- Microsoft partnership/endorsement/Marketplace
- Real NovaBank / real customers / paid traction
- Calibrated probability on NovaBank
- Causal “if X then delivery fails” certainty
- Employee performance ranking
- ROI as measured fact
