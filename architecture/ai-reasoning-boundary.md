# SignalForge AI Reasoning Boundary — Leadership Brief

**Status:** Implemented (Phase 2, Prompt 6)  
**Prompt version:** `leadership-brief-v1`  
**Snapshot schema version:** 1  
**Last verified:** 2026-07-24

---

## 1. Executive Summary

Phase 2 Prompt 6 adds a **structured, grounded Leadership Brief** for persisted assessments. Azure OpenAI (when enabled and configured) summarizes deterministic evidence for executives. When AI is disabled, misconfigured, or fails validation, a **deterministic fallback** produces an equally structured brief.

AI is a **communication layer only**. Readiness scoring, confidence scoring, simulation math, and assessment identifiers remain deterministic and unchanged.

---

## 2. Scope

- Versioned prompt templates under `backend/app/prompts/leadership_brief/v1/`
- Canonical evidence package derived from immutable assessment snapshots
- Stable evidence identifiers (`risk:<hash>`, `trace:<hash>`)
- Azure OpenAI provider with bounded timeout/retries
- Strict JSON parsing, schema validation, and grounding validation
- Deterministic fallback provider (`policy_v1.py`)
- Append-only `leadership_briefs` persistence with audit events
- Production APIs under `/api/v2/assessments/{assessment_record_id}/leadership-brief`

## 3. Non-Goals

- Frontend integration (deferred)
- Live Azure OpenAI validation in CI (deferred unless explicitly opted in)
- Authentication / authorization
- User-controlled prompts, models, or deployments
- Recomputing assessments from current catalog data

---

## 4. Deterministic vs AI Responsibilities

| Deterministic | AI (Azure OpenAI) |
|---------------|-------------------|
| Readiness score | Executive summary wording |
| Confidence score | Risk prioritization narrative |
| Risk findings | Staffing action phrasing |
| Decision trace | Mitigation action phrasing |
| Skill gaps | Leadership decision label from bounded enum |
| Assessment / record IDs | Organization of supplied evidence |

**Prohibited AI behavior:** invent engineers, capabilities, metrics, scores, risks, or trace entries; mutate snapshots; hide provider failures; return unstructured prose as the production contract.

---

## 5. Historical Snapshot as Source of Truth

Generation loads the persisted assessment by `assessment_record_id`, verifies snapshot hashes, and deserializes `result_snapshot["data"]`. It does **not** call readiness scoring or read current catalog rows for historical truth.

If snapshot integrity fails, generation aborts with `snapshot_integrity_error` and persists no brief.

---

## 6. Evidence Package

Built by `build_evidence_package()` from stored assessment data:

- assessment IDs, project metadata, team member IDs
- readiness/confidence scores and levels
- dimension scores, skill gaps, capability coverage
- risk findings and decision trace entries with stable evidence IDs
- deterministic assessment summary
- optional `latest_review_state` (clearly separated from deterministic findings)

Excluded: credentials, SQL, stack traces, unrelated records, mutable ORM objects.

---

## 7. Stable Evidence Identifiers

- **Risk:** SHA-256 (16 hex chars) over canonical JSON of finding type, capability ID, engineer ID, severity, policy rule, message → `risk:<hash>`
- **Trace:** SHA-256 over step, component, label, value, contribution, policy version → `trace:<hash>`

Same snapshot → same IDs. Ordering of lists does not change IDs.

---

## 8. Evidence Package Hashing

Evidence is stored in a versioned snapshot envelope `{schema_version, policy_version, data}`. `evidence_package_hash` is SHA-256 of canonical JSON bytes of the full envelope.

---

## 9–10. Prompt Versioning and Structure

- Version: `leadership-brief-v1`
- Files: `system.txt` (instructions), `user.txt` (schema + evidence JSON)
- Loaded via `Path(__file__)` — not dependent on working directory
- Evidence JSON is structurally separated from system instructions

---

## 11. Prompt-Injection Boundary

Evidence fields are treated as **data**. System prompt instructs the model to ignore instruction-like content inside evidence. Users cannot supply custom prompts or select deployments via API.

---

## 12. LeadershipBrief Schema

Bounded enums for `decision`, `provider_mode`, `generation_status`, severities, and priorities. Every risk and action requires `evidence_references`. Top-level references must equal the deduplicated nested union. No AI-generated score fields.

---

## 13–15. Providers

- **Interface:** `LeadershipBriefProvider.generate(evidence_package_json, prompt_bundle)`
- **Azure:** uses existing `openai` SDK + settings; JSON object response format; timeout `AI_REQUEST_TIMEOUT_SECONDS` (default 30); retries `AI_MAX_RETRIES` (default 2)
- **Fallback:** pure deterministic rules in `policy_v1.py`; `provider_mode=deterministic_fallback`, `generation_status=fallback_generated`

---

## 16. Provider Selection Rules

| Condition | Result |
|-----------|--------|
| `AI_ENABLED=false` | Fallback (`ai_disabled`) |
| Missing Azure config | Fallback (`missing_configuration`) |
| Azure success + valid schema + grounding | Azure brief |
| Timeout / auth / rate limit / unavailable | Fallback with mapped category |
| Malformed JSON / schema / grounding / empty output | Fallback with mapped category |

Provider failures are never represented as successful Azure generation.

---

## 17–22. Validation

- **Parsing:** strict JSON, no silent markdown fence acceptance
- **Schema:** Pydantic `LeadershipBrief` with `extra=forbid`
- **Grounding:** all references must exist in evidence package; capability/engineer IDs validated
- **Unsupported numbers:** conservative check for large unknown numerals in text

---

## 23–25. Persistence and Audit

Table: `leadership_briefs` (append-only). Stores evidence/output snapshots and hashes. Audit event: `leadership_brief_created` in same transaction.

API:

- `POST /api/v2/assessments/{assessment_record_id}/leadership-brief` (no body)
- `GET /api/v2/assessments/{assessment_record_id}/leadership-briefs` (newest first)

---

## 26–29. Security, Privacy, Timeout/Retry, Testing

- Secrets never logged; full prompts/responses not logged
- Bounded timeout and retries
- 69+ new automated tests; no live Azure calls in CI
- Live local validation: `python scripts/live_leadership_brief_validation.py` with `AI_ENABLED=false`

---

## 30–35. Deployment, Limitations, Deferred Work

- **Live Azure validation:** deferred (mock-validated only)
- **PostgreSQL:** DDL compatibility reviewed; live connection deferred
- **Free-text hallucination:** structurally grounded but human review still required for high-impact decisions
- **Frontend:** not connected in this milestone

Alembic revision: `a1b2c3d4e5f6` (`leadership_briefs`) on top of `d573b27e3974`.

---

*End of AI reasoning boundary document.*
