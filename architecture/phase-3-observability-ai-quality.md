# Phase 3 — Observability and AI Quality (Prompt 8)

This document describes the bounded, enterprise-grade observability and
AI-quality layer added in Prompt 8. It does not change Prompt 1–7 product
semantics. It answers operational and trust questions — *is SignalForge reliable,
is the AI trustworthy, can a regression be blocked before customers see it* —
without becoming a generic monitoring demo.

## 1. Observability architecture

Domain code never talks to a telemetry vendor directly. It records through a
provider-independent boundary:

- `ObservabilityProvider` (protocol) — `increment` / `record_value` / `set_gauge`
  / `start_span` / `shutdown`.
- `NoOpObservabilityProvider` — default when observability is disabled.
- `InMemoryObservabilityProvider` — deterministic capture for tests and local
  dashboards; pure Python, no network.
- `OpenTelemetryObservabilityProvider` — constructed only at the application edge
  when `OTEL_EXPORTER_MODE` is `console` or `otlp`.

The process-wide provider is selected once at startup (`init_observability`) and
read by middleware and domain recorders. It is a thin, explicitly-set holder —
**not** a global mutable metrics dictionary. Telemetry recording is fail-open: a
provider error is swallowed and never alters deterministic scoring, security, or
the caller's control flow. (Required security-audit persistence remains
fail-closed per Prompt 7 — telemetry does not weaken that.)

## 2. OpenTelemetry boundary

Official packages are pinned in `requirements.txt` (`opentelemetry-api/sdk`,
OTLP HTTP exporter). The SDK is imported lazily so unit tests never depend on it
and a missing SDK degrades gracefully to the in-memory provider. Exporter is
bounded (timeout, batch queue/export sizes, sample ratio) and flushes on
shutdown. No exporter network call happens in unit tests.

## 3. Trace propagation

- W3C `traceparent` is parsed and, when valid, the trace/span IDs are bound to
  the logging context.
- The correlation ID is sanitized (bounded length, safe charset) or generated
  when absent/invalid, set on `request.state`, echoed in the `X-Correlation-ID`
  response header, and reused by the authentication middleware.
- Correlation/trace/span IDs appear in structured logs but never as metric
  labels.

## 4. Metric taxonomy

Instrument names are a bounded enum (`app/observability/metrics.py`): HTTP,
connector/ingestion, delivery graph, prediction, scenario, Chief-of-Staff/AI,
and security-audit-health families, plus a telemetry self-health counter.

## 5. HTTP status semantics (critical)

`RequestTelemetryMiddleware` is outermost so it observes every response.

| Status | Classification | Server-error metric? |
| --- | --- | --- |
| 2xx/3xx | success | no |
| 400/404/409/422 | client/domain outcome | no |
| 401 | authentication denial | no |
| 403 | authorization denial | no |
| 429 | rate-limited | no |
| 5xx / unhandled | server/application failure | **yes** |

Expected 401/403 (the passing Playwright negative-path checks) are
security-denial telemetry, never 5xx and never availability failures. Only
genuine 5xx / unhandled exceptions increment `http.server.errors` and
`http.server.unhandled_exceptions`. Tests prove this both through the app and via
a standalone middleware app that raises a genuine 500.

## 6. Cardinality and privacy policy

There is exactly one allowlist (`TelemetryAttributePolicy`) of low-cardinality
labels: service, operation, http_method, normalized route template, status
family, bounded status code, outcome, provider_type, fallback_category,
connector_type, evaluation_type, model_version, prompt_template_version,
scenario_kind, environment, source_type, freshness_state, slo_status,
alert_severity.

Never permitted as labels: raw URL/paths with IDs, request/trace/correlation
IDs, tenant IDs, principal IDs, user names, emails, repository/project names,
evidence IDs, exception messages, prompt text, tokens. Persisted rollups may
carry `tenant_id` as an RLS-protected **column**, but tenant_id is never an
exported metric dimension. The policy drops nested/binary values and bounds
value length; it runs on every emission.

## 7. Secret/redaction policy (logs)

Optional JSON logs (`LOG_FORMAT=json`) include only safe structured fields. A
defensive redaction pass removes bearer tokens, `authorization` values,
JWT-shaped strings and `api_key/secret/password/token` assignments. No raw
claim, request body, provider output, evidence package, or connector credential
is logged. Auth/authz denials log safe reason categories only.

## 8. Connector telemetry and freshness

Recorder helpers (`app/observability/domain.py`) capture sync count/duration/
outcome, records observed/accepted/deduplicated/rejected, retries, rate limits,
dead letters, ingestion lag and freshness age. These recorders are **wired into
reachable application-service boundaries** and emit at runtime. Integrated
boundaries (one emission per logical operation, fail-open, bounded attributes):

