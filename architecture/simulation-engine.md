# SignalForge Team Simulation Engine

**Status:** Implemented (Phase 2, Prompt 4)
**Policy version:** v1
**Last verified:** 2026-07-22

---

## 1. Executive Summary

The Team Simulation Engine provides deterministic what-if analysis for engineering team composition changes. It reuses the existing readiness intelligence domain for both baseline and proposed assessments, then computes structured deltas, decision-trace reconciliation, and evidence-backed mitigations.

Production entry point: `POST /api/v2/simulations`

---

## 2. Product Purpose

Engineering leaders can evaluate staffing changes before approving execution plans:

- Remove a critical engineer
- Add a missing specialist
- Replace one engineer with another
- Compare an arbitrary proposed roster against a baseline team

The engine answers readiness, confidence, coverage, gap, risk, dependency, trace, and mitigation questions without AI generation or persistence.

---

## 3. Supported Operations

| Operation | Purpose |
|-----------|---------|
| `add` | Add one engineer to the baseline team |
| `remove` | Remove one engineer from the baseline team |
| `replace` | Atomically swap outgoing and incoming engineers |
| `compare` | Evaluate an explicit proposed roster |

---

## 4. Request Model

```json
{
  "project_id": "azure_ai_migration",
  "baseline_engineer_ids": ["kavi", "arjun", "vikram"],
  "operation": {
    "type": "remove",
    "engineer_id": "kavi"
  },
  "policy_version": "v1"
}
```

Operation variants use a discriminated union (`type` field).

---

## 5. Response Model

Successful responses include:

- `simulation_id` — deterministic fingerprint
- `baseline_team` / `proposed_team`
- `baseline_assessment` / `proposed_assessment` — full readiness envelopes
- Score deltas and structured change lists
- `recommended_mitigations`

---

## 6. Domain Models

Located in `backend/app/domain/simulation_models.py`:

- `SimulationOperation` discriminated union
- `SimulationResult`
- `RiskFindingChange`, `CapabilityCoverageChange`, `KeyPersonDependencyChange`
- `DecisionTraceDelta`, `DeterministicMitigation`

Enums in `backend/app/domain/enums.py`:

- `SimulationOperationType`, `SimulationChangeType`
- `MitigationType`, `MitigationPriority`

---

## 7. Service Architecture

```
API route (simulations.py)
  → SimulationRequest validation
  → SimulationOrchestrator
  → CatalogRepository
  → TeamTransformationService
  → TeamSimulationService
  → ReadinessAssessmentService
  → SimulationDeltaService
  → MitigationService
  → SimulationResponse serialization
```

---

## 8. Dependency Direction

Simulation depends on readiness. Readiness does not depend on simulation.

Simulation services must not access mock dictionaries, FastAPI, or API schemas directly.

---

## 9. Team Transformation Rules

- Baseline engineer IDs are normalized (trim, lowercase) and deduplicated
- Baseline collections are never mutated
- `add`: incoming must not already be present
- `remove`: outgoing must be present; empty proposed team allowed
- `replace`: atomic swap; outgoing/incoming must differ
- `compare`: proposed IDs may be empty; duplicates rejected

---

## 10. Validation Rules

| Condition | Status |
|-----------|--------|
| Unknown project/engineer | 404 |
| Duplicate add / invalid remove / replace conflict | 409 |
| Same-engineer replace / duplicate compare IDs | 400 |
| Unknown policy version | 400 |
| Non-JSON Content-Type | 415 |
| Schema validation failure | 422 |

---

## 11. Baseline Immutability

The orchestrator resolves engineers into new lists. `TeamSimulationService` copies baseline and proposed engineer lists before assessment.

---

## 12. Delta Calculation Rules

- `readiness_score_delta = proposed.readiness_score - baseline.readiness_score`
- `confidence_delta = proposed.confidence_score - baseline.confidence_score`
- Only changed capabilities, gaps, risks, and dependencies are returned

---

## 13. Risk Transition Matching

Risk findings match on `(finding_type, capability_id, engineer_id)`.

Transitions: `introduced`, `resolved`, `escalated`, `deescalated`, `modified`.

---

## 14. Capability Change Matching

Compared by canonical `capability_id`. Changes include level, effective score (team proficiency), and affected engineers.

---

## 15. Gap Matching

Matched on `(capability_id, level)`. Returns newly introduced and resolved gaps only.

---

## 16. Key-Person Dependency Matching

Derived from coverage results where exactly one engineer covers a non-missing capability.

---

## 17. Decision-Trace Reconciliation

Trace entries match on `(step, component, label)`. When structural deltas do not fully explain clamped score changes, explicit `reconciliation` entries document the remainder.

---

## 18. Deterministic Mitigation Rules

Mitigations are rule-generated from deltas. Each receives a deterministic SHA-256 prefix ID and must reference known evidence keys. No Azure OpenAI calls.

---

## 19. Simulation-ID Fingerprint

```json
{
  "project_id": "azure_ai_migration",
  "baseline_engineer_ids": ["kavi", "vikram"],
  "operation": {"type": "remove", "engineer_id": "kavi"},
  "proposed_engineer_ids": ["vikram"],
  "policy_version": "v1"
}
```

Canonical JSON + SHA-256, 16-character prefix (same convention as `assessment_id`).

---

## 20. API Contract

| Method | Path |
|--------|------|
| POST | `/api/v2/simulations` |

Uses `require_json_content_type` and shared `JSON_BODY_ERROR_RESPONSES`.

---

## 21. Error Behavior

All errors use the centralized `APIErrorResponse` envelope (`detail`, `status_code`, `error_type`).

---

## 22. OpenAPI Behavior

OpenAPI documents all four operation variants via discriminated union schemas and reuses readiness assessment components for nested assessments.

---

## 23. Legacy Adapter Behavior

`POST /simulate` maps to a compare operation on the legacy recommended team minus removed engineers. Legacy response fields (`coverage_before`, `risk_before`, etc.) are preserved via `legacy_mapper` helpers.

---

## 24. Test Strategy

- Unit: transformation, simulation service, simulation ID
- API: success/error paths, Content-Type, OpenAPI, legacy regression
- E2E: catalog-driven flow and Kavi-removal scenario
- Live: `backend/scripts/live_simulation_validation.py`

---

## 25. Known Limitations

- No persistence or historical simulation retrieval
- No frontend integration in this phase
- Mitigations are deterministic templates, not AI briefs

---

## 26. Deferred Persistence Concerns

Future simulation storage and retrieval will remain under `/api/v2/simulations/*`.

---

## 27. Example Kavi-Removal Scenario

Verified against mock catalog (2026-07-22):

**Request:**

```json
{
  "project_id": "azure_ai_migration",
  "baseline_engineer_ids": ["kavi", "vikram"],
  "operation": {"type": "remove", "engineer_id": "kavi"}
}
```

**Observed results:**

| Field | Value |
|-------|-------|
| simulation_id | `2669a4307f0bef8b` |
| baseline readiness | 74 |
| proposed readiness | 23 |
| readiness_score_delta | -51 |
| confidence_delta | -35 |
| capability_coverage_changes | 3 |
| newly_introduced_gaps | 1 |
| resolved_gaps | 0 |
| key_person_dependency_changes | 3 |
| recommended_mitigations | 8 |

Removing Kavi eliminates the sole strong coverage for Generative AI and increases delivery risk materially.
