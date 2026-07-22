# Readiness API Validation Report

**Review date:** 2026-07-22
**Branch:** `feat/phase-2-production`
**Reviewer role:** Principal Staff Engineer / FastAPI production architect
**Scope:** Prompt 2.5 / Prompt 3A — Production Readiness API Layer

---

## Executive Summary

Independent inspection and end-to-end validation confirm that the deterministic Phase 2 intelligence domain is correctly exposed through `/api/v2`. All five claimed endpoints are registered, functional, and covered by automated tests. Legacy MVP routes remain unchanged.

**Verdict:** **PASS WITH FIXES**

Three gaps were confirmed during review and closed with minimal changes:

1. `assessment_id` did not include `policy_version` or canonical deduplication of engineer IDs.
2. Duplicate engineer IDs leaked duplicate team members in the API response `team` field.
3. Missing focused end-to-end integration test file and API versioning documentation.

After initial API review fixes: **100 tests pass**. After content-type hardening and OpenAPI regression: **135 tests pass**. Live Uvicorn HTTP validation succeeded.

---

## Implementation Inspected

| Area | Path | Finding |
|------|------|---------|
| App entry | `backend/app/main.py` | v2 router included after legacy routers |
| v2 router | `backend/app/api/v2/router.py` | Centralized `prefix="/api/v2"` |
| Readiness route | `backend/app/api/v2/readiness.py` | Thin handler → orchestrator only |
| Capabilities | `backend/app/api/v2/capabilities.py` | Registry lookup only |
| Catalog | `backend/app/api/v2/catalog.py` | Repository + policy metadata |
| Schemas | `backend/app/schemas/api_v2.py` | `ReadinessAssessResponse` extends domain model |
| Orchestrator | `backend/app/services/readiness_orchestrator.py` | Lookup + coordination only |
| Repository | `backend/app/repositories/mock_catalog_repository.py` | Owns mock catalog access |
| Intelligence | `backend/app/services/intelligence/*` | Scoring isolated from API |
| Policy | `backend/app/domain/policy/v1.py` | Centralized thresholds/weights |
| Error envelope | `backend/app/core/exceptions.py` | Centralized `APIErrorResponse` |
| Content-Type dependency | `backend/app/api/dependencies.py` | Reusable `require_json_content_type` |
| OpenAPI error responses | `backend/app/core/openapi.py` | Shared `JSON_BODY_ERROR_RESPONSES` |
| API tests | `backend/tests/api/test_readiness_api.py` | 50+ API integration tests |
| Content-Type unit tests | `backend/tests/api/test_content_type_dependencies.py` | Media-type matching tests |
| E2E tests | `backend/tests/e2e/test_readiness_v2_flow.py` | Added during review |

---

## API Inventory

### Production (`/api/v2`)

| Method | Path | Verified |
|--------|------|----------|
| POST | `/api/v2/readiness/assess` | Yes (TestClient + HTTP) |
| GET | `/api/v2/capabilities` | Yes |
| GET | `/api/v2/policies/readiness` | Yes |
| GET | `/api/v2/engineers` | Yes |
| GET | `/api/v2/projects` | Yes |

### Legacy (unchanged)

All 8 POST intelligence routes plus `/`, `/health`, `/dashboard/*`, `/docs`, `/openapi.json` remain registered and tested.

---

## Request Flow

```
POST /api/v2/readiness/assess
  → require_json_content_type (415 if unsupported/missing Content-Type)
  → ReadinessAssessRequest (Pydantic validation)
  → ReadinessOrchestrator.assess()
      → CatalogRepository lookup (project + engineers)
      → ReadinessAssessmentService.assess()
  → ReadinessAssessResponse (domain fields + assessment_id + team)
  → Centralized error envelope on failures
```

---

## Architecture Findings

### Confirmed strengths

| Check | Result |
|-------|--------|
| v2 prefix centralized in one router | Pass |
| Routers contain no scoring logic | Pass |
| Routers do not import `MOCK_ENGINEERS` / `MOCK_PROJECTS` | Pass |
| Orchestrator does not implement scoring | Pass |
| Repository owns catalog lookup | Pass |
| `ReadinessAssessResponse` extends domain model | Pass |
| Domain models do not import FastAPI | Pass |
| Centralized error envelope used | Pass |
| No Azure OpenAI in readiness path | Pass |
| Legacy routes preserved | Pass |
| OpenAPI documents all v2 endpoints | Pass |
| JSON Content-Type enforced at API layer | Pass |
| Unsupported media type returns 415 | Pass |

