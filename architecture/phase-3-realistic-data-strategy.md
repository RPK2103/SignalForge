# SignalForge — Phase 3 Realistic Data Strategy

_How SignalForge moves from synthetic toy identities to realistic, legally and
ethically sourced engineering signals — without becoming an employee-surveillance
product._

> **Status: PLANNING (Phase 3).** Phase 2 ships with synthetic, hard-coded toy
> identities (e.g. `kavi`, `vikram`, `arjun`) via the seed script and mock
> repository. Those have **not** been replaced. Replacing them is Phase 3 work.

---

## 1. Objectives

1. Give SignalForge data that is realistic enough to be credible in demos and
   pilots.
2. Support three clearly separated data modes with different legal/consent
   profiles.
3. Attach rich **provenance and permission** metadata to every ingested record.
4. Explicitly prohibit surveillance and scraping patterns.

## 2. Data Modes Overview

| Mode | Source | Consent basis | Primary use |
| --- | --- | --- | --- |
| 1 — Synthetic Enterprise Demo | Generated fictional org | None needed (fabricated) | Demos, tests, screenshots |
| 2 — Public Engineering Signals | Legally public data | Public/open licences | Realistic public showcase |
| 3 — Customer-Consented Data | Customer systems | Explicit authorization | Pilots, POCs, production |

---

## 3. Mode 1 — Synthetic Enterprise Demo

A fully fictional organization, **NovaBank** (a synthetic digital bank), used for
demos, tests and documentation. No real person or company is represented.

Plan realistic entities:

- **Business units:** Retail Banking, Payments, Wealth, Platform, Risk & Fraud.
- **Departments:** e.g. Payments → Card Payments, Real-Time Payments, Settlement.
- **Teams:** 6–12 cross-functional squads (e.g. `rtp-core`, `fraud-ml`,
  `ledger-platform`).
- **Synthetic engineers:** 60–120 fabricated profiles with roles, seniority,
  capabilities/skills, availability and (synthetic) tenure — **no real names,
  emails or photos**; use generated pseudonyms and stable synthetic IDs.
- **Initiatives:** e.g. "Instant Payments GA", "Fraud model v3", "Ledger
  re-platform", each with required capabilities and target dates.
- **Repositories:** synthetic repos mapped to teams with language/stack metadata.
- **Work items:** epics/stories/tasks with status, estimates and links to
  initiatives.
- **Incidents:** severity, affected service, MTTR, owning team.
- **Deployments:** frequency, environment, success/rollback.
- **Dependencies:** service→service and capability→capability edges.
- **Capabilities:** the capability registry that readiness scoring consumes.
- **Availability events:** planned leave, on-call, reallocation windows.

Generation approach: a deterministic, seeded generator (faker-style but pinned
seed) so demo data is reproducible across machines and CI.

---

## 4. Mode 2 — Public Engineering Signals

Use only **legally accessible, public** data under its licence/terms:

- Public repository metadata (stars, languages, topics, size).
- Public commits, pull requests, issues, releases.
- Public dependency manifests (SBOM-style).
- Official incident reports / status-page histories.
- Official public roadmaps.

Rules:

- Respect each platform's API terms and rate limits; store source URLs.
- Represent contributors **pseudonymously** by default (hash the public handle;
  do not build people-profiles or resolve identities).
- Do not enrich public handles with off-platform personal data.
- Cache only what is needed for the delivery signal; honor deletion requests.

Use case: a realistic, non-confidential public showcase (e.g. analyze delivery
signals for a well-known open-source org) without any private data.

---

## 5. Mode 3 — Customer-Consented Data

Ingested **only** under explicit, authorized customer configuration:

- GitHub organizations (App/OAuth with scoped permissions).
- Jira (project-scoped API tokens).
- Azure DevOps (PAT/OAuth, project-scoped).
- Incident systems (PagerDuty/Opsgenie/ServiceNow) via authorized APIs.
- Uploaded CSV/JSON (project plans, org records) provided by the customer.

Rules:

- Per-tenant credentials, least-privilege scopes, revocable at any time.
- Data isolation per tenant (see Phase 3 Prompt 1 / Prompt 7 in the roadmap).
- Configurable retention and hard-delete on offboarding.
- Only ingest fields needed for delivery/readiness signals.

---

## 6. Explicitly Prohibited

SignalForge will **not**, in any mode:

- Scrape LinkedIn or any employee/professional profiles.
- Scrape private profiles or gated content.
- Collect personal email addresses.
- Ingest Slack/Teams/DMs without explicit authorization and scope.
- Infer sensitive personal attributes (health, religion, ethnicity, politics,
  sexual orientation, union membership, etc.).
- Position or market the product as employee surveillance, individual
  performance ranking, or stack-ranking.

The unit of analysis is **team and initiative delivery capability**, not
individual monitoring.

---

## 7. Provenance & Permission Metadata

Every ingested record (all modes) carries provenance fields:

| Field | Meaning |
| --- | --- |
| `tenant_id` | Owning tenant (synthetic tenant for Modes 1/2) |
| `source` | Origin system (e.g. `github`, `jira`, `synthetic`, `public`) |
| `source_record_id` | Stable ID within the source |
| `event_time` | When the underlying event happened |
| `ingestion_time` | When SignalForge ingested it |
| `schema_version` | Version of the ingestion schema |
| `processing_version` | Version of the transform/scoring pipeline |
| `confidence` | Confidence in the record's accuracy/completeness |
| `freshness` | Age / staleness indicator |
| `permission_classification` | `synthetic` \| `public` \| `consented` \| `restricted` |

Provenance enables auditability, freshness-aware scoring, and honest confidence
reporting — a direct extension of Phase 2's deterministic, explainable design.

---

## 8. Migration Path (Phase 2 → Phase 3)

1. Introduce the multi-tenant domain + provenance schema (roadmap Prompt 1).
2. Ship the NovaBank synthetic generator as the default demo tenant.
3. Add connectors (roadmap Prompt 2) feeding Mode 2/3 behind consent config.
4. Only then retire toy seed identities from demo defaults.

**Do not claim** toy identities have been replaced — that is Phase 3 work.
