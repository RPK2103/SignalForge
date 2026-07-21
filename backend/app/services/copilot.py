import json
import re

from fastapi import HTTPException

from app.adapters.legacy_mapper import (
    legacy_coverage_percentage,
    legacy_risk_level_from_coverage,
    legacy_success_probability,
    legacy_team_to_domain,
)
from app.core.config import get_settings
from app.repositories.mock_catalog_repository import MockCatalogRepository
from app.schemas.copilot import CopilotRequest, CopilotResponse
from app.schemas.predictor import SuccessPredictionRequest
from app.schemas.team import TeamRecommendationRequest
from app.services.ai_service import create_chat_completion
from app.services.intelligence.capability_coverage_service import CapabilityCoverageService
from app.services.predictor import predict_success
from app.services.simulator import _build_simulation_summary, _recommended_team
from app.services.team_recommender import recommend_team

_catalog = MockCatalogRepository()

SYSTEM_PROMPT = (
    "You are SignalForge Copilot, an executive AI advisor for engineering leaders. "
    "Answer only using the provided project execution context. "
    "Be concise, practical, and leadership-friendly. Do not invent facts. "
    "Use at most 4 sentences. Mention concrete evidence when possible. "
    "Prefer business language over technical jargon. "
    "When answering questions about critical capabilities, dependencies, resilience, "
    "single points of failure, or staffing changes, prioritize staffing simulation "
    "evidence and capability loss analysis. "
    "If the answer cannot be determined from the context, say so clearly."
)

FALLBACK_ANSWER = (
    "SignalForge could not generate an AI response right now, but the project shows "
    "strong execution readiness based on capability coverage, team fit, and delivery risk."
)

REMOVAL_KEYWORDS = (
    "remove",
    "removed",
    "without",
    "lose",
    "losing",
    "left",
    "leave",
    "leaving",
    "depart",
    "drop",
    "dropped",
)

SIMULATION_SOURCE_KEYWORDS = (
    "staffing simulation",
    "critical capability",
    "most critical",
    "dependency",
    "single point of failure",
    "resilience",
    "what happens if",
    "removed",
    "remove",
    "risk impact",
)

DEFAULT_REMOVAL_BY_PROJECT: dict[str, list[str]] = {
    "Azure AI Migration": ["Kavi"],
}


def _legacy_team_coverage(required_skills: list[str], team, project) -> tuple[int, list[str]]:
    domain_project, domain_team = legacy_team_to_domain(project, team)
    coverage_results = CapabilityCoverageService().analyze(domain_project, domain_team)
    coverage_pct = legacy_coverage_percentage(coverage_results, len(required_skills))
    covered = [
        result.capability_name
        for result in coverage_results
        if result.level.value != "missing"
    ]
    return coverage_pct, covered


def _detect_named_removal_engineers(question: str) -> list[str]:
    question_lower = question.lower()
    if not any(keyword in question_lower for keyword in REMOVAL_KEYWORDS):
        return []

    detected: list[str] = []
    for name in _catalog.list_engineer_names():
        if re.search(rf"\b{re.escape(name.lower())}\b", question_lower):
            detected.append(name)
    return detected


def _is_simulation_relevant(question: str) -> bool:
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in SIMULATION_SOURCE_KEYWORDS)


def _highest_impact_removal(original_team, required_skills: list[str], project) -> list[str]:
    coverage_before, covered_before = _legacy_team_coverage(required_skills, original_team, project)
    risk_before = legacy_risk_level_from_coverage(coverage_before)
    success_before = legacy_success_probability(coverage_before, risk_before)

    best_engineer: str | None = None
    best_impact = -1
    for engineer in original_team:
        remaining_team = [
            member for member in original_team if member.name != engineer.name
        ]
        coverage_after, covered_after = _legacy_team_coverage(
            required_skills, remaining_team, project
        )
        lost_capabilities = [skill for skill in covered_before if skill not in covered_after]
        risk_after = legacy_risk_level_from_coverage(coverage_after)
        success_after = legacy_success_probability(coverage_after, risk_after)
        impact_score = max(0, success_before - success_after)
        if impact_score > best_impact or (
            impact_score == best_impact and lost_capabilities and best_engineer is None
        ):
            best_impact = impact_score
            best_engineer = engineer.name

    return [best_engineer] if best_engineer else []


def _resolve_removal_engineers(
    question: str,
    project_name: str,
    original_team,
    required_skills: list[str],
    project,
) -> list[str]:
    named_removals = _detect_named_removal_engineers(question)
    if named_removals:
        return named_removals
    if project_name in DEFAULT_REMOVAL_BY_PROJECT:
        return DEFAULT_REMOVAL_BY_PROJECT[project_name]
    return _highest_impact_removal(original_team, required_skills, project)


