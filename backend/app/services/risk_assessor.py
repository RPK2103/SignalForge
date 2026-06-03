from app.schemas.engineer import EngineerProfile
from app.schemas.risk import (
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskProjectRequirements,
)


def _has_skill(skills: list[str], target: str) -> bool:
    target_lower = target.lower()
    return any(skill.lower() == target_lower for skill in skills)


def _contains_keyword(items: list[str], keyword: str) -> bool:
    keyword_lower = keyword.lower()
    return any(keyword_lower in item.lower() for item in items)


def _is_skill_matched(required: str, profile: EngineerProfile) -> bool:
    if _has_skill(profile.skills, required):
        return True
    if _contains_keyword(profile.certifications, required):
        return True
    if _contains_keyword(profile.projects, required):
        return True
    return False


def _missing_required_skills(required_skills: list[str], profile: EngineerProfile) -> list[str]:
    return [skill for skill in required_skills if not _is_skill_matched(skill, profile)]


def _risk_level_for_score(score: int) -> str:
    if score <= 30:
        return "Low"
    if score <= 60:
        return "Medium"
    return "High"


def _mitigation_for_level(level: str) -> list[str]:
    if level == "Low":
        return [
            "Assign the engineer to the project with light review from a lead.",
            "Schedule a brief kickoff to confirm scope and expectations.",
        ]
    if level == "Medium":
        return [
            "Pair the engineer with a senior engineer for the first sprint.",
            "Plan upskilling sessions for missing required capabilities.",
            "Increase code review coverage until gaps are closed.",
        ]
    return [
        "Do not assign as the primary project owner.",
        "Create a support plan with a senior engineer owning critical deliverables.",
        "Define milestones and checkpoints before expanding ownership.",
    ]


def _build_reasoning(
    profile: EngineerProfile,
    project: RiskProjectRequirements,
    risk_score: int,
    risk_level: str,
    missing: list[str],
) -> str:
    if not project.required_skills:
        return (
            f"{profile.name} faces {risk_level.lower()} risk ({risk_score}/100) on {project.name} "
            f"because the project has no required skills to validate against the profile."
        )

    if missing:
        missing_text = ", ".join(missing)
        return (
            f"{profile.name} faces {risk_level.lower()} risk ({risk_score}/100) on {project.name} "
            f"due to gaps in required skills: {missing_text}."
        )

    if risk_score == 0:
        return (
            f"{profile.name} faces low risk ({risk_score}/100) on {project.name} "
            f"because all required skills are covered with sufficient supporting evidence."
        )

    return (
        f"{profile.name} faces {risk_level.lower()} risk ({risk_score}/100) on {project.name} "
        f"with all required skills covered, but experience or evidence gaps still elevate exposure."
    )


def assess_risk(request: RiskAssessmentRequest) -> RiskAssessmentResponse:
    profile = request.engineer
    project = request.project

    risks: list[str] = []
    score = 0

    missing = _missing_required_skills(project.required_skills, profile)
    for skill in missing:
        score += 25
        risks.append(f"Missing required skill: {skill} (+25 risk)")

    if profile.experience < 2:
        score += 20
        risks.append(f"Experience under 2 years ({profile.experience} years) (+20 risk)")

    if not profile.certifications:
        score += 10
        risks.append("No certifications on profile (+10 risk)")

    if not profile.projects:
        score += 15
        risks.append("No prior projects listed (+15 risk)")

    if project.required_skills and not missing:
        score -= 10
        risks.append("All required skills matched (-10 risk)")

    risk_score = max(0, min(100, score))
    risk_level = _risk_level_for_score(risk_score)
    mitigation_plan = _mitigation_for_level(risk_level)
    reasoning = _build_reasoning(profile, project, risk_score, risk_level, missing)

    return RiskAssessmentResponse(
        engineer_name=profile.name,
        project_name=project.name,
        risk_score=risk_score,
        risk_level=risk_level,
        risks=risks,
        mitigation_plan=mitigation_plan,
        reasoning=reasoning,
    )
