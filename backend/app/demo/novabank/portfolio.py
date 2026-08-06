"""Portfolio seeding: initiatives, projects, repositories."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import enterprise as orm
from app.demo.novabank import identities as idn
from app.demo.novabank.helpers import dt_from_base, ensure


def seed_portfolio(session: Session, ids: dict[str, str], summary: dict[str, int]) -> None:
    for name, slug, priority, criticality in idn.INITIATIVES:
        init_id = ids[f"init:{slug}"]
        # Stale-evidence initiative keeps earlier planned window for story-04.
        planned_target = (
            dt_from_base(200) if slug != idn.STALE_EVIDENCE_INITIATIVE else dt_from_base(90)
        )
        summary["initiatives"] += ensure(
            session,
            orm.Initiative,
            init_id,
            {
                "initiative_id": init_id,
                "organization_id": ids["org"],
                "name": name,
                "slug": slug,
                "description": f"{name} initiative for NovaBank (synthetic).",
                "strategic_priority": priority,
                "criticality": criticality,
                "status": "active",
                "planned_start": dt_from_base(0),
                "planned_target": planned_target,
                # Deterministic persistence timestamps (no wall clock).
                "created_at": dt_from_base(0),
                "updated_at": dt_from_base(0),
            },
        )
    for name, slug, init_slug, team_slug in idn.PROJECTS:
        proj_id = ids[f"proj:{slug}"]
        summary["projects"] += ensure(
            session,
            orm.EnterpriseProject,
            proj_id,
            {
                "enterprise_project_id": proj_id,
                "initiative_id": ids[f"init:{init_slug}"],
                "owning_team_id": ids[f"team:{team_slug}"],
                "legacy_project_id": None,
                "name": name,
                "slug": slug,
                "status": "active",
                "criticality": "high",
                "planned_start": dt_from_base(0),
                "planned_target": dt_from_base(120),
                "created_at": dt_from_base(0),
                "updated_at": dt_from_base(0),
            },
        )
    for name, team_slug in idn.REPOSITORIES:
        repo_id = ids[f"repo:{name}"]
        summary["repositories"] += ensure(
            session,
            orm.Repository,
            repo_id,
            {
                "repository_id": repo_id,
                "owning_team_id": ids[f"team:{team_slug}"],
                "provider": "github",
                "external_reference": f"novabank/{name}",
                "name": name,
                "default_branch": "main",
                "visibility": "private",
                "state": "active",
                "created_at": dt_from_base(0),
                "updated_at": dt_from_base(0),
            },
        )