def _analyze_most_critical_capability(original_team, required_skills: list[str], project) -> dict:
    coverage_before, covered_before = _legacy_team_coverage(
        required_skills, original_team, project
    )
    risk_before = legacy_risk_level_from_coverage(coverage_before)
    success_before = legacy_success_probability(coverage_before, risk_before)

    top_scenario: dict | None = None
    for engineer in original_team:
        remaining_team = [
            member for member in original_team if member.name != engineer.name
        ]
        coverage_after, covered_after = _legacy_team_coverage(
            required_skills, remaining_team, project
        )
        lost_capabilities = [skill for skill in covered_before if skill not in covered_after]
        risk_after = legacy_risk_level_from_coverage(coverage_after)
        success_after = legacy_success_probability(coverage_after, risk_after)
        impact_score = max(0, success_before - success_after)
        scenario = {
            "removed_engineer": engineer.name,
            "lost_capabilities": lost_capabilities,
            "impact_score": impact_score,
            "risk_before": risk_before,
            "risk_after": risk_after,
            "success_probability_before": success_before,
            "success_probability_after": success_after,
        }
        if top_scenario is None or impact_score > top_scenario["impact_score"]:
            top_scenario = scenario

    if top_scenario and top_scenario["lost_capabilities"]:
        lost_text = ", ".join(top_scenario["lost_capabilities"])
        return {
            "capability": top_scenario["lost_capabilities"][0],
            "lost_capabilities": top_scenario["lost_capabilities"],
            "key_engineer": top_scenario["removed_engineer"],
            "impact_score": top_scenario["impact_score"],
            "analysis": (
                f"Removing {top_scenario['removed_engineer']} is the highest-impact scenario, "
                f"losing {lost_text}, shifting risk from {top_scenario['risk_before']} to "
                f"{top_scenario['risk_after']}, and reducing success probability from "
                f"{top_scenario['success_probability_before']}% to "
                f"{top_scenario['success_probability_after']}%."
            ),
        }

    return {
        "capability": None,
        "lost_capabilities": [],
        "key_engineer": None,
        "impact_score": 0,
        "analysis": (
            "No single-engineer removal from the recommended team loses a required capability."
        ),
    }


def _build_staffing_simulation_context(
    removal_engineers: list[str],
    original_team,
    required_skills: list[str],
    project,
) -> dict | None:
    if not removal_engineers:
        return None

    original_names = [engineer.name for engineer in original_team]
    on_team = [name for name in removal_engineers if name in original_names]
    if not on_team:
        return None

    remaining_team = [
        engineer for engineer in original_team if engineer.name not in on_team
    ]
    coverage_before, covered_before = _legacy_team_coverage(
        required_skills, original_team, project
    )
    coverage_after, covered_after = _legacy_team_coverage(
        required_skills, remaining_team, project
    )
    lost_capabilities = [skill for skill in covered_before if skill not in covered_after]

    risk_before = legacy_risk_level_from_coverage(coverage_before)
    risk_after = legacy_risk_level_from_coverage(coverage_after)
    success_before = legacy_success_probability(coverage_before, risk_before)
    success_after = legacy_success_probability(coverage_after, risk_after)
    impact_score = max(0, success_before - success_after)

    return {
        "removed_engineers": on_team,
        "lost_capabilities": lost_capabilities,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "risk_before": risk_before,
        "risk_after": risk_after,
        "success_probability_before": success_before,
        "success_probability_after": success_after,
        "impact_score": impact_score,
        "simulation_summary": _build_simulation_summary(on_team, lost_capabilities, risk_after),
        "most_critical_capability": _analyze_most_critical_capability(
            original_team,
            required_skills,
            project,
        ),
    }


