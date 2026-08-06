"""Organization hierarchy and people catalog seeding."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import enterprise as orm
from app.demo.novabank import identities as idn
from app.demo.novabank.constants import FOUNDATIONAL_BASE
from app.demo.novabank.helpers import ensure, resolve_foundational_ids, tid


def seed_organization(session: Session, summary: dict[str, int]) -> dict[str, str]:
    ids = resolve_foundational_ids()
    org_id = ids["org"]
    summary["organizations"] += ensure(
        session,
        orm.Organization,
        org_id,
        {
            "organization_id": org_id,
            "name": "NovaBank",
            "slug": "novabank",
            "organization_type": "enterprise",
            "timezone_name": "UTC",
        },
    )
    for name, code in idn.BUSINESS_UNITS:
        bu_id = ids[f"bu:{code}"]
        summary["business_units"] += ensure(
            session,
            orm.BusinessUnit,
            bu_id,
            {
                "business_unit_id": bu_id,
                "organization_id": org_id,
                "name": name,
                "code": code,
                "valid_from": FOUNDATIONAL_BASE,
            },
        )
    for name, code, bu_code in idn.DEPARTMENTS:
        dept_id = ids[f"dept:{code}"]
        summary["departments"] += ensure(
            session,
            orm.Department,
            dept_id,
            {
                "department_id": dept_id,
                "business_unit_id": ids[f"bu:{bu_code}"],
                "name": name,
                "code": code,
                "created_at": FOUNDATIONAL_BASE,
                "updated_at": FOUNDATIONAL_BASE,
            },
        )
    for name, slug, dept_code, team_type, _mission in idn.TEAMS:
        team_id = ids[f"team:{slug}"]
        # Overcommitted platform team: lower spare capacity signal via points.
        capacity = 28 if slug == idn.OVERCOMMITTED_TEAM else 40
        summary["teams"] += ensure(
            session,
            orm.Team,
            team_id,
            {
                "team_id": team_id,
                "department_id": ids[f"dept:{dept_code}"],
                "name": name,
                "slug": slug,
                "team_type": team_type,
                "capacity_points": capacity,
                "created_at": FOUNDATIONAL_BASE,
                "updated_at": FOUNDATIONAL_BASE,
            },
        )
    return ids


def seed_people_and_catalog(session: Session, ids: dict[str, str], summary: dict[str, int]) -> None:
    for name, key, team_slug, level in idn.ENGINEERS:
        eng_id = ids[f"eng:{key}"]
        summary["engineers"] += ensure(
            session,
            orm.EngineerProfile,
            eng_id,
            {
                "engineer_profile_id": eng_id,
                "current_team_id": ids[f"team:{team_slug}"],
                "display_name": name,
                "role_title": f"{level.title()} Engineer",
                "level": level,
                "employment_state": "active",
                "region": "emea",
                "valid_from": FOUNDATIONAL_BASE,
            },
        )
    for name, slug, category in idn.CAPABILITIES:
        cap_id = ids[f"cap:{slug}"]
        summary["capabilities"] += ensure(
            session,
            orm.EnterpriseCapability,
            cap_id,
            {
                "capability_id": cap_id,
                "name": name,
                "slug": slug,
                "category": category,
                "description": f"{name} capability",
            },
        )
    for name, slug, category in idn.SKILLS:
        skill_id = ids[f"skill:{slug}"]
        summary["skills"] += ensure(
            session,
            orm.EnterpriseSkill,
            skill_id,
            {
                "skill_id": skill_id,
                "name": name,
                "slug": slug,
                "category": category,
                "description": f"{name} skill",
            },
        )
    for cap_slug, skill_slug in idn.CAPABILITY_SKILLS:
        link_id = tid("capskill", ids[f"cap:{cap_slug}"], ids[f"skill:{skill_slug}"])
        summary["capability_skills"] += ensure(
            session,
            orm.CapabilitySkill,
            link_id,
            {
                "capability_skill_id": link_id,
                "capability_id": ids[f"cap:{cap_slug}"],
                "skill_id": ids[f"skill:{skill_slug}"],
            },
        )
    cap_slugs = [c[1] for c in idn.CAPABILITIES]
    skill_slugs = [s[1] for s in idn.SKILLS]
    for index, (_name, key, _team, _level) in enumerate(idn.ENGINEERS):
        for offset in (0, 1):
            cap_slug = cap_slugs[(index + offset) % len(cap_slugs)]
            valid_from = FOUNDATIONAL_BASE
            ev_id = tid("capev", ids[f"eng:{key}"], ids[f"cap:{cap_slug}"], valid_from.isoformat())
            summary["capability_evidence"] += ensure(
                session,
                orm.EngineerCapabilityEvidence,
                ev_id,
                {
                    "evidence_id": ev_id,
                    "engineer_profile_id": ids[f"eng:{key}"],
                    "capability_id": ids[f"cap:{cap_slug}"],
                    "proficiency": 55 + ((index * 7 + offset * 13) % 40),
                    "source": "imported",
                    "confidence": 0.9,
                    "valid_from": valid_from,
                },
            )
        skill_slug = skill_slugs[index % len(skill_slugs)]
        sev_id = tid(
            "skillev",
            ids[f"eng:{key}"],
            ids[f"skill:{skill_slug}"],
            FOUNDATIONAL_BASE.isoformat(),
        )
        summary["skill_evidence"] += ensure(
            session,
            orm.EngineerSkillEvidence,
            sev_id,
            {
                "evidence_id": sev_id,
                "engineer_profile_id": ids[f"eng:{key}"],
                "skill_id": ids[f"skill:{skill_slug}"],
                "proficiency": 50 + (index * 5) % 45,
                "source": "imported",
                "confidence": 0.85,
                "valid_from": FOUNDATIONAL_BASE,
            },
        )
    # Capability requirements for story initiatives (azure shortage, fraud, copilot).
    requirements = [
        ("init:azure-migration", "azure-platform", 85, "critical"),
        ("init:fraud-detection-uplift", "fraud-modeling", 80, "critical"),
        ("init:customer-copilot-launch", "customer-copilot-ai", 80, "critical"),
        ("init:customer-copilot-launch", "identity-platform", 70, "high"),
        ("init:payment-modernization", "payments-processing", 75, "critical"),
        ("init:identity-resilience", "identity-platform", 80, "critical"),
        ("proj:core-banking-azure", "azure-platform", 85, "critical"),
        ("proj:fraud-scoring-v2", "fraud-modeling", 80, "critical"),
        ("proj:copilot-orchestration", "customer-copilot-ai", 80, "high"),
        ("proj:rt-payments-rail", "payment-apis", 60, "medium"),
    ]
    for target_key, cap_slug, level, criticality in requirements:
        if target_key.startswith("init:"):
            subject_type, subject_id = "initiative", ids[target_key]
        else:
            subject_type, subject_id = "project", ids[target_key]
        req_id = tid("capreq", subject_type, subject_id, ids[f"cap:{cap_slug}"])
        summary["capability_requirements"] += ensure(
            session,
            orm.CapabilityRequirement,
            req_id,
            {
                "requirement_id": req_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "capability_id": ids[f"cap:{cap_slug}"],
                "required_level": level,
                "criticality": criticality,
                "source": "imported",
                "confidence": 0.9,
            },
        )
