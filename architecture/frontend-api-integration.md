# SignalForge Frontend API Integration

## 1. Executive summary

The Next.js dashboard connects to SignalForge `/api/v2` endpoints through a centralized typed API client. Production runtime no longer uses hardcoded assessment, catalog, or Leadership Brief data. The existing visual identity and page structure are preserved while adding history, simulation, review, and brief flows with explicit loading, empty, error, and retry states.

## 2. Scope and non-goals

**In scope**

- Catalog, readiness, persistence, simulation, review, and Leadership Brief integration
- Typed contracts aligned with backend Pydantic models
- Request cancellation and stale-response protection
- Accessible forms and state presentation

**Non-goals**

- Authentication and authorization
- Frontend scoring or simulation delta calculation
- Custom AI prompts or provider selection
- Public deployment validation
- Visual redesign

## 3. Frontend architecture

```
Page (server)
  └── DashboardContainer (client)
        ├── CatalogSelector / AssessmentActions
        ├── Presentational dashboard cards (props only)
        ├── History / Simulation / Leadership Brief tabs
        └── Typed services → api/client → /api/v2
```

## 4. API client structure

- `src/lib/api/config.ts` — base URL normalization
- `src/lib/api/errors.ts` — error envelope parsing and categories
- `src/lib/api/client.ts` — GET, JSON POST, no-body POST
- `src/lib/api/contracts/*` — TypeScript contracts
- `src/lib/api/services/*` — feature-oriented service wrappers

## 5. Environment configuration

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL` | Public backend origin (no secrets) |

Development defaults to `http://127.0.0.1:8000` when unset. Production requires explicit configuration.

## 6. Server/client component boundaries

- `src/app/page.tsx` — server shell
- `src/features/dashboard/dashboard-container.tsx` — client orchestration
- Dashboard cards remain mostly server-compatible presentational components receiving typed props

## 7. Contract types

Contracts mirror backend models in `backend/app/schemas/api_v2.py`, `backend/app/domain/*`, and persistence DTOs. Simulation operations use discriminated unions on `type`.

## 8–15. Flows

All flows call `/api/v2` only:

- **Catalog** — projects, engineers, capabilities, readiness policies
- **Readiness preview** — `POST /api/v2/readiness/assess`
- **Persisted assessment** — `POST /api/v2/assessments`
- **History/detail** — list and get persisted records (no recompute)
- **Reviews** — `POST .../reviews` with state-specific validation
- **Simulation preview** — `POST /api/v2/simulations`
- **Persisted simulation** — `POST /api/v2/simulation-records`
- **Leadership Brief** — no-body POST and list endpoints on persisted assessments only

## 16. Provider/fallback presentation

- Azure mode: “AI-generated from deterministic SignalForge evidence”
- Fallback mode: “Deterministic fallback brief” plus safe failure category label
- Advisory disclaimer: brief wording does not change deterministic scores

## 17. Error model

Client preserves backend `error_type` and safe `detail`. User-facing messages avoid stack traces, SQL, and internal paths.

## 18. Loading and empty states

Shared components in `src/components/ui/async-state.tsx` provide loading, empty, and error UI with retry actions.

## 19–20. Request cancellation and race conditions

- `AbortController` on catalog load and API client requests
- Monotonic request IDs in `useAsyncRequest` prevent stale overwrites

## 21. Accessibility

- Labeled selects and checkbox groups
- `aria-live` loading/status regions
- Dialog focus management via shadcn Dialog
- Delta text includes sign and labels, not color alone

## 22. Responsive behavior

Existing Tailwind grid layouts retained; tables scroll horizontally on small screens.

## 23. Testing

Vitest covers API client behavior, stale-request hook behavior, review validation, and empty executive summary state. No live Azure calls in tests.

## 24. Local development

1. Start backend (`uvicorn`, migrations applied, seed data loaded)
2. Set `NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL=http://127.0.0.1:8000`
3. Run `npm run dev` in `frontend/`

## 25. CORS configuration

Backend already allows local Next.js origins via `CORS_ORIGINS` with safe dev defaults in `backend/app/core/config.py`. No frontend-specific backend changes were required.

## 26. Security considerations

- No secrets in frontend bundle
- No `localStorage` snapshot persistence
- React text escaping for all API strings
- No `dangerouslySetInnerHTML`

## 27. Known limitations

- Browser E2E (Playwright) not configured in repository
- Manual live validation required for full cross-service browser flow
- Live Azure generation not validated in automated tests (`AI_ENABLED=false` expected)

## 28–29. Deferred work

- Design-system expansion
- Authentication/authorization
- OpenAPI type generation pipeline

## 30. Deferred public deployment validation

No claim of production deployment validation is made by this integration phase.
