"""Deterministic, idempotent NovaBank enterprise demo seed (Phase 3 Prompt 1).

NovaBank is a fictional bank used as the Phase 3 demo tenant. This is a bounded
FOUNDATIONAL sample (not the full Prompt 9 scenario scale). All identifiers are
deterministic (derived from the tenant + a natural key), all names are fictional,
and there is NO real, scraped or sensitive employee data.

Idempotency: every row is created only if its deterministic primary key is
absent, so a second run creates zero duplicates.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import enterprise as orm
from app.db.session import init_engine, session_scope
from app.domain.enterprise_identifiers import build_entity_id
from app.services.persistence.snapshot_service import snapshot_hash

TENANT_ID = "novabank"
_BASE = datetime(2026, 1, 6, 9, 0, 0, tzinfo=timezone.utc)


def _dt(days: int = 0, hours: int = 0) -> datetime:
    return _BASE + timedelta(days=days, hours=hours)


# ---------------------------------------------------------------------------
# Deterministic fictional dataset definitions
# ---------------------------------------------------------------------------
BUSINESS_UNITS = [
    ("Retail Banking", "retail-banking"),
    ("Enterprise Platforms", "enterprise-platforms"),
]

DEPARTMENTS = [
    ("Payments Engineering", "payments-eng", "retail-banking"),
    ("Digital Channels", "digital-channels", "retail-banking"),
    ("Cloud Platform", "cloud-platform", "enterprise-platforms"),
    ("Data & Fraud", "data-fraud", "enterprise-platforms"),
]

TEAMS = [
    ("Payments Core", "payments-core", "payments-eng", "product"),
    ("Payments Rails", "payments-rails", "payments-eng", "product"),
    ("Mobile Banking", "mobile-banking", "digital-channels", "product"),
    ("Cloud Foundations", "cloud-foundations", "cloud-platform", "platform"),
    ("Site Reliability", "site-reliability", "cloud-platform", "sre"),
    ("Fraud Detection", "fraud-detection", "data-fraud", "data"),
]

# 15 synthetic engineers (fictional names / pseudonymous keys).
ENGINEERS = [
    ("Ada Nguyen", "eng-01", "payments-core", "senior"),
    ("Ben Carter", "eng-02", "payments-core", "mid"),
    ("Chloe Park", "eng-03", "payments-rails", "staff"),
    ("Diego Ruiz", "eng-04", "payments-rails", "mid"),
    ("Ezra Cohen", "eng-05", "mobile-banking", "senior"),
    ("Farah Idris", "eng-06", "mobile-banking", "junior"),
    ("Gita Rao", "eng-07", "cloud-foundations", "principal"),
    ("Hugo Silva", "eng-08", "cloud-foundations", "senior"),
    ("Ivy Chen", "eng-09", "cloud-foundations", "mid"),
    ("Jonas Weber", "eng-10", "site-reliability", "staff"),
    ("Kira Novak", "eng-11", "site-reliability", "mid"),
    ("Liam Osei", "eng-12", "fraud-detection", "senior"),
    ("Maya Kapoor", "eng-13", "fraud-detection", "senior"),
    ("Noah Kim", "eng-14", "fraud-detection", "mid"),
    ("Olivia Braun", "eng-15", "payments-core", "junior"),
]

CAPABILITIES = [
    ("Payments Processing", "payments-processing", "backend"),
    ("Cloud Architecture", "cloud-architecture", "cloud"),
    ("Azure Platform", "azure-platform", "cloud"),
    ("Fraud Modeling", "fraud-modeling", "ai"),
    ("Data Engineering", "data-engineering", "data"),
    ("Site Reliability", "site-reliability", "devops"),
    ("Mobile Engineering", "mobile-engineering", "backend"),
    ("Security Engineering", "security-engineering", "security"),
]

SKILLS = [
    ("Kubernetes", "kubernetes", "cloud"),
    ("Terraform", "terraform", "cloud"),
    ("Kafka", "kafka", "backend"),
    ("Python", "python", "backend"),
    ("Spark", "spark", "data"),
    ("Kotlin", "kotlin", "backend"),
    ("Threat Modeling", "threat-modeling", "security"),
    ("Observability", "observability", "devops"),
]

CAPABILITY_SKILLS = [
    ("cloud-architecture", "kubernetes"),
    ("cloud-architecture", "terraform"),
    ("azure-platform", "terraform"),
    ("payments-processing", "kafka"),
    ("payments-processing", "python"),
    ("fraud-modeling", "spark"),
    ("mobile-engineering", "kotlin"),
    ("security-engineering", "threat-modeling"),
    ("site-reliability", "observability"),
]

INITIATIVES = [
    ("Payment Modernization", "payment-modernization", "critical", "critical"),
    ("Azure Migration", "azure-migration", "high", "high"),
    ("Fraud Detection Uplift", "fraud-detection-uplift", "high", "high"),
    ("Mobile Refresh", "mobile-refresh", "medium", "medium"),
    ("Reliability Program", "reliability-program", "medium", "high"),
]

PROJECTS = [
    ("Real-Time Payments Rail", "rt-payments-rail", "payment-modernization", "payments-rails"),
    ("Ledger Modernization", "ledger-modernization", "payment-modernization", "payments-core"),
    ("Core Banking to Azure", "core-banking-azure", "azure-migration", "cloud-foundations"),
    ("Data Lake Migration", "data-lake-migration", "azure-migration", "fraud-detection"),
    ("Fraud Scoring v2", "fraud-scoring-v2", "fraud-detection-uplift", "fraud-detection"),
    ("Mobile App 4.0", "mobile-app-4", "mobile-refresh", "mobile-banking"),
    ("SLO Platform", "slo-platform", "reliability-program", "site-reliability"),
    ("Payments Observability", "payments-observability", "reliability-program", "payments-core"),
]

REPOSITORIES = [
    ("payments-core-svc", "cloud-foundations"),
    ("payments-rails-svc", "payments-rails"),
    ("ledger-svc", "payments-core"),
    ("mobile-android", "mobile-banking"),
    ("mobile-ios", "mobile-banking"),
    ("cloud-landing-zone", "cloud-foundations"),
    ("fraud-scoring", "fraud-detection"),
    ("data-lake-pipelines", "fraud-detection"),
    ("slo-controller", "site-reliability"),
    ("observability-stack", "site-reliability"),
]

DATA_SOURCES = [
    ("github", "NovaBank GitHub Org"),
    ("jira", "NovaBank Jira"),
    ("azure_devops", "NovaBank Azure DevOps"),
]


def _tid(prefix: str, *parts: str) -> str:
    return build_entity_id(prefix, TENANT_ID, *parts)


def _ensure(session: Session, model, pk_value: str, columns: dict) -> int:
    if session.get(model, pk_value) is not None:
        return 0
    session.add(model(tenant_id=TENANT_ID, **columns))
    # Flush immediately so foreign-key targets exist for later child rows
    # (the session runs with autoflush disabled).
    session.flush()
    return 1


def _seed_hierarchy(session: Session, summary: dict) -> dict[str, str]:
    ids: dict[str, str] = {}
    org_id = _tid("org", "novabank")
    ids["org"] = org_id
    summary["organizations"] += _ensure(
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
    for name, code in BUSINESS_UNITS:
        bu_id = _tid("bu", code)
        ids[f"bu:{code}"] = bu_id
        summary["business_units"] += _ensure(
            session,
            orm.BusinessUnit,
            bu_id,
            {
                "business_unit_id": bu_id,
                "organization_id": org_id,
                "name": name,
                "code": code,
                "valid_from": _BASE,
            },
        )
    for name, code, bu_code in DEPARTMENTS:
        dept_id = _tid("dept", code)
        ids[f"dept:{code}"] = dept_id
        summary["departments"] += _ensure(
            session,
            orm.Department,
            dept_id,
            {
                "department_id": dept_id,
                "business_unit_id": ids[f"bu:{bu_code}"],
                "name": name,
                "code": code,
            },
        )
    for name, slug, dept_code, team_type in TEAMS:
        team_id = _tid("team", slug)
        ids[f"team:{slug}"] = team_id
        summary["teams"] += _ensure(
            session,
            orm.Team,
            team_id,
            {
                "team_id": team_id,
                "department_id": ids[f"dept:{dept_code}"],
                "name": name,
                "slug": slug,
                "team_type": team_type,
                "capacity_points": 40,
            },
        )
    return ids


def _seed_people_and_catalog(session: Session, ids: dict[str, str], summary: dict) -> None:
    for name, key, team_slug, level in ENGINEERS:
        eng_id = _tid("eng", key)
        ids[f"eng:{key}"] = eng_id
        summary["engineers"] += _ensure(
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
                "valid_from": _BASE,
            },
        )
    for name, slug, category in CAPABILITIES:
        cap_id = _tid("cap", slug)
        ids[f"cap:{slug}"] = cap_id
        summary["capabilities"] += _ensure(
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
    for name, slug, category in SKILLS:
        skill_id = _tid("skill", slug)
        ids[f"skill:{slug}"] = skill_id
        summary["skills"] += _ensure(
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
    for cap_slug, skill_slug in CAPABILITY_SKILLS:
        link_id = _tid("capskill", ids[f"cap:{cap_slug}"], ids[f"skill:{skill_slug}"])
        summary["capability_skills"] += _ensure(
            session,
            orm.CapabilitySkill,
            link_id,
            {
                "capability_skill_id": link_id,
                "capability_id": ids[f"cap:{cap_slug}"],
                "skill_id": ids[f"skill:{skill_slug}"],
            },
        )
    # Deterministic engineer -> capability evidence (two capabilities per engineer).
    cap_slugs = [c[1] for c in CAPABILITIES]
    for index, (_name, key, _team, _level) in enumerate(ENGINEERS):
        for offset in (0, 1):
            cap_slug = cap_slugs[(index + offset) % len(cap_slugs)]
            valid_from = _BASE
            ev_id = _tid("capev", ids[f"eng:{key}"], ids[f"cap:{cap_slug}"], valid_from.isoformat())
            summary["capability_evidence"] += _ensure(
                session,
                orm.EngineerCapabilityEvidence,
                ev_id,
                {
                    "evidence_id": ev_id,
                    "engineer_profile_id": ids[f"eng:{key}"],
                    "capability_id": ids[f"cap:{cap_slug}"],
                    "proficiency": 60 + ((index * 7 + offset * 13) % 40),
                    "source": "imported",
                    "confidence": 0.9,
                    "valid_from": valid_from,
                },
            )


def _seed_initiatives_projects(session: Session, ids: dict[str, str], summary: dict) -> None:
    for name, slug, priority, criticality in INITIATIVES:
        init_id = _tid("init", slug)
        ids[f"init:{slug}"] = init_id
        summary["initiatives"] += _ensure(
            session,
            orm.Initiative,
            init_id,
            {
                "initiative_id": init_id,
                "organization_id": ids["org"],
                "name": name,
                "slug": slug,
                "description": f"{name} initiative for NovaBank.",
                "strategic_priority": priority,
                "criticality": criticality,
                "status": "active",
                "planned_start": _dt(0),
                "planned_target": _dt(180),
            },
        )
    for name, slug, init_slug, team_slug in PROJECTS:
        proj_id = _tid("proj", slug)
        ids[f"proj:{slug}"] = proj_id
        summary["projects"] += _ensure(
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
                "planned_start": _dt(0),
                "planned_target": _dt(120),
            },
        )


def _seed_delivery(session: Session, ids: dict[str, str], summary: dict) -> None:
    for name, team_slug in REPOSITORIES:
        repo_id = _tid("repo", "github", f"novabank/{name}")
        ids[f"repo:{name}"] = repo_id
        summary["repositories"] += _ensure(
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
            },
        )
    team_slugs = [t[1] for t in TEAMS]
    for sprint_index in range(6):
        team_slug = team_slugs[sprint_index % len(team_slugs)]
        name = f"Sprint {sprint_index + 1}"
        sprint_id = _tid("sprint", ids[f"team:{team_slug}"], name)
        ids[f"sprint:{sprint_index}"] = sprint_id
        summary["sprints"] += _ensure(
            session,
            orm.Sprint,
            sprint_id,
            {
                "sprint_id": sprint_id,
                "team_id": ids[f"team:{team_slug}"],
                "name": name,
                "start_time": _dt(sprint_index * 14),
                "end_time": _dt(sprint_index * 14 + 14),
                "state": "closed" if sprint_index < 4 else "active",
            },
        )
    project_slugs = [p[1] for p in PROJECTS]
    statuses = ["backlog", "in_progress", "in_review", "done"]
    priorities = ["p0", "p1", "p2", "p3"]
    types = ["story", "task", "bug", "spike"]
    for n in range(30):
        proj_slug = project_slugs[n % len(project_slugs)]
        ref = f"NB-{100 + n}"
        wi_id = _tid("wi", "jira", ref)
        summary["work_items"] += _ensure(
            session,
            orm.WorkItem,
            wi_id,
            {
                "work_item_id": wi_id,
                "enterprise_project_id": ids[f"proj:{proj_slug}"],
                "sprint_id": ids[f"sprint:{n % 6}"],
                "provider": "jira",
                "external_reference": ref,
                "work_item_type": types[n % len(types)],
                "status": statuses[n % len(statuses)],
                "priority": priorities[n % len(priorities)],
                "source_created_at": _dt(n),
                "source_updated_at": _dt(n, 4),
                "completed_at": _dt(n, 8) if statuses[n % len(statuses)] == "done" else None,
            },
        )
    repo_names = [r[0] for r in REPOSITORIES]
    severities = ["sev1", "sev2", "sev3", "sev4"]
    for n in range(4):
        ref = f"INC-{200 + n}"
        inc_id = _tid("inc", "manual", ref)
        summary["incidents"] += _ensure(
            session,
            orm.Incident,
            inc_id,
            {
                "incident_id": inc_id,
                "repository_id": ids[f"repo:{repo_names[n % len(repo_names)]}"],
                "provider": "manual",
                "external_reference": ref,
                "severity": severities[n % len(severities)],
                "started_at": _dt(20 + n),
                "resolved_at": _dt(20 + n, 6),
                "state": "resolved",
            },
        )
    for n in range(10):
        ref = f"deploy-{300 + n}"
        dep_id = _tid("deploy", "github", ref)
        summary["deployments"] += _ensure(
            session,
            orm.Deployment,
            dep_id,
            {
                "deployment_id": dep_id,
                "repository_id": ids[f"repo:{repo_names[n % len(repo_names)]}"],
                "provider": "github",
                "external_reference": ref,
                "environment": "production" if n % 2 == 0 else "staging",
                "status": "succeeded" if n % 3 else "failed",
                "started_at": _dt(30 + n),
                "completed_at": _dt(30 + n, 1),
            },
        )


def _seed_relationships(session: Session, ids: dict[str, str], summary: dict) -> None:
    # Payment-modernization dependency risk + Azure migration coupling.
    dependencies = [
        ("project", "proj:rt-payments-rail", "project", "proj:ledger-modernization", "depends_on"),
        ("project", "proj:ledger-modernization", "project", "proj:core-banking-azure", "blocks"),
        ("project", "proj:fraud-scoring-v2", "project", "proj:data-lake-migration", "depends_on"),
        (
            "repository",
            "repo:payments-rails-svc",
            "repository",
            "repo:ledger-svc",
            "integrates_with",
        ),
        (
            "team",
            "team:payments-rails",
            "capability",
            "cap:payments-processing",
            "shares_capability",
        ),
        ("project", "proj:mobile-app-4", "repository", "repo:mobile-android", "depends_on"),
    ]
    for s_type, s_key, t_type, t_key, dep_type in dependencies:
        s_id = ids[s_key]
        t_id = ids[t_key]
        dep_id = _tid("dep", s_type, s_id, t_type, t_id, dep_type)
        summary["dependencies"] += _ensure(
            session,
            orm.Dependency,
            dep_id,
            {
                "dependency_id": dep_id,
                "source_type": s_type,
                "source_id": s_id,
                "target_type": t_type,
                "target_id": t_id,
                "dependency_type": dep_type,
                "criticality": "high",
                "valid_from": _BASE,
                "evidence_reference": None,
                "status": "active",
            },
        )
    # Ownership: teams own repositories; fraud ownership concentration on Maya.
    ownerships = [
        ("team", "team:cloud-foundations", "repository", "repo:payments-core-svc", "primary"),
        ("team", "team:payments-rails", "repository", "repo:payments-rails-svc", "primary"),
        ("team", "team:mobile-banking", "repository", "repo:mobile-android", "primary"),
        ("team", "team:fraud-detection", "repository", "repo:fraud-scoring", "primary"),
        ("engineer_profile", "eng:eng-13", "repository", "repo:fraud-scoring", "primary"),
        ("engineer_profile", "eng:eng-13", "repository", "repo:data-lake-pipelines", "primary"),
        ("engineer_profile", "eng:eng-12", "repository", "repo:fraud-scoring", "secondary"),
        ("team", "team:site-reliability", "repository", "repo:slo-controller", "primary"),
    ]
    for o_type, o_key, r_type, r_key, own_type in ownerships:
        o_id = ids[o_key]
        r_id = ids[r_key]
        own_id = _tid("own", o_type, o_id, r_type, r_id, own_type)
        summary["ownership"] += _ensure(
            session,
            orm.Ownership,
            own_id,
            {
                "ownership_id": own_id,
                "owner_type": o_type,
                "owner_id": o_id,
                "resource_type": r_type,
                "resource_id": r_id,
                "ownership_type": own_type,
                "allocation": 100 if own_type == "primary" else 50,
                "valid_from": _BASE,
                "evidence_reference": None,
            },
        )
    # Availability: incident-driven capacity reduction for SRE + Azure shortage.
    availabilities = [
        ("engineer_profile", "eng:eng-10", 40, "incident_response"),
        ("engineer_profile", "eng:eng-11", 60, "incident_response"),
        ("engineer_profile", "eng:eng-07", 50, "allocation"),
        ("engineer_profile", "eng:eng-08", 70, "allocation"),
        ("engineer_profile", "eng:eng-06", 0, "planned_leave"),
        ("team", "team:cloud-foundations", 65, "allocation"),
    ]
    for t_type, t_key, pct, reason in availabilities:
        t_id = ids[t_key]
        start = _dt(15)
        avail_id = _tid("avail", t_type, t_id, start.isoformat())
        summary["availability"] += _ensure(
            session,
            orm.Availability,
            avail_id,
            {
                "availability_id": avail_id,
                "target_type": t_type,
                "target_id": t_id,
                "availability_percentage": pct,
                "capacity_units": None,
                "start_time": start,
                "end_time": _dt(45),
                "reason": reason,
                "source": "imported",
                "confidence": 0.8,
            },
        )


def _seed_provenance(session: Session, ids: dict[str, str], summary: dict) -> None:
    for source_type, display_name in DATA_SOURCES:
        ds_id = _tid("ds", source_type, display_name)
        ids[f"ds:{source_type}"] = ds_id
        summary["data_sources"] += _ensure(
            session,
            orm.DataSource,
            ds_id,
            {
                "data_source_id": ds_id,
                "source_type": source_type,
                "display_name": display_name,
                # Opaque future-safe reference; NOT a secret and NOT yet connected.
                "credential_reference": f"vault://novabank/{source_type}#deferred",
                "config_reference": None,
                "status": "registered",
                "permission_classification": "internal",
            },
        )
    run_specs = [
        ("github", 0, "succeeded"),
        ("jira", 1, "succeeded"),
        ("azure_devops", 2, "partial"),
        ("github", 3, "succeeded"),
    ]
    run_ids: list[str] = []
    for source_type, seq, status in run_specs:
        ds_id = ids[f"ds:{source_type}"]
        run_id = _tid("run", ds_id, f"seed-{seq}")
        run_ids.append(run_id)
        summary["ingestion_runs"] += _ensure(
            session,
            orm.IngestionRun,
            run_id,
            {
                "ingestion_run_id": run_id,
                "data_source_id": ds_id,
                "run_type": "backfill",
                "status": status,
                "started_at": _dt(seq),
                "completed_at": _dt(seq, 1),
                "cursor": {"page": seq},
                "records_read": 20 + seq,
                "records_written": 18 + seq,
                "records_skipped": 2,
                "error_category": "none" if status == "succeeded" else "rate_limited",
                "error_summary": None if status == "succeeded" else "partial page fetched",
                "processing_version": "1",
            },
        )
    # 40 append-only evidence signals across sources and subjects.
    repo_names = [r[0] for r in REPOSITORIES]
    signal_types = ["commit", "pull_request", "code_review", "deployment_event"]
    for n in range(40):
        source_type = DATA_SOURCES[n % len(DATA_SOURCES)][0]
        ds_id = ids[f"ds:{source_type}"]
        run_id = run_ids[n % len(run_ids)]
        repo_name = repo_names[n % len(repo_names)]
        subject_id = ids[f"repo:{repo_name}"]
        signal_type = signal_types[n % len(signal_types)]
        source_record_id = f"{source_type}-rec-{n}"
        payload = {
            "kind": signal_type,
            "sequence": n,
            "repository": repo_name,
            "message": f"deterministic {signal_type} event {n}",
        }
        payload_hash = snapshot_hash(payload)
        sig_id = _tid("sig", ds_id, source_record_id, signal_type, payload_hash)
        summary["evidence_signals"] += _ensure(
            session,
            orm.EvidenceSignal,
            sig_id,
            {
                "evidence_signal_id": sig_id,
                "data_source_id": ds_id,
                "ingestion_run_id": run_id,
                "source_record_id": source_record_id,
                "signal_type": signal_type,
                "subject_type": "repository",
                "subject_id": subject_id,
                "event_time": _dt(n),
                "observed_at": _dt(n, 1),
                "ingested_at": _dt(n, 2),
                "schema_version": "1",
                "processing_version": "1",
                "confidence": 0.95,
                "permission_classification": "internal",
                "expires_at": None,
                "payload": payload,
                "payload_hash": payload_hash,
                "provenance": {"source_type": source_type},
            },
        )


_COUNT_KEYS = [
    "organizations",
    "business_units",
    "departments",
    "teams",
    "engineers",
    "capabilities",
    "skills",
    "capability_skills",
    "capability_evidence",
    "initiatives",
    "projects",
    "repositories",
    "sprints",
    "work_items",
    "incidents",
    "deployments",
    "dependencies",
    "ownership",
    "availability",
    "data_sources",
    "ingestion_runs",
    "evidence_signals",
]


def seed_enterprise(session: Session) -> dict[str, int]:
    """Idempotently seed the NovaBank demo tenant. Returns created-row counts."""
    summary = {key: 0 for key in _COUNT_KEYS}
    ids = _seed_hierarchy(session, summary)
    _seed_people_and_catalog(session, ids, summary)
    _seed_initiatives_projects(session, ids, summary)
    _seed_delivery(session, ids, summary)
    _seed_relationships(session, ids, summary)
    _seed_provenance(session, ids, summary)
    summary["total_created"] = sum(summary[key] for key in _COUNT_KEYS)
    return summary


def main() -> int:
    init_engine()
    try:
        with session_scope() as session:
            summary = seed_enterprise(session)
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"Enterprise seed failed: {exc}", file=sys.stderr)
        return 1
    print("NovaBank enterprise seed complete (created rows):")
    for key in _COUNT_KEYS:
        print(f"  {key}={summary[key]}")
    print(f"  total_created={summary['total_created']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
