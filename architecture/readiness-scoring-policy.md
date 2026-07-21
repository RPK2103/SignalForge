# Readiness Scoring Policy (v1)

**Policy version:** `v1`  
**Module:** `backend/app/domain/policy/v1.py`  
**Effective:** Phase 2 — deterministic intelligence domain

This document describes the explicit, testable scoring rules used by the Phase 2 readiness assessment pipeline. **No AI model calculates these scores.**

---

## Design Principles

1. **Deterministic** — identical inputs always produce identical outputs.
2. **Separated concerns** — readiness score and confidence score are computed independently.
3. **Traceable** — every score contribution is recorded in the decision trace.
4. **Versioned** — thresholds and weights live in `policy/v1.py`, not scattered constants.
5. **Legacy-compatible** — legacy MVP routes translate through adapters; boolean coverage percentages for simulator/predictor preserve MVP thresholds.

---

## Capability Categories

Required bounded categories (enum `CapabilityCategory`):

| Category | ID |
|----------|-----|
| Backend | `backend` |
| Cloud | `cloud` |
| AI | `ai` |
| Data | `data` |
| DevOps | `devops` |
| Architecture | `architecture` |
| Security | `security` |
| Delivery Execution | `delivery_execution` |

---

## Evidence and Proficiency

Engineer proficiency (0–100) is derived from evidence sources:

| Evidence Pattern | Base Proficiency |
|------------------|------------------|
| Skills only | 55 |
| Skills + projects | 65 |
| Skills + certifications | 75 |
| Skills + certifications + projects | 85 |

**Experience bonus:** `+2` per year, capped at `+15`.

---

## Coverage Classification

Team proficiency for a requirement = **max proficiency** among covering engineers.

| Level | Condition |
|-------|-----------|
| **Missing** | 0 covering engineers OR team proficiency = 0 |
| **Weak** | Team proficiency 1–39 |
| **Adequate** | Team proficiency 40–69 |
| **Strong** | Team proficiency ≥ 70 |

### Critical Requirements

Project requirements may be flagged `critical=True`. Missing or weak critical capabilities trigger:

- `RiskFindingType.MISSING_CRITICAL_CAPABILITY` (severity: high)
- `RiskFindingType.WEAK_CAPABILITY` (severity: medium)
- Confidence penalties (see below)

When mapped from legacy MVP projects with ≤3 required skills, all requirements are treated as critical.

---

## Weighted Requirements

Each `ProjectRequirement` carries a `weight > 0`. Coverage percentage for readiness dimensions uses:

```
earned = Σ(weight × level_multiplier)
total  = Σ(weight)
coverage_pct = round(earned / total × 100)
```

### Level Multipliers

| Level | Multiplier |
|-------|------------|
| Missing | 0.0 |
| Weak | 0.4 |
| Adequate | 0.7 |
| Strong | 1.0 |

---

## Readiness Score

Readiness is a **weighted blend of five dimensions** minus risk penalties, clamped to 0–100.

### Dimension Weights (sum = 1.0)

| Dimension | Weight |
|-----------|--------|
| Capability Coverage | 0.45 |
| Skill Depth | 0.20 |
| Team Balance | 0.15 |
| Delivery Risk | 0.10 |
| Evidence Quality | 0.10 |

### Dimension Calculations

- **Capability Coverage** — weighted coverage percentage (see above)
- **Skill Depth** — average team proficiency across non-missing requirements
- **Team Balance** — `100 − (single_person_dependencies / total_requirements × 100)`
- **Delivery Risk** — equals capability coverage percentage
- **Evidence Quality** — average per-engineer score (100 base, −25 no certs, −25 no projects, −20 low experience)

### Risk Penalties (subtracted from weighted readiness)

| Finding | Penalty |
|---------|---------|
| Missing critical capability | 15 |
| Key person dependency (high) | 12 |
| Key person dependency (medium) | 8 |
| Duplicate team member | 5 (50% of confidence duplicate penalty) |

