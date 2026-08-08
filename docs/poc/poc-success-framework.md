# POC Success-Measurement Framework

All metrics below define **how to measure**. They do **not** claim measured
customer results. Separate:

1. **Demonstrated NovaBank values** — synthetic demo only
2. **Suggested POC targets** — starting points for negotiation
3. **Customer-specific targets** — set during discovery

## Metric template

Every metric uses: name · definition · numerator · denominator · collection
method · target/acceptance range · interpretation · limitations.

---

## 1. Data quality

### Source coverage
- **Definition:** Share of approved source systems with at least one successful
  ingestion in the evaluation window.
- **Numerator / denominator:** sources with success / approved sources.
- **Collection:** connector checkpoints + ingestion receipts.
- **Suggested POC target:** 100% of *required* sources; optional sources tracked
  separately.
- **Limitations:** Coverage ≠ completeness of records inside a source.

### Freshness
- **Definition:** Age of latest successful sync per stream.
- **Collection:** connector freshness APIs / observability freshness.
- **Suggested POC target:** customer-defined SLA per source.
- **Limitations:** Clock skew and never-synced states must remain honest
  (`unavailable` / `never_synced`).

### Completeness
- **Definition:** Required fields present for mapped entities.
- **Collection:** data-quality checks during onboarding reconciliation.
- **Limitations:** Missing optional fields should not be scored as failures.

### Duplicate rate
- **Definition:** Duplicate source keys after normalization / total ingested.
- **Collection:** ingestion receipts + dedup logs.
- **Limitations:** Deterministic dedup of EvidenceSignal is not the same as
  business-duplicate people/repos.

### Unresolved identities
- **Definition:** Source identities without tenant person/repo mapping.
- **Suggested POC target:** trending down week over week; absolute target set
  with data owner.

### Missing ownership / dependency links
- **Definition:** Repos/projects lacking ownership edges; initiatives lacking
  declared dependencies where owners assert they exist.
- **Collection:** graph findings + manual reconciliation worksheets.

### Demonstrated NovaBank (synthetic)
Canonical Prompt 9 inventory (fresh DB): 14 initiatives, 24 projects,
48 engineer profiles, 32 repositories, 8 scenarios, graph rebuild with findings.
These are **demo fixtures**, not POC attainment.

---

## 2. Intelligence quality

| Metric | Definition | Notes |
|---|---|---|
| Evidence grounding | Claims with required evidence ids / total claims sampled | CoS claim support status |
| Citation validity | Citations resolving to package evidence / citations sampled | Sampled human review |
| Finding precision | Accepted findings / (accepted + dismissed as false) | Human review |
| Finding usefulness | Findings rated actionable by managers / reviewed findings | Qualitative rubric |
| Prediction availability | Targets with non-`insufficient_data` estimates / evaluated targets | Preserve estimate_kind |
| Calibration status | Whether active model is production-eligible and calibrated | NovaBank: unpromoted; scorecard fallback |
| Scenario consistency | Re-runs with identical inputs yield identical result hashes | Determinism tests |
| Unsupported-claim rate | Unsupported claims / claims in sampled briefs | AI-quality scanners + review |

**Do not** treat uncalibrated scores as calibrated probabilities.

---

## 3. Human review

| Metric | Definition |
|---|---|
| Engineering-manager agreement | Agree / reviewed findings |
| Program-lead agreement | Agree / reviewed initiative briefs |
| Disputed findings | Disputed / reviewed |
| Accepted findings | Accepted / reviewed |
| Dismissed findings | Dismissed / reviewed |
| Actionable recommendations | Recommendations with owned follow-ups / recommendations offered |
| Reviewer turnaround | Median hours from brief availability to first review |

---

## 4. Security

| Metric | Definition | Evidence posture |
|---|---|---|
| Tenant isolation | Cross-tenant reads denied in tests/review | App tenancy + PG FORCE RLS |
| Least privilege | Role matrix matches assigned principals | RBAC matrix |
| Authentication | Unauthenticated protected routes = 401 | Default-deny middleware |
| Authorization | Authenticated without permission = 403 | require_permission |
| Required audit coverage | Sensitive actions audited | audit service + API |
| Secret handling | No secrets in frontend/source/logs | gitleaks + redaction |
| Data retention / export | Customer policy documented and enforceable | POC CONFIGURATION |

No SOC 2 / ISO 27001 / penetration-test completion is claimed unless proven.

---

## 5. Operations

| Metric | Collection |
|---|---|
| Ingestion reliability | success ratio / lag |
| Materialization reliability | graph rebuild success |
| Graph rebuild reliability | idempotent rebuild tests + ops logs |
| Observability | `/api/v3/observability/*` + dashboard |
| Failure recovery | CLI dead-letter replay + customer IR process (no dedicated ops failure-recovery runbook packaged in Prompt 10; demo runbook is presentation-only) |
| Deployment reproducibility | CI workflows + env docs |
| Support ownership | named customer + SignalForge contacts |

---

## 6. Adoption

| Metric | Definition |
|---|---|
| Executive-brief consumption | Briefs opened / briefs generated |
| Scenario-workshop participation | Attendees / invited |
| Follow-up action creation | Actions created from workshops |
| Repeated usage | Distinct active users week 4 vs week 2 |
| Qualitative usefulness | Structured interview score |

---

## Safeguards

- Do not double-count the same risk across multiple benefit lines.
- Do not treat every identified risk as avoided loss.
- Do not count NovaBank outcomes as customer evidence.
- Do not treat scenario deltas as causal.
- Include implementation and change-management cost in any ROI hypothesis
  (see `docs/pitch/roi-hypothesis-model.md`).