### Violations found

| ID | Severity | Description |
|----|----------|-------------|
| V1 | P1 | `assessment_id` omitted `policy_version` and did not deduplicate engineer IDs |
| V2 | P1 | Response `team` included duplicate members when duplicate IDs submitted |
| V3 | P2 | No dedicated e2e integration test file |
| V4 | P2 | No API versioning strategy document |
| V5 | P2 | Unsupported Content-Type on assess returned HTTP 500 instead of 415 |

### Violations fixed

| ID | Fix |
|----|-----|
| V1 | Canonical JSON fingerprint with sorted unique engineer IDs + policy version in `_build_assessment_id()` |
| V2 | Deduplicated `team` in orchestrator response via `deduplicate_team()` |
| V3 | Added `backend/tests/e2e/test_readiness_v2_flow.py` |
| V4 | Added `architecture/api-versioning.md` |
| V5 | Added `require_json_content_type` dependency, 415 error envelope, OpenAPI documentation |

### Not changed (accepted)

| Item | Rationale |
|------|-----------|
| Extra request fields silently ignored | Matches legacy Pydantic convention (no `extra="forbid"`) |
| Pre-existing private cross-service imports in legacy services | Out of v2 scope; legacy still functional |
| Legacy route content-type behavior | Unchanged — v2 JSON policy applies only where dependency is attached |

---

## Content-Type Hardening (V5 Fix)

### Original defect

`POST /api/v2/readiness/assess` returned **HTTP 500** (`error_type: internal_error`) when called with unsupported media types such as `Content-Type: text/plain`, even though the request body contained valid JSON.

### Confirmed root cause

1. FastAPI does not JSON-decode the body when `Content-Type` is not a JSON media type.
2. Pydantic receives raw `bytes`, raising `RequestValidationError` with `input: b'...'`.
3. The centralized validation handler attempted to JSON-serialize `exc.errors()` including the raw `bytes` value.
4. Serialization failed with `TypeError: Object of type bytes is not JSON serializable`.
5. The unhandled exception fell through to the generic 500 handler.

Reproduction confirmed for: `text/plain`, missing `Content-Type`, `application/xml`, `multipart/form-data`.

### Selected media-type policy

| Policy | Behavior |
|--------|----------|
| Missing `Content-Type` on body-bearing assess requests | HTTP 415 |
| Supported JSON media types | Process normally |
| Unsupported media types | HTTP 415 with centralized envelope |
| Malformed JSON with valid JSON Content-Type | HTTP 422 (unchanged) |
| Schema-invalid JSON | HTTP 422 (unchanged) |
| Legacy routes | Unchanged |

Validation runs in `require_json_content_type` — a Request-only FastAPI dependency that executes **before** body parsing. No middleware, no domain-layer changes.

### Supported JSON media types

- `application/json`
- `application/json; charset=utf-8` (and other parameters)
- Structured JSON types matching `application/*+json` (e.g. `application/vnd.api+json`, `application/problem+json`, `application/ld+json`)

Rejected explicitly (non-exhaustive): `text/plain`, `application/xml`, `text/xml`, `multipart/form-data`, `text/json`, `application/javascript`.

Matching logic: exact `application/json` **or** media type starting with `application/` and ending with `+json`. Parameters such as `charset` are stripped before comparison.

### Unsupported content-type behavior

HTTP **415 Unsupported Media Type** with centralized envelope:

```json
{
  "detail": "Request body must use Content-Type application/json or a structured JSON media type.",
  "status_code": 415,
  "error_type": "unsupported_media_type"
}
```

No stack traces, file paths, exception class names, or secrets exposed.

### Malformed JSON behavior

With `Content-Type: application/json`, malformed bodies (e.g. `{"project_id":`) return HTTP **422** with `error_type: validation_error` and centralized envelope. Validation handler now sanitizes any residual `bytes` in error details to prevent secondary 500s.

### Tests added

| File | Tests |
|------|-------|
| `backend/tests/api/test_readiness_api.py` | `TestJsonContentTypeValidation` (supported types, unsupported types, missing header, envelope shape, no leakage, malformed JSON, schema validation, output unchanged, legacy regression) |
| `backend/tests/api/test_readiness_api.py` | `TestOpenApiSchemaGeneration.test_assess_openapi_documents_json_request_and_error_responses` |
| `backend/tests/api/test_content_type_dependencies.py` | Unit tests for `is_json_media_type` accept/reject cases |

