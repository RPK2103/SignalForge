# Phase 3 Prompt 6 — AI Chief of Staff

## Purpose

SignalForge AI Chief of Staff converts deterministic, temporal, provenance-aware
execution intelligence (Prompts 1–5) into **immutable, evidence-backed executive
briefs**.

This is **not**:

- an autonomous agent
- a chatbot with conversational memory
- a staffing / employee-ranking tool
- a thin LLM wrapper that invents scores
- a mutation API for unauthenticated callers

## Supported intents

1. `delivery_status_brief`
2. `change_since_last_review`
3. `scenario_comparison_brief`
4. `delivery_prediction_brief`
5. `evidence_gap_brief`

Targets: `project` or `initiative` only.

Decision options are a structured advisory section derived from a deterministic
allowlist — not a separate intent.

## Product boundary vs Phase 2 Leadership Brief

Phase 2 Leadership Brief remains assessment-scoped communication over readiness
risk packages.

Prompt 6 introduces a **new v3 domain** that:

- reuses canonical JSON / SHA-256 hashing, tenant context, UoW, provider patterns
- does **not** mutate Phase 2 schemas into an all-purpose object
- cites Prompt 3/4/5 immutable outputs without recalculating them

## Evidence package

Packages are tenant-qualified, cutoff-scoped, bounded, deterministically ordered,
and hashed with `snapshot_service.canonical_json` / `snapshot_hash`.

When an immutable Phase 2 assessment exists for the target at the cutoff (via
`legacy_project_id`), its readiness score and assessment confidence are included
as evidence. Prompt 6 never recalculates those scores. When no valid assessment
exists, the package records an explicit missing-data warning and leaves readiness
fields null — graph findings do not substitute for readiness or assessment
confidence.

Truncation is recorded and exposed as a limitation — evidence is never silently
dropped without metadata.

## Claims and citations

Claims are first-class persisted entities with a support matrix.
Citations may reference **only** evidence IDs from the exact package used by the
brief. Unsupported / partially supported / fabricated citations reject the
provider result and trigger deterministic fallback.

Grounding validation is **structured**, not natural-language entailment: claim
type ↔ evidence type matrix, citation package/tenant/cutoff checks, prediction
estimate-kind/probability rules, and decision-option allowlisting. Phrase and
responsible-language scanners are defense-in-depth only and do not prove that
claim prose is entailed by cited evidence summaries.

## Estimate semantics (preserved)

| Concept | Meaning |
|---|---|
| Readiness | Deterministic execution-condition score |
| Assessment confidence | Strength of evidence for readiness |
| Graph confidence | Support for a graph finding |
| Prediction probability | Only from an active validated calibrated model |
| Uncalibrated score | Deterministic scorecard; **not** probability |
| Scenario impact confidence | Support for a deterministic scenario impact |

NovaBank retains `uncalibrated_score` with `probability=null`. The synthetic
candidate model is **not** promoted for demonstration.

## Provider and fallback

Modes: `azure_openai`, `deterministic_fallback`.

Requested provider may be Azure OpenAI; final provider may be deterministic
fallback after provider/validation failure. Failures are categorized and visible.

No unbounded retry loop. One provider attempt; explicit regeneration creates a
new immutable run.

## Prompt-injection defenses and limits

Evidence text is treated as untrusted data. Suspicious instruction-like phrases
force deterministic fallback with `prompt_injection_detected`.

**This is not perfect prevention.** Phrase checks are defense-in-depth alongside
schema, grounding, citation, and responsible-language validation.

## Tenant isolation

Every repository/service lookup is tenant-qualified. Foreign and nonexistent IDs
are externally equivalent. Tenant header is **not authentication**.

## API / CLI boundary

Read-only `/api/v3/chief-of-staff/*` routes.
Generation, review append, and NovaBank seeding are **CLI/service-only**.

```text
python -m app.chief_of_staff generate|validate|compare|review|quality|seed-novabank
```

## Responsible use

- Decision options are advisory only
- No autonomous decisions or tool execution
- No delivery guarantees
- No causal inference from scenarios
- No employee blame / ranking / punitive staffing recommendations
- No Microsoft endorsement claim
- No customer validation exists

## NovaBank demonstration

`seed-novabank` generates bounded deterministic briefs for delivery status,
change-since-review, scenario comparison (when runs exist), prediction, and
evidence gaps. Synthetic/demo limitations are stated in output.

## Quality metrics

`GET /api/v3/chief-of-staff/quality-summary` and CLI `quality` expose run counts,
fallback rate, failure categories, grounding/citation failures, and optional
latency/token summaries when persisted.

OpenTelemetry dashboards / alerting are deferred to Prompt 8.

## Known limitations

- Tenant header is not authentication (Prompt 7)
- Generation mutations are not exposed on the unauthenticated API
- NovaBank uses uncalibrated fallback semantics; candidate model failed its gate
- NovaBank `seed-novabank` skips `scenario_comparison_brief` when fewer than two
  completed scenario runs exist for the selected target
- No live PostgreSQL validation is claimed unless separately executed
- No real-time streaming, multi-agent orchestration, or portfolio digest
- Prompt 6 does **not** make SignalForge fully enterprise-ready
- `prior_brief_id` is application-enforced (same tenant/target, earlier cutoff);
  there is no database foreign key (avoids circular run↔brief constraints)
- Grounding does not perform full NL entailment of claim text against evidence
- Package maximum-bound behavior truncates with metadata; request-level scenario
  ID overflow is rejected
- `package_hash` is content-canonical (excludes self-hash). Semantic citations
  bind to that hash (not a database snapshot primary key). `output_hash` hashes
  the structured brief plus an explicit version envelope
  (`evidence_package_hash`, `fallback_template_version`, `output_schema_version`)
  and excludes run/brief/snapshot database IDs, timestamps and durations.
  Persistence still stores an internal evidence-snapshot FK separately.

## Deferred work

- Prompt 7: Entra ID, RBAC, PostgreSQL RLS
- Prompt 8: observability export / alerting
- Prompt 9: larger NovaBank / portfolio scale
- Prompt 10: remaining enterprise hardening