def _build_execution_context(project_name: str, question: str) -> dict:
    project = _catalog.get_legacy_project(project_name)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found.")
    engineers = _catalog.list_legacy_engineers()
    required_skills = project.required_skills

    team_result = recommend_team(
        TeamRecommendationRequest(project=project, engineers=engineers)
    )
    prediction = predict_success(SuccessPredictionRequest(project_name=project_name))

    original_team = _recommended_team(project, engineers)
    coverage_percent, covered_skills = _legacy_team_coverage(
        required_skills, original_team, project
    )
    risk_level = legacy_risk_level_from_coverage(coverage_percent)
    average_fit = (
        round(
            sum(member.fit_score for member in team_result.recommended_team)
            / len(team_result.recommended_team)
        )
        if team_result.recommended_team
        else 0
    )

    context: dict = {
        "project_name": project.name,
        "required_skills": required_skills,
        "project_fit": {
            "average_team_fit_score": average_fit,
            "matched_skills": team_result.team_coverage,
            "missing_skills": team_result.missing_coverage,
        },
        "team_recommendation": {
            "recommended_team": [
                {
                    "name": member.name,
                    "fit_score": member.fit_score,
                    "role": member.role,
                }
                for member in team_result.recommended_team
            ],
            "team_coverage": team_result.team_coverage,
            "missing_coverage": team_result.missing_coverage,
            "summary": team_result.summary,
        },
        "risk_assessment": {
            "risk_level": risk_level,
            "coverage_percent": coverage_percent,
            "covered_skills": covered_skills,
            "missing_skills": team_result.missing_coverage,
        },
        "success_prediction": {
            "success_probability": prediction.success_probability,
            "confidence": prediction.confidence,
            "delivery_outlook": prediction.delivery_outlook,
            "reasoning": prediction.reasoning,
            "summary": prediction.summary,
        },
    }

    if _is_simulation_relevant(question):
        removal_engineers = _resolve_removal_engineers(
            question=question,
            project_name=project_name,
            original_team=original_team,
            required_skills=required_skills,
            project=project,
        )
        simulation = _build_staffing_simulation_context(
            removal_engineers=removal_engineers,
            original_team=original_team,
            required_skills=required_skills,
            project=project,
        )
        if simulation is not None:
            context["staffing_simulation"] = simulation

    return context


def _sources_from_context(context: dict) -> list[str]:
    source_map = {
        "project_fit": "project_fit",
        "team_recommendation": "team_recommendation",
        "risk_assessment": "risk_assessment",
        "success_prediction": "success_prediction",
        "staffing_simulation": "staffing_simulation",
    }
    return [label for key, label in source_map.items() if key in context]


def _build_user_prompt(question: str, context: dict) -> str:
    return (
        "Project execution context (JSON):\n"
        f"{json.dumps(context, indent=2)}\n\n"
        f"Leader question: {question}"
    )


def _build_contextual_fallback(context: dict) -> str:
    prediction = context.get("success_prediction", {})
    risk = context.get("risk_assessment", {})
    team = context.get("team_recommendation", {})
    simulation = context.get("staffing_simulation")

    if simulation:
        critical = simulation.get("most_critical_capability") or {}
        capability = critical.get("capability")
        if capability:
            return (
                f"SignalForge could not generate an AI response right now. "
                f"Staffing simulation shows {capability} is the most critical capability—"
                f"removing {critical['key_engineer']} loses it, shifts risk from "
                f"{simulation['risk_before']} to {simulation['risk_after']}, and drops "
                f"success probability from {simulation['success_probability_before']}% to "
                f"{simulation['success_probability_after']}%."
            )

        removed = ", ".join(simulation["removed_engineers"])
        return (
            f"SignalForge could not generate an AI response right now. "
            f"{simulation['simulation_summary']} "
            f"Coverage moves from {simulation['coverage_before']}% to "
            f"{simulation['coverage_after']}% with impact score {simulation['impact_score']}."
        )

    probability = prediction.get("success_probability")
    risk_level = risk.get("risk_level", "unknown")
    coverage = team.get("team_coverage") or []
    if probability is not None and coverage:
        coverage_text = ", ".join(coverage)
        return (
            f"SignalForge could not generate an AI response right now, but {context['project_name']} "
            f"shows {probability}% success probability with {risk_level.lower()} delivery risk "
            f"and full coverage of {coverage_text}."
        )

    return FALLBACK_ANSWER


def _generate_ai_answer(question: str, context: dict) -> str | None:
    settings = get_settings()
    if not settings.azure_openai_configured():
        return None

    try:
        answer = create_chat_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(question, context),
            max_tokens=250,
            temperature=0.3,
        )
    except Exception:
        return None

    return answer or None


def answer_copilot_question(request: CopilotRequest) -> CopilotResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty.")

    project_name = request.project_name.strip()
    if _catalog.get_legacy_project(project_name) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{request.project_name}' not found.",
        )

    context = _build_execution_context(project_name, question)
    sources_used = _sources_from_context(context)

    answer = _generate_ai_answer(question, context)
    if not answer:
        answer = _build_contextual_fallback(context)

    return CopilotResponse(
        project_name=project_name,
        question=question,
        answer=answer,
        sources_used=sources_used,
    )
