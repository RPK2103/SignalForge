# SignalForge — Demo Scripts

_Two scripts: a 3-minute business demo and a 10-minute technical walkthrough.
Both lead with the business decision, not the technology stack._

Prerequisites (local): backend running on a migrated + seeded SQLite DB with
`AI_ENABLED=false`, frontend production build started, frontend API base URL
pointing at the backend. (See root `README.md` → Local setup.)

---

## Three-Minute Demo Script

**Framing (say this first):**
> "The question every engineering leader asks is: _can this team actually deliver
> this initiative?_ SignalForge answers that with an explainable readiness
> decision — and lets you simulate changes before you make them."

1. **Project / team selection** — Open the dashboard; pick a seeded project and a
   baseline team. _"Projects and engineers load from the catalog."_
2. **Readiness and confidence — separately** — Point at both scores.
   _"Readiness is can-they-deliver; confidence is how-sure-we-are. They're
   different, and we never conflate them."_ (Demo values: readiness 74,
   confidence 85/high.)
3. **Gaps and ownership concentration** — Show skill gaps and key-person risk.
   _"Here's where coverage is thin and where one person is a single point of
   failure."_
4. **Decision trace** — Open the trace. _"Every score is explainable — no black
   box."_
5. **Remove-engineer simulation** — Remove the key engineer.
6. **Changed outcome** — Show the readiness delta (demo: **-51**).
   _"Losing this person drops readiness sharply — now you can see it before it
   happens."_
7. **Persisted assessment** — Save; show it's an immutable snapshot.
8. **Human review** — Add an "accepted" review. _"Leaders can record judgment —
   and it never rewrites the deterministic scores."_
9. **Grounded Leadership Brief** — Generate the brief.
10. **AI fallback provenance** — Point at `provider_mode:
    deterministic_fallback` / `failure_category: ai_disabled`. _"When AI is off or
    can't be grounded, we fall back deterministically and say so."_
11. **History and auditability** — Open history. _"Everything is persisted and
    auditable."_
12. **Phase 3 Delivery Graph vision** — Close: _"Next, we feed this from real
    GitHub/Jira/Azure DevOps signals via a delivery graph and calibrated
    prediction."_

Total: ~3 minutes. Do not open code or talk stack.

---

## Ten-Minute Technical Walkthrough

1. **Architecture (1 min)** — typed Next.js frontend → FastAPI `/api/v2` →
   deterministic services → persistence → Leadership Brief orchestrator. App
   imports with no DB/Azure at import time.
2. **Deterministic intelligence (1.5 min)** — versioned policy (`policy_v1`),
   readiness/confidence, coverage, skill gaps, key-person risk, decision traces.
   Scores are reproducible.
3. **Simulation (1 min)** — add/remove/replace/compare; readiness + confidence
   deltas and mitigations.
4. **Persistence (1 min)** — immutable snapshots with input/result hashes;
   history and detail return persisted data, not recomputed.
5. **AI boundary (1.5 min)** — grounding validation; deterministic fallback;
   explicit `provider_mode` / `generation_status` / `failure_category`. AI never
   changes scores.
6. **Frontend (1 min)** — typed service/contract layers, async-state handling,
   Vitest tests (23 passing).
7. **CI (1 min)** — backend, frontend, e2e, security workflows; least privilege,
   timeouts, concurrency; local/CI command parity.
8. **E2E (0.5 min)** — Playwright 22-step flow on disposable SQLite, AI disabled,
   production frontend build; asserts no console errors / failed requests.
9. **Deployment (0.5 min)** — Render backend config; CORS parsing fix; rollback
   via redeploy + `alembic downgrade -1`; public frontend deferred.
10. **Limitations (0.5 min)** — synthetic data, no calibrated ML, no connectors,
    no auth/multi-tenancy, no live PG/Azure validation.
11. **Phase 3 roadmap (0.5 min)** — foundation → connectors → graph → prediction
    → continuous scenarios → AI chief of staff → security/scale → observability →
    realistic tenant → POC/pitch.

Total: ~10 minutes. Keep the business decision central even in the technical
walkthrough.