### Empty Team

If the team is empty after deduplication, readiness = **0**.

---

## Confidence Score

Confidence starts at **100** and is reduced independently of readiness.

| Condition | Penalty |
|-----------|---------|
| Empty team | 40 |
| Engineer without certifications | 8 per engineer |
| Engineer without project history | 8 per engineer |
| Missing critical capability | 20 |
| Weak critical capability | 10 |
| Key person dependency | 15 per finding |
| Duplicate team member | 10 |
| Incomplete evidence finding | 12 |

### Confidence Levels

| Score | Level |
|-------|-------|
| ≥ 80 | High |
| 50–79 | Medium |
| < 50 | Low |

---

## Key Person Risk

A **key person dependency** is detected when exactly one engineer covers a non-missing capability.

- Critical capability → severity **high**
- Non-critical capability → severity **medium**

---

## Decision Trace

Every scoring step appends a `DecisionTraceEntry`:

```json
{
  "step": "readiness | confidence | coverage",
  "component": "requirement | dimension | risk_penalty | evidence | ...",
  "label": "<identifier>",
  "value": "<human-readable detail>",
  "contribution": <float>,
  "policy_version": "v1"
}
```

**Reconciliation rules:**

- `readiness` step contributions (dimensions + risk penalties + normalization) sum to the final readiness score.
- `confidence` step contributions sum to the final confidence score.
- `coverage` step entries document per-requirement weighted coverage detail and are informational.

Normalization/clamping adds a final trace entry when raw totals fall outside 0–100.

---

## Legacy Adapter Mapping

Legacy MVP routes (`/recommend-team`, `/simulate`, `/success-prediction`, `/copilot`) translate:

1. Legacy `EngineerProfile` → domain `EngineerProfile` with inferred capabilities
2. Legacy `ProjectRequirements.required_skills` → domain `ProjectRequirement` list
3. Domain coverage results → legacy skill name lists and boolean coverage percentages

### Legacy Delivery Risk Thresholds

| Coverage % | Risk Level |
|------------|------------|
| ≥ 80 | Low |
| 70–79 | Medium |
| < 70 | High |

### Legacy Success Probability (simulator)

```
success_probability = clamp(coverage − risk_penalty, 0, 100)
```

Risk penalties: Low = 0, Medium = 15, High = 30.

### Legacy Success Prediction (predictor)

```
probability = 0.5 × coverage + 0.3 × team_quality + 0.2 × (100 − delivery_risk_score)
```

Delivery risk scores: Low = 10, Medium = 45, High = 75.

---

## Service Architecture

```
ReadinessAssessmentService
├── CapabilityCoverageService
├── SkillGapService
├── KeyPersonRiskService
├── ReadinessScoringService  → DecisionTraceService
└── ConfidenceService        → DecisionTraceService
```

**Rules:**

- Services do not import private functions from other services.
- Services do not read global mock dictionaries directly — catalog data flows through `MockCatalogRepository`.
- Shared helpers live in `app/domain/evidence.py`.

---

## Test Coverage

Unit tests in `backend/tests/intelligence/` cover:

- Balanced team
- Missing critical capability
- Weak capability
- Key person dependency
- Duplicate engineers
- Empty team
- No project requirements
- Incomplete engineer evidence
- Score boundaries (0–100)
- Confidence boundaries
- Deterministic repeatability
- Decision trace structure
- Weighted requirement behavior
- Legacy adapter mapping

Run tests:

```powershell
cd backend
python -m pytest tests/intelligence -v
python -m pytest -v
```

---

## Versioning

To introduce new scoring behavior:

1. Add `backend/app/domain/policy/v2.py` with a new `POLICY_VERSION`.
2. Register it in `backend/app/domain/policy/__init__.py`.
3. Update this document with a v2 section.
4. Add migration tests comparing v1 and v2 on reference fixtures.

Existing assessments remain reproducible by passing `policy_version="v1"`.
