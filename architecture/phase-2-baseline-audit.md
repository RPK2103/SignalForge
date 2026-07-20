# SignalForge Phase 2 Baseline Audit

**Audit date:** 2026-07-19  
**Auditor role:** Senior Python/FastAPI engineer, Next.js architect, production-readiness reviewer  
**Scope:** Read-only repository inspection and validation. No product functionality was modified.

---

## Executive Summary

SignalForge is a demo-ready hackathon MVP with a **modular FastAPI backend**, a **static HTML/JS executive dashboard** mounted at `/dashboard`, and a **separate Next.js frontend** that currently renders **hardcoded mock data only** (no backend integration). Azure OpenAI powers two AI surfaces: `/generate-insight` (strict — returns HTTP 503 without config) and `/copilot` (graceful — falls back to deterministic text).

At audit time (2026-07-19), the live Render deployment (`https://signalforge-o0m4.onrender.com`) responded **HTTP 200** on GET routes `/`, `/health`, `/dashboard/`, and `/docs`. Those GET routes were **independently re-verified on 2026-07-20** (all **HTTP 200**). Time-stamped POST probes on **2026-07-19** also returned **HTTP 200** for `/generate-insight` and `/copilot`; current Azure OpenAI availability is **not inferable from the repository** and remains an **external platform setting** until Render environment variables are inspected. Intermittent or endpoint-specific **HTTP 503** remains a plausible production issue driven by missing Azure env vars, Render free-tier cold starts, or incorrect start-directory configuration — not by current full-service outage.

**Critical gaps for Phase 2:**

| Area | Status |
|------|--------|
| Backend API surface | Existing MVP surface inventoried (8 intelligence POST endpoints + 2 application GET endpoints: `/` and `/health`) |
| Static dashboard ↔ API | Partial (3 of 8 endpoints used) |
| Next.js frontend ↔ API | Not connected |
| Automated tests | None |
| CI/CD / deployment IaC | None in repository |
| Repository hygiene | Committed `__pycache__/*.pyc`, duplicate dashboard trees |

**Validation summary:**

| Check | Result |
|-------|--------|
| Backend import (`backend/`) | **PASS** |
| Backend import (repo root, no `PYTHONPATH`) | **FAIL** — `ModuleNotFoundError: No module named 'app'` |
| Backend tests (`pytest`) | **FAIL** — `No module named pytest`; no test files |
| Frontend `npm ci` | **PASS** |
| Frontend `npm run lint` | **PASS** |
| Frontend `npx tsc --noEmit` | **PASS** |
| Frontend `npm run build` | **PASS** |

### Phase 2 UI Decision (2026-07-20)

| Surface | Phase 2 role |
|---------|----------------|
| Next.js `frontend/` | **Primary** Phase 2 product interface |
| `backend/dashboard/` | **Legacy compatibility surface** (served at `/dashboard` on Render until Next.js reaches parity) |
| Root `dashboard/` | **Duplicate** — remove after verification |
| Static dashboard deprecation | Deprecate `backend/dashboard/` **only after** Next.js reaches API and demo-flow parity |

---

## Repository Map

```
SignalForge/
├── AGENTS.md                          # Agent/project rules (MVP constraints)
├── README.md                          # Primary docs; local run + Render URLs
├── .gitignore                         # Ignores .env, __pycache__ (partially effective)
├── .cursorignore                      # Cursor indexing exclusions
├── architecture/
│   ├── mvp-scope.md                   # MVP boundaries
│   ├── system-design.md               # High-level design (partially stale vs code)
│   └── phase-2-baseline-audit.md      # This document
├── assets/                            # README/marketing screenshots
├── backend/
│   ├── requirements.txt               # Pinned Python deps (FastAPI, OpenAI, uvicorn)
│   ├── app/
│   │   ├── main.py                    # FastAPI app, CORS, dashboard mount, routers
│   │   ├── core/config.py             # Settings + load_dotenv()
│   │   ├── data/mock_catalog.py       # Single demo project + 3 engineers
│   │   ├── routes/                    # 8 active routers + 1 empty stub (analysis.py)
│   │   ├── schemas/                   # Pydantic v2 models (+ 1 empty stub)
│   │   └── services/                  # Deterministic engines + AI wrappers
│   └── dashboard/                     # **Served** static dashboard (mounted in main.py)
├── dashboard/                         # **Duplicate** of backend/dashboard (NOT mounted)
├── frontend/                          # Next.js 16 + shadcn/ui (static demo data)
├── prompts/cursor-prompts.md          # Empty placeholder
├── sample-data/engineer_profile.json  # Sample input (not wired to API)
└── (no .github/workflows, render.yaml, Procfile, or Dockerfile)
```

