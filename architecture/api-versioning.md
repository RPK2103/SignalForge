# SignalForge API Versioning Strategy

**Status:** Adopted for Phase 2 production intelligence layer
**Last reviewed:** 2026-07-22

---

## Summary

SignalForge uses **two API namespaces**:

| Namespace | Purpose | Stability |
|-----------|---------|-----------|
| Unversioned legacy routes | Hackathon MVP intelligence endpoints | Frozen contracts — adapters preserve behavior |
| `/api/v2` | Production readiness intelligence platform | Versioned, documented, test-covered |

The production intelligence layer intentionally uses **`/api/v2`**, not `/api/v1`, because `/api/v2` is already the established production namespace for the deterministic readiness domain. Future capabilities (simulation, persistence, review, leadership brief) should extend `/api/v2` rather than introducing a conflicting `/api/v1`.

---

## Legacy Unversioned API

These routes remain registered at the application root with **no version prefix**:

| Method | Path |
|--------|------|
| GET | `/`, `/health`, `/dashboard/*`, `/docs`, `/redoc`, `/openapi.json` |
| POST | `/analyze`, `/project-fit`, `/assess-risk`, `/recommend-team`, `/generate-insight`, `/simulate`, `/success-prediction`, `/copilot` |

### Compatibility policy

- Request and response shapes are **frozen** unless a deliberate breaking change is approved.
- Legacy routes continue to use deterministic adapters where Phase 2 domain logic applies.
- AI endpoints (`/generate-insight`, `/copilot`) retain their existing failure/degradation behavior.
- No new domain fields are exposed on legacy responses without an explicit migration.

### Deprecation policy

- Legacy routes are **not deprecated** while the static dashboard and external demos depend on them.
- When the Next.js frontend reaches parity, legacy routes may be marked deprecated in OpenAPI summaries before removal.
- Removal requires a documented migration path to `/api/v2` equivalents.

---

## Production API Namespace (`/api/v2`)

Centralized registration:

```
backend/app/api/v2/router.py  →  prefix="/api/v2"
backend/app/main.py           →  app.include_router(api_v2_router)
```

### Current surface

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v2/readiness/assess` | Full deterministic readiness assessment |
| POST | `/api/v2/simulations` | Deterministic team composition simulation |
| GET | `/api/v2/capabilities` | Canonical capability registry |
| GET | `/api/v2/policies/readiness` | Active scoring policy metadata |
| GET | `/api/v2/engineers` | Domain engineer catalog |
| GET | `/api/v2/projects` | Domain project catalog |
| POST | `/api/v2/assessments` | Compute + persist readiness assessment (SQL catalog) |
| GET | `/api/v2/assessments` | Paginated assessment history |
| GET | `/api/v2/assessments/{assessment_record_id}` | Stored assessment snapshot + reviews |
| POST | `/api/v2/assessments/{assessment_record_id}/reviews` | Append human review |
| POST | `/api/v2/assessments/{assessment_record_id}/leadership-brief` | Generate grounded leadership brief (no request body) |
| GET | `/api/v2/assessments/{assessment_record_id}/leadership-briefs` | Append-only leadership brief history |
| POST | `/api/v2/simulation-records` | Compute + persist simulation (SQL catalog) |
| GET | `/api/v2/simulation-records` | Paginated simulation history |
| GET | `/api/v2/simulation-records/{simulation_record_id}` | Stored simulation snapshots |

Compute-only routes (`POST /api/v2/readiness/assess`, `POST /api/v2/simulations`) remain unchanged and use the in-memory mock catalog. Persistence routes require `DATABASE_URL`, migrated schema, and seeded catalog data. See `architecture/persistence-and-audit.md`.

### Implemented extensions (Phase 2 Prompt 6)

| Area | Path |
|------|------|
| Leadership brief generation | `POST /api/v2/assessments/{assessment_record_id}/leadership-brief` |
| Leadership brief history | `GET /api/v2/assessments/{assessment_record_id}/leadership-briefs` |

See `architecture/ai-reasoning-boundary.md`.

### Future endpoints (planned, same namespace)

All future production features should remain under `/api/v2` to avoid namespace fragmentation.

---

## Version Prefix Centralization

- The `/api/v2` prefix is defined **once** in `backend/app/api/v2/router.py`.
- Sub-routers (`readiness`, `capabilities`, `catalog`) add resource segments only.
- Legacy routers in `backend/app/routes/` have **no prefix** by design.

---

## Route Aliases

**No aliases are required today.** There are no external consumers requesting alternate paths for the v2 surface. If a consumer later requires an alias, add it as an explicit duplicate route with identical handler wiring — do not silently rename existing paths.

---

## OpenAPI and Documentation

- Legacy and v2 routes appear together in `/openapi.json` and `/docs`.
- v2 routes use dedicated tags: `Readiness Intelligence`, `Capability Catalog`, `Intelligence Catalog`, `Assessment History`, `Simulation History`.
- Policy versioning (`policy_version` request field, `policy_version` response field) is separate from URL versioning.
- **JSON request bodies:** v2 POST endpoints that accept structured payloads require `Content-Type: application/json` or a valid structured JSON media type (`application/*+json`). Unsupported media types return HTTP 415 with the centralized `APIErrorResponse` envelope (`error_type: unsupported_media_type`). Legacy unversioned POST routes retain their existing content-type behavior.

---

## Decision Record

| Decision | Rationale |
|----------|-----------|
| Keep `/api/v2` as production namespace | Already implemented and tested; avoids churn |
| Do not introduce `/api/v1` for newer features | Would contradict established namespace and confuse consumers |
| Keep legacy routes unversioned | Preserves Render dashboard and demo compatibility |
| Centralize prefix in one router module | Prevents drift across route files |

---

*End of API versioning strategy.*
