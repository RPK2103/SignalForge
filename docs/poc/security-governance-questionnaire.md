# Security and Governance Questionnaire

Language used intentionally: **designed to support**, **requires customer
validation**, **POC configuration**, **not yet certified**, **not independently
audited**.

**Microsoft has not endorsed this project.** No SOC 2, ISO 27001, GDPR
certification, HIPAA, PCI DSS, or formal penetration-test completion is claimed
unless repository evidence proves it (none of those certifications are present).

## System boundaries

| Question | Current answer | Evidence | Status | Customer decision | Gap |
|---|---|---|---|---|---|
| What is in scope? | FastAPI backend + Next.js frontend + PostgreSQL/SQLite persistence | `backend/app/main.py`, `frontend/` | IMPLEMENTED | Confirm network boundary | Production hosting topology |
| Multi-tenant model? | Shared schema with tenant qualification + PG FORCE RLS | security migration + RLS tests | IMPLEMENTED (PG) | Approve tenancy model | SQLite does not prove RLS |
| Public surfaces? | `/`, `/health`, `/dashboard/*` assets only | auth middleware allowlist | IMPLEMENTED | Confirm allowlist | Docs URLs only when enabled |

## Authentication and authorization

| Question | Current answer | Evidence | Status | Customer decision | Gap |
|---|---|---|---|---|---|
| How are callers authenticated? | Bearer JWT; default-deny | `app/security/` | IMPLEMENTED | Choose `entra_oidc` for POC | Interactive MSAL SPA not shipped |
| Is tenant header authentication? | No — selector only | Prompt 7 docs + tests | IMPLEMENTED | N/A | N/A |
| RBAC? | 6 roles, versioned permission matrix | `permissions.py` | IMPLEMENTED | Map IdP groups → roles | SCIM deferred |
| Employee ranking permission? | Intentionally absent | permissions module | IMPLEMENTED | Confirm policy | N/A |

## Data protection

| Question | Current answer | Evidence | Status | Customer decision | Gap |
|---|---|---|---|---|---|
| Encryption in transit | HTTPS expected at edge | deployment guidance | POC CONFIGURATION | Provide TLS termination | App does not terminate prod TLS alone |
| Encryption at rest | Database/platform responsibility | hosting choice | POC CONFIGURATION | Azure PG + disk encryption | Not app-enforced |
| Secrets | Env vars locally; Key Vault recommended | config + architecture | PROPOSED for Key Vault | Mandate vault | Key Vault integration not implemented |
| Soft deletion / retention | Archival fields exist; customer policy needed | domain models | POC CONFIGURATION | Set retention | Formal deletion runbook customer-specific |
| Backup / DR | Not independently validated for production | — | NOT VALIDATED | Define RPO/RTO | No production DR proof |

## Audit, observability, AI controls

| Question | Current answer | Evidence | Status | Customer decision | Gap |
|---|---|---|---|---|---|
| Audit events? | Append-only security audit with redaction | audit service + API | IMPLEMENTED | Retention of audit store | SIEM export deferred |
| Observability? | Provider boundary + protected APIs + UI | Prompt 8 | IMPLEMENTED local | Azure Monitor export | Production OTLP not validated |
| Prompt injection controls? | Scanners + grounding rejection paths | CoS + AI quality | IMPLEMENTED (bounded) | Accept residual NL risk | Not full NL entailment |
| Evidence grounding? | Structured citations + support matrix | CoS services | IMPLEMENTED | Sample validation in POC | Phrase scanners ≠ semantic entailment |
| Human review? | Assessment + CoS review workflows | APIs/CLI/UI | IMPLEMENTED | Mandate review SOP | — |
| Live LLM in CI? | Forbidden for mandatory tests | AI quality gate | IMPLEMENTED | Keep offline gate | — |

## Synthetic demo boundaries

| Question | Current answer | Status |
|---|---|---|
| Is NovaBank real customer data? | No — fictional composite | IMPLEMENTED disclaimer |
| Public seed/reset API? | No — privileged CLI only | IMPLEMENTED |
| Production-eligible synthetic models? | No (`production_eligible=false`) | IMPLEMENTED |

## Vulnerability management

| Question | Current answer | Evidence | Gap |
|---|---|---|---|
| Dependency scanning? | pip-audit + npm production audit in CI | workflows | Continuous monitoring process is customer ops |
| Secret scanning? | gitleaks in CI | security-ci | — |
| Pen test? | Not completed | — | Customer may require independent test |

## Incident response

Designed to support customer IR processes via audit logs and observability
signals. A formal SignalForge production IR retainer is **not** claimed.

## Export handling

Exports of briefs/findings inherit tenant authz. Customer must define
download/print controls for regulated environments (POC CONFIGURATION).