**Tracked file count:** 113 tracked paths were observed during independent verification on 2026-07-20, including four tracked `.pyc` files under `backend/app/**/__pycache__/`. (The original audit on 2026-07-19 recorded 108 paths — a point-in-time observation.)

---

## Existing API Inventory

All POST routes are registered at the **application root** (no `/api` prefix). Routers have **no path prefix**.

### Health & Static

| Method | Path | Request Model | Response Model | Service | Error Handling | Frontend Usage |
|--------|------|---------------|----------------|---------|----------------|----------------|
| GET | `/` | — | `{"message": "..."}` | inline handler | none | none |
| GET | `/health` | — | `{"status": "healthy"}` | inline handler | none | none |
| GET | `/dashboard/*` | — | static HTML/CSS/JS | `StaticFiles` mount | Starlette static 404 if missing | Legacy static dashboard (compatibility surface) |
| GET | `/docs`, `/redoc`, `/openapi.json` | — | OpenAPI UI/schema | FastAPI auto | — | none |

### Intelligence Endpoints

| Method | Path | Request Model | Response Model | Service | Error Handling | Frontend Usage |
|--------|------|---------------|----------------|---------|----------------|----------------|
| POST | `/analyze` | `EngineerProfile` | `EngineerAnalysis` | `analyzer.analyze_engineer` | Pydantic 422 on validation | none (Next.js uses static demo data) |
| POST | `/project-fit` | `ProjectFitRequest` | `ProjectFitResult` | `fit_recommender.recommend_project_fit` | Pydantic 422 | none |
| POST | `/assess-risk` | `RiskAssessmentRequest` | `RiskAssessmentResponse` | `risk_assessor.assess_risk` | Pydantic 422 | none |
| POST | `/recommend-team` | `TeamRecommendationRequest` | `TeamRecommendationResponse` | `team_recommender.recommend_team` | Pydantic 422 | none |
| POST | `/generate-insight` | `InsightRequest` | `InsightResponse` | `insight_generator.generate_insight` | **503** if Azure not configured; **502** on OpenAI failure/empty | none (static dashboard does not call this) |
| POST | `/simulate` | `SimulateRequest` | `SimulateResponse` | `simulator.simulate_staffing` | **404** unknown project; **400** empty/unknown/not-on-team engineers | **Static dashboard** (`backend/dashboard/app.js`) |
| POST | `/success-prediction` | `SuccessPredictionRequest` | `SuccessPredictionResponse` | `predictor.predict_success` | **404** unknown project | **Static dashboard** |
| POST | `/copilot` | `CopilotRequest` | `CopilotResponse` | `copilot.answer_copilot_question` | **400** empty question; **404** unknown project; AI errors → contextual fallback (200) | **Static dashboard** |

### Stub / Unregistered

| File | Status |
|------|--------|
| `backend/app/routes/analysis.py` | Empty — **not included** in `main.py` |
| `backend/app/schemas/analysis.py` | Empty |

### Static Dashboard API Calls

`backend/dashboard/app.js` uses `API_BASE = window.location.origin` and calls:

- `POST /success-prediction` — `{ project_name: "Azure AI Migration" }`
- `POST /simulate` — `{ project_name, remove_engineers: ["Kavi"] }`
- `POST /copilot` — `{ project_name, question }`

Failed requests fall back to hardcoded `FALLBACK` constants in `app.js`.

---

## Backend Architecture Assessment

### Structure

Clean layered layout: **routes → services → schemas**, with shared mock data in `app/data/mock_catalog.py`. Deterministic scoring engines are independent; AI services (`insight_generator`, `copilot`) sit on top via `ai_service.py`.

### Configuration (`app/core/config.py`)