| Domain | Service boundary | Emits |
| --- | --- | --- |
| Connector / ingestion | `IngestionService.complete_run` | connector sync outcome (success/partial/failure), duration, observed/accepted/deduplicated records — **after durable commit** |
| Ingestion freshness | `IngestionService.append_evidence` | ingestion lag and freshness age (clock-skew / missing event time never fabricated) — **after durable commit** |
| Delivery graph | `GraphProjectionService._project` | rebuild vs incremental outcome + duration; failure reported as failure, never success — **success deferred until UoW commit** |
| Prediction | `PredictionOrchestrator.predict` | prediction outcome (calibrated / uncalibrated fallback / insufficient-data / error) + duration — **success deferred until UoW commit** |
| Scenario | `ScenarioExecutionService.execute` | scenario run outcome + duration + deterministic fallback (idempotent reuse is not re-counted) — **success deferred until UoW commit** (keeps watch evaluation atomic) |
| Chief of Staff | `ChiefOfStaffOrchestrator.generate` | one generation count + provider/fallback/parse/schema/grounding/citation categories (no prompt/evidence/output text). Generation is compute-bound; persistence of briefs is a separate boundary. |
| Human review | `ChiefOfStaffService.append_review` and `HumanReviewPersistenceService.add_review` | requires non-optional `SecurityContext` (`chief_of_staff.review`; CLI uses explicit `internal_system_context`); bounded `cos.reviews` outcomes (`accepted` / `corrected` / `rejected` / `needs_follow_up` / `error`) — **success deferred until UoW commit**; no review text, reviewer identity, brief/assessment IDs |
| Prediction validation | `PredictionOrchestrator.evaluate` | requires non-optional `SecurityContext` (`predictions.validate`; CLI uses explicit `internal_system_context`); `prediction.validation_runs` outcomes (`passed` / `failed` / `insufficient_data` / `rejected` / `error`) + bounded `model_version` / `evaluation_type` — **success deferred until UoW commit**; does not promote or change model semantics |
| Security-audit health | `SecurityAuditService.record_sensitive_action` | required count at append; **succeeded count only after UoW commit**; failed/fail-closed on append failure |

Telemetry never alters deterministic business output, transaction behavior, or the
Prompt 7 fail-closed audit contract. Committed-success samples are emitted only
after a successful UnitOfWork commit (connector/ingestion commit inside the
service; graph/prediction/scenario/review/validation/audit success samples are
queued on the UoW and flushed on commit). A rollback or commit failure discards
pending success samples and never reports success. Node/edge deltas are recorded
on the graph run record but are not exported as separate metric dimensions (the
existing `record_graph_rebuild` recorder API is intentionally unchanged).
Human-review and prediction-validation metrics are collected at the service
boundaries above and readable via `MetricsReader`; they are **not** yet dedicated
dashboard tiles or SLO inputs. Dangerous values under allowlisted attribute keys
(email, UUID, JWT, token-like strings) are redacted to `redacted` by the
cardinality policy. Production OTLP
export, Azure Monitor deployment, external alert delivery and live-provider
evaluation remain deferred. Definitions (timezone-aware UTC):

```
ingestion lag = ingestion_time - source_event_time
freshness age = evaluation_time - latest_valid_source_event_time
```

Edge cases are honest, never fabricated: missing event time → `unavailable`;
future event time / negative lag → `clock_skew`; no successful checkpoint →
`never_synced`; within/over the per-source threshold → `fresh`/`aging`/`stale`.

## 9. AI-quality framework

A first-class **offline** evaluation framework (`app/observability/evaluation.py`)
with synthetic, immutable, versioned cases. Categories: evidence completeness,
citation correctness, unsupported-claim rate, decision consistency, fallback
determinism, prompt regression, adversarial evidence, provider variation. The
deterministic grounded generator cites only tenant-owned, at-or-before-cutoff
evidence, refuses when required evidence is missing, and ignores instructions
embedded in evidence text (prompt injection is resisted by construction).
Provider variants (`primary`/`secondary`/`malformed`) are fake and deterministic
— **no live LLM in mandatory CI**.

### Release gate

`release_dataset.py` defines a small high-quality dataset spanning Prompt 6
intents and edge conditions. Thresholds: citation correctness 100%, cross-tenant
citations 0, post-cutoff citations 0, unsupported high-severity claims 0,
fallback determinism 100%, schema-valid outputs 100%, employee-blame 0,
secret-exposure 0. The gate fails on **any** critical safety violation even when
the aggregate score is high. `python -m app.observability evaluate-ai-quality`
exits non-zero on failure.

## 10. Prediction drift/calibration tracking

Reuses Prompt 4 artifacts (no retraining). Snapshots compute Brier score,
expected calibration error, prediction/outcome distributions, PSI drift where
supported, and label coverage. Honest statuses: no labels → `unavailable` (not
zero); too few samples → `insufficient_data`; an uncalibrated score is never
called a probability; no automatic promotion/demotion.

## 11. SLO definitions and evaluation

