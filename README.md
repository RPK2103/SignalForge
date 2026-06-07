# SignalForge

**Predict. Simulate. Deliver.**

**AI-powered Engineering Execution Intelligence**

SignalForge is an AI-powered Engineering Execution Intelligence platform that helps engineering leaders predict project delivery success, identify staffing risks, simulate team changes, and make evidence-based decisions before projects fail.

Built for the **Microsoft Build AI Hackathon 2026**.

## Live Project Links

Try the deployed demo:

- **Live Dashboard:** [https://signalforge-o0m4.onrender.com/dashboard/](https://signalforge-o0m4.onrender.com/dashboard/)
- **Backend API:** [https://signalforge-o0m4.onrender.com](https://signalforge-o0m4.onrender.com)
- **Swagger API Docs:** [https://signalforge-o0m4.onrender.com/docs](https://signalforge-o0m4.onrender.com/docs)

---

## Problem

Engineering managers often lack a reliable way to match engineers to high-stakes initiatives. Resumes and self-assessments do not reveal execution readiness for complex work such as cloud migrations, platform modernization, or AI adoption.

## Solution

SignalForge analyzes structured engineering evidence and produces:

- **Execution and capability scores** (backend, cloud, AI readiness)
- **Project fit recommendations** for a target initiative
- **Risk assessment** with explainable strengths and gaps
- **Team composition guidance** for delivery planning
- **Staffing impact simulation** to compare before/after scenarios
- **SignalForge Copilot** for natural-language queries over execution intelligence
- **REST API** with interactive Swagger documentation

### Demo scenario

An engineering manager needs to staff an **Azure AI migration** project. SignalForge evaluates candidate engineers, highlights the best fit, flags delivery risks, and recommends a team—backed by evidence rather than guesswork.

---

## Screenshots

![SignalForge Cover](assets/signalforge-cover.png)

### Dashboard

The executive dashboard summarizes delivery readiness, capability breakdown, project fit, risk, and team recommendations in one view.

![Dashboard Overview](assets/dashboard-home.png)

### Architecture

SignalForge combines a modular FastAPI backend, Azure OpenAI reasoning, and an executive dashboard to turn evidence into actionable execution intelligence.

![Architecture Diagram](assets/architecture.png)

### Staffing Impact Simulator

Compare staffing decisions side by side to understand how team changes affect delivery outcomes.

![Staffing Impact Simulator](assets/staffing-simulator-before-after.png)

### SignalForge Copilot

Ask questions in natural language and explore analysis, recommendations, and insights through the copilot console.

![SignalForge Copilot](assets/copilot-console.png)

### API Documentation

Explore and test SignalForge endpoints through auto-generated Swagger docs.

![Swagger API Docs](assets/api-docs.png)

---

## AI Integration & Intelligence Design

SignalForge uses a hybrid intelligence architecture.

The platform first converts engineer and project inputs into structured execution signals such as capability coverage, project fit, delivery risk, success probability, and staffing dependency impact.

Azure OpenAI is then used as a reasoning layer over these structured signals. Instead of acting as a generic chatbot, the SignalForge Copilot interprets project context, explains staffing risk, summarizes delivery confidence, and generates strategic recommendations for engineering leaders.

This design keeps the core decision signals explainable while using AI for synthesis, reasoning, and executive decision support.

---

## Data Privacy

SignalForge uses synthetic demo data only.

No confidential employer data, proprietary project data, sensitive employee information, or personal records are included in this repository.

API keys and secrets are managed through environment variables and are not committed to source control.

---

## AI Tools Used

- Azure OpenAI for Copilot reasoning and strategic recommendations
- AI-assisted development tools for coding support, UI iteration, documentation refinement, and demo storytelling

All final product decisions, architecture direction, implementation choices, testing, deployment, and submission materials were reviewed and completed by the participant.

---

## MVP Limitations

This is a hackathon MVP built to demonstrate the core execution intelligence concept.

Current limitations:

- Uses synthetic demo data
- Uses explainable scoring logic rather than trained historical ML models
- Does not yet integrate with enterprise systems such as Azure DevOps, GitHub, Microsoft Graph, Workday, or Teams
- Does not yet include authentication or role-based access control

These limitations are intentional for the MVP scope and are part of the future roadmap.

---

## Future Roadmap

- Azure DevOps integration for delivery signals
- GitHub integration for contribution and code activity signals
- Microsoft Graph integration for collaboration and team context
- Workday or HRIS integration for skill and role data
- Historical delivery learning from completed projects
- Organization-wide capability graph
- Agentic staffing recommendations
- Executive briefing generation
- Role-based access and enterprise authentication

The long-term vision is to evolve SignalForge into an AI Chief of Staff for Engineering Delivery.

---

## Evaluation Criteria Alignment

### AI Integration & Intelligence Design

SignalForge uses Azure OpenAI as a reasoning layer over structured execution signals. The Copilot converts staffing, capability, risk, and delivery data into strategic recommendations.

### System Architecture & Engineering Quality

The application uses a modular backend, structured APIs, explainable scoring engines, Azure OpenAI integration, an interactive dashboard, and live deployment.

### Communication, Presentation & UX

The dashboard is designed as an executive command center with clear metrics, reasoning panels, and simulation-first storytelling.

### Prototype Readiness & Scalability

The project is fully deployed with a live dashboard, backend API, Swagger documentation, and public GitHub repository.

### Problem Depth & Product Clarity

SignalForge addresses a real enterprise problem: engineering leaders often lack an evidence-based way to predict delivery risk and staffing impact.

### Market Understanding & Product Fit

The product fits enterprise engineering organizations, consulting firms, AI transformation teams, cloud migration teams, and delivery leadership groups.

---

## Tech stack

| Layer | Technologies |
|-------|--------------|
| Frontend | HTML, CSS, JavaScript, custom executive dashboard, interactive simulator, AI reasoning panels |
| Backend | Python, FastAPI, Pydantic v2, Azure OpenAI, OpenAI SDK, REST APIs |
| Deployment | Render, GitHub |

---

## Repository structure

```
SignalForge/
├── assets/            # Project screenshots (see assets/README.md)
├── backend/           # FastAPI API, services, and deployed dashboard
│   └── dashboard/     # Live executive dashboard UI
├── frontend/          # Next.js prototype (local development)
├── architecture/      # System design and MVP scope
└── sample-data/       # Demo engineer profiles
```

---

## Getting started

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open the dashboard at `http://localhost:8000/dashboard/` after starting the backend.

### Frontend (optional local prototype)

```bash
cd frontend
npm install
npm run dev
```

Configure Azure OpenAI credentials in your local environment before running AI-powered features. See backend configuration for required settings.

---

## Hackathon highlights

- **Evidence-based execution intelligence** — scores and recommendations grounded in structured engineering signals
- **Explainable AI** — clear strengths, risks, and fit rationale for judges and stakeholders
- **End-to-end demo flow** — dashboard, simulator, copilot, and API in a cohesive MVP
- **Azure AI integration** — Azure OpenAI powers analysis, insights, and the copilot experience

---

## License

See repository license terms for usage details.