- Uses `python-dotenv` `load_dotenv()` at import time — **does not fail** if `.env` is absent.
- Settings: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`.
- `azure_openai_configured()` gates AI behavior.
- README also documents `AZURE_OPENAI_API_VERSION` and `OPENAI_API_KEY` — **neither is read by code**. API version is hardcoded to `2024-10-21` in `ai_service.py`.

### Static Path Resolution

```python
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
```

This resolves to `backend/dashboard/` via `__file__`. It is **not fragile to process working directory**. The duplicate `SignalForge/dashboard/` at repo root is **dead code** for the running API.

### Import / CWD Dependency

- Application module path is `app.*`.
- **Must run from `backend/`** (or set `PYTHONPATH=backend`).
- README command `uvicorn app.main:app --reload` assumes `cd backend` first.
- Running uvicorn from repo root without `PYTHONPATH` → **`ModuleNotFoundError: No module named 'app'`** (verified).

### CORS

Permissive: `allow_origins=["*"]` — acceptable for MVP demo, not production-ready.

### Mock Data

Single project (`Azure AI Migration`) and three engineers (`Kavi`, `Vikram`, `Arjun`) in `mock_catalog.py`. Endpoints `/success-prediction`, `/simulate`, and `/copilot` resolve projects by name against this catalog.

---

## Frontend Architecture Assessment

### Stack

- Next.js **16.2.7**, React 19, TypeScript (strict), Tailwind 4, shadcn/ui components.
- `axios` is in `package.json` but **unused** in `src/`.
- No `NEXT_PUBLIC_*` API URL configuration.

### Current Behavior

`frontend/src/app/page.tsx` composes dashboard cards fed entirely from `frontend/src/lib/demo-data.ts`. No `fetch`, no server actions, no API routes.

### Scripts

| Script | Command | Notes |
|--------|---------|-------|
| Dev | `npm run dev` → `next dev` | Default port 3000 |
| Build | `npm run build` | Turbopack; static `/` page |
| Start | `npm run start` | Production server |
| Lint | `npm run lint` → `eslint` | No dedicated `typecheck` script; use `npx tsc --noEmit` |
| TypeScript | `npx tsc --noEmit` | Not in package.json scripts |

### Deployment Gap

Next.js frontend is **not deployed** alongside the Render backend documented in README. Two parallel UIs exist today:

1. **Render production (legacy):** static dashboard at `/dashboard/`
2. **Phase 2 primary (local):** Next.js `frontend/` — static mock UI, not yet wired to APIs

**Phase 2 decision:** Next.js `frontend/` is the primary product interface. `backend/dashboard/` remains temporarily as a legacy compatibility surface on Render until Next.js reaches API and demo-flow parity.

### Build Output

```
Route (app)
┌ ○ /
└ ○ /_not-found
○  (Static)  prerendered as static content
```

---

## AI Integration Assessment

### Azure OpenAI Client (`app/services/ai_service.py`)

- Lazy client via `@lru_cache` — instantiated on first AI call, not at import.
- Model ID = `AZURE_OPENAI_DEPLOYMENT` env var.
- Fixed API version: `2024-10-21`.

### `/generate-insight` — Strict

Returns **HTTP 503** when Azure env vars are missing:

```text
Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT,
AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT.
```

Returns **502** on OpenAI exceptions or empty responses.

### `/copilot` — Resilient

- Builds rich JSON context from deterministic engines (+ optional staffing simulation).
- If Azure unavailable or call fails → returns **200** with `_build_contextual_fallback()` text.
- Validates question (400) and project name (404).

### Live Verification

#### GET routes — re-verified 2026-07-20

| Endpoint | HTTP Status | Notes |
|----------|-------------|-------|
| `/` | 200 | Independently re-verified |
| `/health` | 200 | Independently re-verified |
| `/dashboard/` | 200 | Independently re-verified |
| `/docs` | 200 | Independently re-verified |

#### AI POST routes — time-stamped observation (2026-07-19)

| Endpoint | HTTP Status | Notes |
|----------|-------------|-------|
| `/generate-insight` | 200 | Time-stamped audit observation; implied Azure configured on Render at that time |
| `/copilot` | 200 | Time-stamped audit observation; AI answer returned |

**External configuration note:** Whether Azure OpenAI is currently configured on Render cannot be confirmed from the repository. Inspect Render environment variables (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`) to verify. AI POST probes were **not re-run** during independent verification on 2026-07-20.

---

## Data and Persistence Assessment

