from app.schemas.engineer import EngineerAnalysis, EngineerProfile

DIMENSION_LABELS = {
    "execution": "Execution",
    "backend": "Backend",
    "cloud": "Cloud",
    "ai_readiness": "AI Readiness",
}


def _cap(score: int) -> int:
    return min(100, score)


def _has_skill(skills: list[str], target: str) -> bool:
    target_lower = target.lower()
    return any(skill.lower() == target_lower for skill in skills)


def _cert_contains(certifications: list[str], keyword: str) -> bool:
    keyword_lower = keyword.lower()
    return any(keyword_lower in cert.lower() for cert in certifications)


def _count_certs_with_keywords(certifications: list[str], keywords: list[str]) -> int:
    count = 0
    for cert in certifications:
        cert_lower = cert.lower()
        if any(keyword.lower() in cert_lower for keyword in keywords):
            count += 1
    return count


def _score_execution(profile: EngineerProfile) -> int:
    return _cap(int(profile.experience * 20 + len(profile.projects) * 10))


def _score_backend(profile: EngineerProfile) -> int:
    score = 0
    if _has_skill(profile.skills, "Java") or _has_skill(profile.skills, "Spring Boot"):
        score += 30
    if _has_skill(profile.skills, "Python"):
        score += 20
    return _cap(score)


def _score_cloud(profile: EngineerProfile) -> int:
    score = 0
    if _has_skill(profile.skills, "Azure"):
        score += 40
    score += _count_certs_with_keywords(profile.certifications, ["Cloud", "Azure"]) * 20
    return _cap(score)


def _score_ai_readiness(profile: EngineerProfile) -> int:
    score = 0
    if _cert_contains(profile.certifications, "Generative AI"):
        score += 50
    if _has_skill(profile.skills, "Python"):
        score += 20
    return _cap(score)


def _collect_strengths(scores: dict[str, int]) -> list[str]:
    return [DIMENSION_LABELS[key] for key, value in scores.items() if value >= 60]


def _collect_risks(scores: dict[str, int]) -> list[str]:
    return [DIMENSION_LABELS[key] for key, value in scores.items() if value < 40]


def _generate_summary(name: str, scores: dict[str, int]) -> str:
    execution = scores["execution"]
    backend = scores["backend"]
    cloud = scores["cloud"]
    ai_readiness = scores["ai_readiness"]

    if execution >= 60:
        execution_level = "strong"
    elif execution >= 40:
        execution_level = "moderate"
    else:
        execution_level = "limited"

    strongest = max(
        ("backend", backend),
        ("cloud", cloud),
        ("AI readiness", ai_readiness),
        key=lambda item: item[1],
    )
    weakest = min(
        ("backend", backend),
        ("cloud", cloud),
        ("AI readiness", ai_readiness),
        key=lambda item: item[1],
    )

    return (
        f"{name} shows {execution_level} execution capability ({execution}/100) "
        f"based on {profile_years_hint(execution)}. "
        f"Strongest area: {strongest[0]} ({strongest[1]}/100). "
        f"Area needing attention: {weakest[0]} ({weakest[1]}/100)."
    )


def profile_years_hint(execution: int) -> str:
    if execution >= 80:
        return "extensive experience and project delivery"
    if execution >= 60:
        return "solid experience and project history"
    if execution >= 40:
        return "some experience and limited project evidence"
    return "limited experience and project evidence"


def analyze_engineer(profile: EngineerProfile) -> EngineerAnalysis:
    scores = {
        "execution": _score_execution(profile),
        "backend": _score_backend(profile),
        "cloud": _score_cloud(profile),
        "ai_readiness": _score_ai_readiness(profile),
    }

    return EngineerAnalysis(
        name=profile.name,
        execution=scores["execution"],
        backend=scores["backend"],
        cloud=scores["cloud"],
        ai_readiness=scores["ai_readiness"],
        strengths=_collect_strengths(scores),
        risks=_collect_risks(scores),
        summary=_generate_summary(profile.name, scores),
    )