All unsupported-media tests use raw `content=` bodies with explicit `Content-Type` headers — never `json={...}`.

### Content-type verification results

| Case | Status | Error envelope |
|------|--------|----------------|
| `application/json` | 200 | — |
| `application/json; charset=utf-8` | 200 | — |
| `application/vnd.api+json` | 200 | — |
| `application/problem+json` | 200 | — |
| `text/plain` | 415 | `unsupported_media_type` |
| `application/xml` | 415 | `unsupported_media_type` |
| `text/xml` | 415 | `unsupported_media_type` |
| `multipart/form-data` | 415 | `unsupported_media_type` |
| Missing `Content-Type` | 415 | `unsupported_media_type` |
| Malformed JSON | 422 | `validation_error` |
| Schema-invalid JSON | 422 | `validation_error` |

---

## Commands Executed

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\backend
python -m pytest tests/api/test_readiness_api.py -q
python -m pytest tests/e2e/test_readiness_v2_flow.py -q
python -m pytest tests -q
python -m pytest tests --collect-only
```

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
python scripts/content_type_live_validation.py
# Server stopped after validation
```

---

## Exact Test Results

| Metric | Value |
|--------|-------|
| Python version | 3.13.7 |
| Python executable | `C:\Python313\python.exe` |
| pytest version | 9.1.1 |
| Command | `python -m pytest tests -q` (from `backend/`) |
| Collected | 135 |
| Passed | 135 |
| Failed | 0 |
| Skipped | 0 |
| Warnings | 1 (Starlette `httpx` deprecation in TestClient) |

**Note:** 100 tests at initial review; 35 tests added for content-type hardening and OpenAPI regression.

---

## Live Server Validation Results