| Aspect | Finding |
|--------|---------|
| Database | None |
| Persistence | In-memory mock catalog only |
| External data | `sample-data/engineer_profile.json` — reference sample, not loaded by backend |
| State | Stateless per request |
| Catalog extensibility | Add entries to `MOCK_PROJECTS` / `MOCK_ENGINEERS` |

---

## Testing Assessment

| Item | Finding |
|------|---------|
| Unit tests | **None** |
| Integration tests | **None** |
| Test framework | Not in `requirements.txt` |
| `python -m pytest` | **FAIL** — `No module named pytest` |
| Frontend tests | **None** |
| CI validation | **No GitHub workflows** |

---

## Deployment Diagnosis

### Documented Local Commands

| Component | Command | Working Directory |
|-----------|---------|-------------------|
| Backend | `uvicorn app.main:app --reload` | **`backend/`** (required) |
| Frontend | `npm run dev` | `frontend/` |

### Render Start Command (Repository Inference)

**No `render.yaml`, Procfile, or workflow defines deployment.** From README and module layout, the expected Render start command is:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Alternative if root directory is set to `backend/` in Render dashboard:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**Blocking question:** Exact Render service configuration (root directory, start command, env vars) is **not in the repository** — only inferable from README and live behavior.

### Live Deployment Probe (2026-07-19)

```text
curl https://signalforge-o0m4.onrender.com/health        → 200
curl https://signalforge-o0m4.onrender.com/              → 200
curl https://signalforge-o0m4.onrender.com/dashboard/    → 200
curl https://signalforge-o0m4.onrender.com/docs          → 200
```

Service was **healthy at audit time**; prior 503 reports may have been transient.

### Deployment Root-Cause Hypotheses (503) — Ranked by Confidence

| Rank | Hypothesis | Confidence | Evidence |
|------|------------|------------|----------|
| 1 | **Render free-tier cold start / service spin-down** | **High** | Render URL; no health-check keepalive in repo; first request after idle commonly returns 503/502 until process boots |
| 2 | **`POST /generate-insight` without Azure env vars** | **High** | Explicit `HTTPException(status_code=503)` in `insight_generator.py`; only endpoint that intentionally returns 503 |
| 3 | **Wrong Render root directory / start command** (uvicorn from repo root) | **Medium** | Import fails without `backend/` on path; would prevent process start entirely |
| 4 | **Missing `backend/dashboard/` on deploy artifact** | **Low–Medium** | Would crash at `StaticFiles` mount if directory absent; current deploy serves dashboard OK |
| 5 | **Azure OpenAI quota/rate errors misread as outage** | **Low** | `/generate-insight` maps to 502, not 503; `/copilot` degrades to 200 fallback |

### Static Path Fragility

| Path mechanism | Fragile? | Notes |
|----------------|----------|-------|
| `Path(__file__).resolve().parent.parent / "dashboard"` | **No** | Absolute from source file |
| `dashboard/` at repo root | N/A | Not referenced by FastAPI |
| `API_BASE = window.location.origin` in `app.js` | **No** | Correct for same-origin deploy |

---

## Security / Configuration Findings

| Finding | Severity | Detail |
|---------|----------|--------|
| CORS `allow_origins=["*"]` | P2 | Acceptable for demo; tighten for production |
| No authentication | Expected (MVP) | Per AGENTS.md |
| Secrets in env vars | Good pattern | `.env` gitignored |
| README lists unused `OPENAI_API_KEY` | P2 | Documentation drift |
| Committed `.pyc` files | P1 | Hygiene; `.gitignore` rule not retroactive |
| Permissive AI fallback exposes deterministic data | P2 | Copilot still returns 200 with internal context summaries |
| No rate limiting on AI endpoints | P2 | Cost/abuse risk if public |

---

## Generated-File and Repository-Hygiene Findings

### Committed Generated / Accidental Files

```
backend/app/__pycache__/main.cpython-313.pyc
backend/app/core/__pycache__/config.cpython-313.pyc
backend/app/data/__pycache__/__init__.cpython-313.pyc
backend/app/data/__pycache__/mock_catalog.cpython-313.pyc
```

`.gitignore` lists `__pycache__/` and `*.pyc` but these were committed before ignore or via force-add.

### Duplicate Trees

