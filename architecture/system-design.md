# SignalForge System Design

Mission:
SignalForge is an AI-powered execution intelligence platform that helps engineering leaders identify what engineers can actually deliver based on evidence rather than self-reported skills.

Inputs:

- Engineer profile
- Certifications
- GitHub summaries
- PR summaries
- Architecture notes
- Project history

Outputs:

- Execution score
- Backend score
- Cloud score
- AI readiness score
- Strengths
- Risks
- Project fit recommendations
- Team recommendations

Frontend:

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

Backend:

- FastAPI
- Python
- Pydantic
- Versioned readiness API at `/api/v2` (Phase 2 intelligence domain)
- Team simulation API at `/api/v2/simulations` (deterministic what-if staffing analysis)
- Persistence and history APIs at `/api/v2/assessments` and `/api/v2/simulation-records` (SQLAlchemy + Alembic; immutable snapshots, append-only reviews and audit events)
- Leadership Brief APIs at `/api/v2/assessments/{assessment_record_id}/leadership-brief` (grounded AI communication layer with deterministic fallback)
- Compute-only v2 routes unchanged; persistence endpoints use SQL-backed catalog via `DATABASE_URL`
- Legacy MVP routes remain at root paths (`/analyze`, `/recommend-team`, `/simulate`, etc.)

AI:

- Azure OpenAI

MVP Features:

1. Engineer Analysis
2. Capability Scoring
3. Project Fit Recommendation
4. Risk Assessment

Hackathon Rule:
Every feature must improve the demo experience.


Business Problem:

Engineering managers struggle to identify which engineers can successfully execute a project based on real evidence rather than self-reported skills.

SignalForge analyzes engineering evidence and generates explainable execution intelligence.

Core Demo Scenario:

An engineering manager needs to staff an Azure AI migration project.

SignalForge evaluates engineers and recommends:

* Best-fit engineer
* Risk assessment
* Capability breakdown
* Recommended team composition

Differentiator:

Unlike traditional skill matrices, SignalForge focuses on execution capability inferred from evidence.