Versioned, objective, deterministic (`app/observability/slo.py`). Indicators
include API 5xx-free ratio (excludes 401/403), latency p95, connector success
ratio, ingestion freshness, required-audit-write success, AI schema-valid ratio,
citation correctness. Statuses: `healthy` / `at_risk` / `breached` /
`insufficient_data` (below the minimum sample count). **Expected 401/403 do not
reduce the availability SLO** — proven by tests.

## 12. Alert model

Internal state evaluation only (`open`/`acknowledged`/`resolved`), severity
`info`/`warning`/`critical`. A stable fingerprint deduplicates: the same
condition/window never opens a second alert; a recovered SLO resolves its alert.
Transitions are append-only and tenant-scoped. Acknowledgement is authorized
(`observability.manage`) and audited. **No email/Teams/PagerDuty/SMS/SIEM.**

## 13. API security

`/api/v3/observability/*` routes are authenticated (middleware), tenant-resolved
and permission-gated by `require_permission`; the services re-check the same
permission (a direct service call without context fails closed). Reads paginate
with bounded limits; foreign/nonexistent resources are indistinguishable.
Responses carry only bounded safe fields. No Prompt 8 endpoint is public, and
there is no public `/metrics` scrape endpoint — OTLP export is preferred.

## 14. RBAC

Permissions: `observability.read`, `observability.manage`, `ai_quality.read`,
`ai_quality.evaluate`. Least-privilege mapping — TENANT_ADMIN: all four;
SECURITY_AUDITOR: observability.read + ai_quality.read; INTEGRATION_OPERATOR:
observability.read; INTELLIGENCE_ANALYST: ai_quality.read + ai_quality.evaluate.
The permission-matrix and coverage-registry versions are bumped and the two new
sensitive permissions are ROUTE-classified and cross-checked against live route
introspection.

## 15. Dashboard

`/observability` renders an authenticated, role-aware panel using the existing
design system: request volume, p50/p95 latency, 5xx rate, auth/authz denials,
connector success, AI fallback/grounding/schema ratios, SLO states, open alerts
and the latest evaluation run. It has loading/empty/error/retry states, no mock
fallback, and does no client-side metric calculation the backend owns. A 403
renders an access message with no retry.

## 16. Persistence and RLS

One additive migration `p3_observability_ai_quality` (parent
`p3_enterprise_security_scale`) creates nine tenant-scoped tables:
`ent_observability_metric_rollups`, `ent_slo_definitions`,
`ent_slo_evaluations`, `ent_alert_events`, `ent_ai_evaluation_datasets`,
`ent_ai_evaluation_cases`, `ent_ai_evaluation_runs`,
`ent_ai_evaluation_results`, `ent_prediction_quality_snapshots`. No raw spans,
logs, prompts, evidence or tokens are stored. All nine are added to the forced
PostgreSQL RLS registry (ENABLE + FORCE, transaction-local tenant GUC,
non-superuser app role, fail-closed on missing context); downgrade removes the
policies. SQLite is application-isolation only.

## 17. CI release gate

`observability-ci.yml` adds jobs: ruff format/lint, focused observability tests,
focused AI-evaluation tests, the deterministic release gate (non-zero on
critical violation, no `|| true` / `continue-on-error`), migration lifecycle,
PostgreSQL Prompt 8 RLS tests, pip-audit, and frontend tests/typecheck/build +
production npm audit. Mandatory CI never calls a live LLM or an external
exporter.

## 18. Failure behavior

Injected failures (exporter unavailable/timeout, metric persistence failure,
invalid/oversized attributes, evaluator exception, missing labels, malformed
provider output) leave deterministic scoring unchanged, never cross tenants,
never break the user request for ordinary telemetry, are safely counted/logged,
keep required audit fail-closed, persist evaluation-run failures safely, and
never leak secrets.

## 19. Operational runbook (local)

- Evaluate the AI release gate: `python -m app.observability evaluate-ai-quality --tenant-id <t>`
- Evaluate SLOs + sync alerts: `python -m app.observability evaluate-slos --tenant-id <t>`
- Inspect freshness: `python -m app.observability inspect-freshness --source-type github --latest-event <iso>`
- Record a calibration snapshot: `python -m app.observability record-prediction-quality --tenant-id <t> --input probs.json`
- View the dashboard: authenticate, select a tenant, open `/observability`.

## 20. Known limitations and non-claims

- Expected 401/403 test responses are **not** server failures.
- No production monitoring backend has been validated. **No Azure Monitor /
  Application Insights / live OTLP validation is claimed** (none was executed).
- **No production SLO attainment is claimed** — synthetic/local data only.
- AI evaluation uses deterministic/fake providers in mandatory CI; live provider
  comparison is optional/manual and never required.
- No automatic model promotion/demotion; no external alert delivery; no SIEM
  integration; no raw prompt/response retention.
- No Prompt 9 (NovaBank expansion) work. No Microsoft endorsement.