| Path | Issue |
|------|-------|
| `dashboard/` vs `backend/dashboard/` | Identical content (Compare-Object found no differences in `app.js`); only `backend/dashboard/` is served |
| Empty stubs | `routes/analysis.py`, `schemas/analysis.py`, `prompts/cursor-prompts.md`, `data/__init__.py` |

### Missing Expected Artifacts

- `.github/workflows/*`
- `render.yaml` / `Procfile`
- `backend/tests/`
- `frontend/next-env.d.ts` (gitignored — regenerated on build)

---

## P0 / P1 / P2 Risks

### P0 — Blocks reliable Phase 2 delivery

| ID | Risk |
|----|------|
| P0-1 | **Dual UI divergence** — Next.js frontend and static dashboard show different architectures; **resolved:** Next.js `frontend/` is the Phase 2 primary interface; static dashboard is legacy until parity |
| P0-2 | **No deployment IaC in repo** — Render config not reproducible from source |
| P0-3 | **Zero automated tests** — regressions undetectable |

### P1 — Should address early in Phase 2

| ID | Risk |
|----|------|
| P1-1 | Next.js not connected to backend APIs |
| P1-2 | Duplicate `dashboard/` directory causes edit drift |
| P1-3 | Committed `__pycache__` / `.pyc` files |
| P1-4 | Inconsistent AI failure modes (503 vs silent fallback) |
| P1-5 | `system-design.md` and README structure outdated vs actual repo |

### P2 — Improve before production

| ID | Risk |
|----|------|
| P2-1 | Wide-open CORS |
| P2-2 | No CI lint/test/build pipeline |
| P2-3 | Unused `axios` dependency |
| P2-4 | Hardcoded Azure API version |
| P2-5 | Empty stub files (`analysis`, `cursor-prompts`) |
| P2-6 | npm audit: 4 vulnerabilities (2 moderate, 2 high) on `npm ci` |

---

## Recommended Implementation Sequence

1. **Freeze baseline** — preserve this audit; add `render.yaml` or document Render settings in repo.
2. **Repository hygiene** — remove committed `.pyc`; delete or symlink duplicate `dashboard/`; remove empty stubs or implement them.
3. **Wire primary UI to APIs** — Next.js `frontend/` is the Phase 2 product interface; connect it to backend APIs and reach demo-flow parity before deprecating `backend/dashboard/`.
4. **API client layer** — shared typed client + env-based `API_BASE` for frontend.
5. **Unify AI error policy** — consistent degradation for insight + copilot.
6. **Add minimal tests** — service unit tests for scoring engines; smoke test for `/health` and `/simulate`.
7. **CI workflow** — backend import check, pytest, frontend lint/tsc/build.
8. **Deployment hardening** — explicit start command, health check path, env var validation at startup (log-only).
9. **Expand mock catalog** — only after above stabilizes.

---

## Exact Commands Executed and Results

### Backend

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\backend
python -c "from app.main import app; print('import_ok', app.title)"
```
**Result:** PASS — `import_ok SignalForge API`

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge
python -c "from app.main import app"
```
**Result:** FAIL — `ModuleNotFoundError: No module named 'app'`

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\backend
python -m pytest
```
**Result:** FAIL — `No module named pytest`

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\backend
python -c "import uvicorn; from app.main import app; print('uvicorn_import_ok')"
```
**Result:** PASS — `uvicorn_import_ok`

### Frontend

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\frontend
npm ci
```
**Result:** PASS — 735 packages installed; 4 npm audit vulnerabilities reported

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\frontend
npm run lint
```
**Result:** PASS — ESLint completed with exit code 0

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\frontend
npx tsc --noEmit
```
**Result:** PASS — exit code 0

```powershell
cd C:\Users\Kaviyashre\projects\SignalForge\frontend
npm run build
```
**Result:** PASS — Next.js 16.2.7 production build succeeded

### Live Deployment Probes

#### GET routes — original audit (2026-07-19) and independent re-verification (2026-07-20)

```powershell
curl -s -o NUL -w "health: %{http_code}\n" https://signalforge-o0m4.onrender.com/health
curl -s -o NUL -w "root: %{http_code}\n" https://signalforge-o0m4.onrender.com/
curl -s -o NUL -w "dashboard: %{http_code}\n" https://signalforge-o0m4.onrender.com/dashboard/
curl -s -o NUL -w "docs: %{http_code}\n" https://signalforge-o0m4.onrender.com/docs
```
**Result (2026-07-19):** PASS — all returned **200**  
**Result (2026-07-20, independent re-verification):** PASS — all returned **200**

#### AI POST routes — time-stamped observation (2026-07-19 only)

```powershell
curl -s -w "`nstatus: %{http_code}`n" -X POST "https://signalforge-o0m4.onrender.com/generate-insight" ^
  -H "Content-Type: application/json" ^
  -d "{\"engineer_name\":\"Kavi\",\"project_name\":\"Azure AI Migration\",\"fit_score\":100,\"risk_level\":\"Low\",\"team_coverage\":[\"Azure\",\"Python\",\"Generative AI\"]}"
