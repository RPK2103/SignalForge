# Microsoft Enterprise POC Blueprint

**Status labels used:** IMPLEMENTED · POC CONFIGURATION · PROPOSED · DEFERRED · NOT VALIDATED  
**Endorsement:** Microsoft has **not** endorsed, partnered with, certified, or
listed SignalForge on Azure Marketplace.

## 1. POC objective

Evaluate whether SignalForge helps engineering leaders answer delivery questions
with grounded evidence for selected initiatives — not whether a single score
“passes.”

Recommended duration: **4–6 weeks**.

## 2. Stakeholders

| Role | Responsibility |
|---|---|
| Executive sponsor | Go/no-go authority; success criteria approval |
| VP Engineering / CTO | Economic buyer; readiness interpretation |
| Engineering operations lead | Operational buyer; workflow fit |
| Program / portfolio leader | Initiative selection and usefulness review |
| Platform engineering lead | Architecture and ops fit |
| Security / compliance reviewer | Security questionnaire and control acceptance |
| Data owner | Source approval, retention, deletion |
| Engineering managers | Human validation of findings |
| Product owner | Initiative framing |
| SignalForge implementation owner | Tenant setup, connectors, workshops |

## 3. POC lifecycle

1. Discovery  
2. Security and architecture review  
3. Data-source selection  
4. Connector configuration  
5. Historical evidence ingestion  
6. Delivery Graph construction  
7. Baseline readiness analysis  
8. Scenario workshops  
9. Chief-of-Staff brief review  
10. Human validation  
11. Success-measurement review  
12. Go/no-go decision  

## 4. Entry criteria

- Executive sponsor identified.
- Tenant and data boundaries agreed in writing.
- Approved source systems identified (see data-onboarding plan).
- Required historical window available from data owners.
- Security review initiated (questionnaire in progress).
- User roles mapped to SignalForge RBAC roles.
- Success criteria approved (multi-metric; not a single score).
- Evaluation initiatives selected (typically 2–5).
- Responsible data owners assigned.
- Authentication mode for the POC environment agreed
  (`entra_oidc` recommended for customer POC; `local_development` is **not**
  production authentication).

## 5. Exit criteria

- Required data sources ingested or explicitly deferred with sign-off.
- Evidence completeness measured (coverage/freshness/completeness).
- Graph relationships spot-validated by engineering managers.
- Baseline findings reviewed with accepted / disputed / dismissed outcomes.
- Scenario outputs reviewed with estimate-kind honesty preserved.
- Citations validated on sampled Chief-of-Staff briefs.
- False-positive and false-negative review completed for sampled findings.
- Security controls accepted or exceptions documented.
- Operational support model reviewed (who owns ingestion failures).
- Decision recorded (go / no-go / extend) with written rationale.

POC success **must not** depend solely on a single readiness or prediction score.

## 6. Recommended evaluation initiatives

Select initiatives that exercise:

- capability gaps;
- cross-team dependencies;
- ownership concentration;
- key-person / availability risk;
- at least one counterfactual workshop.

Prefer real customer initiatives for evaluation. NovaBank may be used only as a
**pre-POC product tour** and must remain labelled fictional.

## 7. Configuration checklist (POC CONFIGURATION)

| Item | Notes |
|---|---|
| PostgreSQL | Required to exercise FORCE RLS like CI |
| Entra app registration | If using `entra_oidc` |
| GitHub connector credentials | IMPLEMENTED connector; customer secrets in vault |
| Jira / Azure DevOps | DESCRIPTORS ONLY — PROPOSED CONNECTOR / MANUAL IMPORT |
| Azure OpenAI | Optional; deterministic fallback remains valid |
| Network controls | Private ingress / restricted egress as customer requires |
| Tenant admin + reader principals | Map to RBAC matrix |

## 7b. Microsoft-aligned reference architecture

| Area | Current implementation | Microsoft POC option | Required work | Status |
|---|---|---|---|---|
| Application hosting | Local uvicorn / Render blueprint | Azure Container Apps or App Service; AKS only if justified | Containerize, deploy, health probes | PROPOSED |
| Data | SQLite local; PostgreSQL for RLS proof | Azure Database for PostgreSQL | Provision, migrate, RLS role | POC CONFIGURATION |
| Object storage | Not required for core path | Azure Storage for bounded artifacts if needed | Define artifact classes | DEFERRED unless required |
| Identity | JWT verifier incl. `entra_oidc` mode; local/test modes; no MSAL SPA | Microsoft Entra ID interactive login | App registration + frontend token provider | INTEGRATION REQUIRED |
| Secrets | Environment variables | Azure Key Vault | Wire secret resolution | PROPOSED |
| Observability | In-process + optional OTel construct; protected APIs/UI | Azure Monitor, Application Insights, Log Analytics | Exporters + dashboards | PROPOSED |
| Networking | CORS/trusted hosts config | Private ingress, private endpoints, VNet, restricted egress | Customer network design | POC CONFIGURATION |
| DevOps | GitHub Actions CI | GitHub Actions; Azure DevOps as optional **source** connector later | Pipeline to Azure env | CONFIGURATION |
| AI | Deterministic fallback + provider abstraction; Azure client paths exist | Azure OpenAI when approved | Keys, grounding policy, disable-in-CI | CONFIGURATION |
| Analytics | SignalForge UI | Power BI export/integration | Not built | DEFERRED |
| Collaboration | None | Teams / Copilot Studio | Not built | DEFERRED |

Do **not** present proposed services as already implemented. Microsoft has not
endorsed this project.

## 8. Decision framework

Record for each evaluation initiative:

- evidence completeness;
- finding usefulness (manager agreement);
- disputed rate;
- actionable recommendations accepted;
- residual limitations;
- whether leadership would use the brief in a real review meeting.

Go criteria example (customer-specific targets — NOT VALIDATED defaults):

- sampled citation validity ≥ agreed threshold;
- disputed finding rate within agreed band;
- security questionnaire exceptions closed or accepted;
- at least one workshop produced follow-up actions leadership owns.

## 9. Explicit non-claims

- No guaranteed delivery improvement.
- No claim that scenarios are causal predictions.
- Uncalibrated scores are not probabilities.
- Synthetic NovaBank outcomes are not customer evidence.
- No Microsoft Marketplace or endorsement claim.
