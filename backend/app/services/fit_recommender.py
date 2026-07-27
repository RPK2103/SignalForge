from app.schemas.engineer import EngineerProfile
from app.schemas.project_fit import ProjectFitRequest, ProjectFitResult, ProjectRequirements


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


def _match_sources(required: str, profile: EngineerProfile) -> list[str]:
    sources: list[str] = []
    if _has_skill(profile.skills, required):
        sources.append("skills")
    if _contains_keyword(profile.certifications, required):
        sources.append("certifications")
    if _contains_keyword(profile.projects, required):
        sources.append("projects")
    return sources


def _recommendation_for_score(score: int) -> str:
    if score >= 80:
        return "Strong Fit"
    if score >= 60:
        return "Good Fit"
    if score >= 40:
        return "Moderate Fit"
    if score >= 20:
        return "Weak Fit"
    return "Not Recommended"


def _score_fit(
    required_skills: list[str], profile: EngineerProfile
) -> tuple[int, list[str], list[str]]:
    if not required_skills:
        return 100, [], []

    matched: list[str] = []
    missing: list[str] = []

    for skill in required_skills:
        if _is_skill_matched(skill, profile):
            matched.append(skill)
        else:
            missing.append(skill)

    fit_score = round(len(matched) / len(required_skills) * 100)
    return fit_score, matched, missing


def _build_reasoning(
    profile: EngineerProfile,
    project: ProjectRequirements,
    fit_score: int,
    recommendation: str,
    matched: list[str],
    missing: list[str],
) -> str:
    if not project.required_skills:
        return (
            f"{profile.name} is considered for {project.name} with no specific skill requirements. "
            f"Assign a default fit score of {fit_score}/100 ({recommendation})."
        )

    evidence_parts: list[str] = []
    for skill in matched:
        sources = _match_sources(skill, profile)
        evidence_parts.append(f"{skill} (via {', '.join(sources)})")

    matched_text = ", ".join(evidence_parts) if evidence_parts else "none"
    missing_text = ", ".join(missing) if missing else "none"

    return (
        f"{profile.name} scores {fit_score}/100 for {project.name} ({recommendation}). "
        f"Matched {len(matched)} of {len(project.required_skills)} "
        f"required skills: {matched_text}. "
        f"Missing skills: {missing_text}."
    )


def recommend_project_fit(request: ProjectFitRequest) -> ProjectFitResult:
    profile = request.engineer
    project = request.project

    fit_score, matched, missing = _score_fit(project.required_skills, profile)
    recommendation = _recommendation_for_score(fit_score)
    reasoning = _build_reasoning(profile, project, fit_score, recommendation, matched, missing)

    return ProjectFitResult(
        engineer_name=profile.name,
        project_name=project.name,
        fit_score=fit_score,
        recommendation=recommendation,
        matched_skills=matched,
        missing_skills=missing,
        reasoning=reasoning,
    )