```
**Result (2026-07-19):** PASS — **200** with AI insight JSON body (time-stamped observation; not re-run on 2026-07-20)

```powershell
curl -s -w "`nstatus: %{http_code}`n" -X POST "https://signalforge-o0m4.onrender.com/copilot" ^
  -H "Content-Type: application/json" ^
  -d "{\"project_name\":\"Azure AI Migration\",\"question\":\"Why is this project likely to succeed?\"}"
```
**Result (2026-07-19):** PASS — **200** with copilot answer JSON body (time-stamped observation; not re-run on 2026-07-20)

**External configuration note:** Current Azure OpenAI configuration on Render remains an external platform setting until environment variables are inspected.

---

## Files That Should Be Preserved

| Path | Reason |
|------|--------|
| `backend/app/main.py` | Application entry, routing, static mount |
| `backend/app/routes/*.py` (except empty `analysis.py`) | API contract |
| `backend/app/schemas/*.py` (except empty `analysis.py`) | Pydantic contracts |
| `backend/app/services/*.py` | Core intelligence logic |
| `backend/app/data/mock_catalog.py` | Demo data source |
| `backend/app/core/config.py` | Configuration pattern |
| `backend/dashboard/*` | Legacy compatibility dashboard (served at `/dashboard` until Next.js parity) |
| `backend/requirements.txt` | Dependency lock |
| `frontend/src/**` | Next.js UI foundation |
| `frontend/package.json`, `tsconfig.json`, `next.config.ts` | Frontend toolchain |
| `architecture/*.md` | Design history |
| `AGENTS.md` | Project constraints |
| `sample-data/engineer_profile.json` | Reference fixture |
| `assets/**` | Demo/marketing visuals |

---

## Files That Should Be Refactored

| Path | Refactor Need |
|------|---------------|
| `README.md` | Update repo tree, document dual UI, fix env var list, add Render start command |
| `architecture/system-design.md` | Align with implemented features (simulator, copilot, predictor) |
| `backend/app/services/fit_recommender.py`, `risk_assessor.py`, `team_recommender.py` | Deduplicate `_has_skill` / matching helpers |
| `backend/app/core/config.py` | Centralize API version; optional startup env validation logging |
| `frontend/src/lib/demo-data.ts` | Replace with API-driven data or shared OpenAPI types |
| `frontend/package.json` | Add `typecheck` script; remove unused `axios` or use it |
| `.gitignore` | Ensure root-level `__pycache__` coverage; consider `frontend/.next` at root |

---

## Files That Should Eventually Be Deprecated

| Path | Reason |
|------|--------|
| `dashboard/` (repo root) | Duplicate of `backend/dashboard/`; not served by API — remove after verification |
| `backend/dashboard/` | Deprecate after Next.js `frontend/` reaches API and demo-flow parity |
| `backend/app/routes/analysis.py` | Empty stub, not registered |
| `backend/app/schemas/analysis.py` | Empty stub |
| `prompts/cursor-prompts.md` | Empty placeholder |
| Committed `**/__pycache__/*.pyc` | Remove from git history / stop tracking |

---

## Blocking Questions

Only items **not answerable from the repository**:

1. **What exact Render service settings are configured?** (root directory, start command, instance type, env vars) — required to reproduce deployment, confirm Azure OpenAI configuration, and explain historical 503 incidents definitively.

**Resolved (2026-07-20):** Next.js `frontend/` is the Phase 2 primary product interface. `backend/dashboard/` is a legacy compatibility surface until Next.js reaches API and demo-flow parity. Root `dashboard/` is a duplicate to remove after verification.

---

*End of Phase 2 baseline audit.*