| Check | Result |
|-------|--------|
| Startup command | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8765` |
| GET `/health` | 200 |
| GET `/docs` | 200 |
| GET `/openapi.json` | 200 |
| OpenAPI assess documents 415 | Pass |
| POST assess `application/json` | 200 |
| POST assess `text/plain` | 415 |
| POST assess `application/xml` | 415 |
| POST assess malformed JSON | 422 |
| Legacy `/analyze` | 200 |
| Server shutdown | Confirmed (process stopped) |

### Sample flow result

```
project=azure_ai_migration
engineers=['kavi', 'vikram']
readiness_score=74
confidence_score=85
assessment_id=4fdffba9e7673277
policy_version=v1
```

---

## Request Validation Matrix

Tested via HTTP and TestClient:

| Case | Status | Error envelope |
|------|--------|----------------|
| One valid engineer | 200 | — |
| Multiple valid engineers | 200 | — |
| Balanced team | 200 | — |
| Missing capability team | 200 (lower score) | — |
| Weak capability team | 200 | — |
| Missing critical capability | 200 | — |
| Key person dependency | 200 | — |
| Repeated identical request | 200 (identical) | — |
| Reversed engineer order | 200 (same scores/id) | — |
| Missing `project_id` | 422 | `validation_error` |
| Null `project_id` | 422 | `validation_error` |
| Empty `project_id` | 422 | `validation_error` |
| Unknown `project_id` | 404 | `http_error` |
| Missing `engineer_ids` (defaults []) | 200 | — |
| Null `engineer_ids` | 422 | `validation_error` |
| Empty `engineer_ids` | 200 | — |
| Unknown engineer ID | 404 | `http_error` |
| Mixed valid/unknown IDs | 404 | `http_error` |
| Duplicate engineer IDs | 200 (deduped team + risk finding) | — |
| Wrong type `project_id` | 422 | `validation_error` |
| Wrong type `engineer_ids` | 422 | `validation_error` |
| Malformed JSON | 422 | `validation_error` |
| Unexpected request fields | 200 (ignored) | — |
| Whitespace-only identifiers | 404 | `http_error` |
| Large engineer array (500 dupes) | 200 | — |
| Unsupported GET on assess | 405 | — |
| Wrong content type (`text/plain`, etc.) | 415 | `unsupported_media_type` |
| Missing `Content-Type` | 415 | `unsupported_media_type` |

No Python tracebacks, file paths, or secrets observed in error responses.

---

## Contract and Determinism Findings

### Response model reuse

`ReadinessAssessResponse` inherits from domain `ReadinessAssessmentResponse` and adds only `assessment_id` and `team`. Scoring fields are not duplicated.

### Decision trace reconciliation

Readiness and confidence trace contributions sum to final scores (verified in unit, API, and live tests).

### Assessment ID behavior (after fix)

Canonical input:

```json
{
  "engineer_ids": ["kavi", "vikram"],
  "policy_version": "v1",
  "project_id": "azure_ai_migration"
}
```

- Engineer IDs sorted and deduplicated before hashing
- Policy version included
- SHA-256 digest truncated to 16 hex chars
- Order-independent
- Not time/random/process dependent

### Order independence

Confirmed: reversed `engineer_ids` produce identical readiness, confidence, assessment_id, and decision trace.

### Policy version

Default and explicit `"v1"` produce matching assessment IDs. Response and trace entries report `policy_version: "v1"`.

---

## OpenAPI Findings

| Check | Result |
|-------|--------|
| All five v2 paths present | Pass |
| HTTP methods correct | Pass |
| `ReadinessAssessResponse` includes domain + API fields | Pass |
| Assess request body consumes `application/json` | Pass |
| 415 response documented with `APIErrorResponse` | Pass |
| 422 response documented with `APIErrorResponse` | Pass |
| No duplicate error component schemas | Pass |
| Meaningful tags and summaries | Pass |
| `/docs` loads | Pass |
| Automated regression test | Pass (`TestOpenApiSchemaGeneration`) |

---

## Legacy Compatibility

| Route | Status |
|-------|--------|
| `/analyze` | Pass |
| `/project-fit` | Pass |
| `/assess-risk` | Pass |
| `/recommend-team` | Pass |
| `/generate-insight` | Pass (503 without Azure — expected) |
| `/simulate` | Pass |
| `/success-prediction` | Pass |
| `/copilot` | Pass |
| GET `/`, `/health`, `/docs` | Pass |

No regressions found after v2 gap-closure fixes.

---

## API Versioning Decision

Documented in `architecture/api-versioning.md`:

- Legacy routes remain unversioned
- Production intelligence uses `/api/v2`
- Future simulation/persistence endpoints extend `/api/v2`
- No `/api/v1` alias introduced

---

## Gaps Discovered and Fixes Implemented

| Gap | Fix | Files |
|-----|-----|-------|
| Non-canonical assessment ID | JSON canonical fingerprint with policy version + unique sorted IDs | `readiness_orchestrator.py` |
| Duplicate team in response | Deduplicate before response serialization | `readiness_orchestrator.py` |
| Missing order/ID tests | Added API tests | `test_readiness_api.py` |
| Missing e2e file | Created catalog-driven flow tests | `tests/e2e/test_readiness_v2_flow.py` |
| Missing versioning doc | Created strategy document | `architecture/api-versioning.md` |
| Wrong content type returns 500 | API-layer dependency + 415 envelope + OpenAPI | `dependencies.py`, `exceptions.py`, `openapi.py`, `readiness.py` |

---

## Unresolved Risks

| Priority | Risk |
|----------|------|
| P0 | None blocking next phase |
| P1 | Repo-root import still requires `cd backend` or `PYTHONPATH=backend` |
| P1 | Render dashboard config may not match `render.yaml` (pre-existing) |
| P2 | Extra request fields silently ignored (consistent with legacy, not strict) |
| P2 | Docker validation deferred (per instructions) |
| P2 | Legacy services still import private helpers (`_score_fit`, etc.) |
| P2 | Other v2 POST endpoints do not yet attach `require_json_content_type` (none exist today) |

---

## Deferred Items

- Docker end-to-end validation (Windows infrastructure — explicitly deferred)
- Team Simulation Engine (next phase — not in scope)
- Frontend wiring to `/api/v2`
- Strict `extra="forbid"` on request models (would require app-wide convention change)

---

## Readiness Decision for Next Phase

**Ready for Team Simulation Engine implementation.**

The production readiness API layer is verified end-to-end, deterministic, architecturally clean, legacy-compatible, and documented. Recommended next work: `/api/v2/simulations/*` under the same namespace per `architecture/api-versioning.md`.

---

*End of readiness API validation report.*
