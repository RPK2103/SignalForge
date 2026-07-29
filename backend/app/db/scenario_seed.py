"""Deterministic NovaBank continuous scenario seed (Phase 3 Prompt 5).

Idempotent: second run creates zero duplicates. Synthetic only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.enterprise_seed import TENANT_ID, _tid
from app.db.unit_of_work import UnitOfWork
from app.domain.scenario_enums import ScenarioKind, ScenarioTargetType
from app.domain.tenant_context import TenantContext
from app.services.scenarios.orchestration import ScenarioOrchestrationService

_BASE = datetime(2026, 1, 6, 9, 0, tzinfo=timezone.utc)
_AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _scenario_specs(ids: dict[str, str]) -> list[dict[str, Any]]:
    eng_fraud = ids["eng:eng-12"]  # Liam Osei — fraud-detection
    team_platform = ids["team:cloud-foundations"]
    repo_shared = ids["repo:cloud-landing-zone"]
    # Prefer a payment dependency if present; fall back to first dependency id later.
    dep_payment = ids.get("dep:payment-modernization")
    cap_azure = ids["cap:azure-platform"]
    project_rt = ids["proj:rt-payments-rail"]
    project_fraud = ids["proj:fraud-scoring-v2"]
    initiative_fraud = ids["init:fraud-detection-uplift"]
    initiative_payment = ids["init:payment-modernization"]
    repo_payments = ids["repo:payments-core-svc"]

    return [
        {
            "name": "FRAUD ENGINEER UNAVAILABLE",
            "description": "Key fraud-domain engineer unavailable for 30 days (synthetic).",
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": initiative_fraud,
            "kind": ScenarioKind.ENGINEER_UNAVAILABLE,
            "assumptions": {
                "engineer_id": eng_fraud,
                "unavailable_from": _AS_OF.isoformat(),
                "unavailable_until": (_AS_OF + timedelta(days=30)).isoformat(),
            },
        },
        {
            "name": "PLATFORM TEAM CAPACITY REDUCTION",
            "description": "Shared platform team capacity reduced by 40% (synthetic).",
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": initiative_payment,
            "kind": ScenarioKind.TEAM_CAPACITY_REDUCTION,
            "assumptions": {
                "team_id": team_platform,
                "reduction_percentage": 40,
                "effective_from": _AS_OF.isoformat(),
                "effective_until": (_AS_OF + timedelta(days=60)).isoformat(),
            },
        },
        {
            "name": "SHARED REPOSITORY UNAVAILABLE",
            "description": "Shared platform repository unavailable (synthetic).",
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": initiative_payment,
            "kind": ScenarioKind.REPOSITORY_UNAVAILABLE,
            "assumptions": {
                "repository_id": repo_shared,
                "unavailable_from": _AS_OF.isoformat(),
                "unavailable_until": (_AS_OF + timedelta(days=14)).isoformat(),
            },
        },
        {
            "name": "PAYMENT DEPENDENCY DELAY",
            "description": "Explicit payment dependency delayed by 30 days (synthetic).",
            "target_type": ScenarioTargetType.PROJECT,
            "target_id": project_rt,
            "kind": ScenarioKind.DEPENDENCY_DELAY,
            "assumptions": {
                "dependency_id": dep_payment or "__RESOLVE_FIRST_DEP__",
                "delay_days": 30,
            },
        },
        {
            "name": "AZURE CAPABILITY UNAVAILABLE",
            "description": "Required Azure capability temporarily unavailable (synthetic).",
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": ids["init:azure-migration"],
            "kind": ScenarioKind.CAPABILITY_UNAVAILABLE,
            "assumptions": {
                "capability_id": cap_azure,
                "unavailable_from": _AS_OF.isoformat(),
                "unavailable_until": (_AS_OF + timedelta(days=21)).isoformat(),
                "affected_owner_ids": [],
            },
        },
        {
            "name": "INCIDENT ESCALATION",
            "description": "Shared platform incident severity increased (synthetic).",
            "target_type": ScenarioTargetType.PROJECT,
            "target_id": project_rt,
            "kind": ScenarioKind.INCIDENT_ESCALATION,
            "assumptions": {
                "repository_id": repo_payments,
                "simulated_severity": "critical",
                "effective_from": _AS_OF.isoformat(),
                "effective_until": (_AS_OF + timedelta(days=7)).isoformat(),
            },
        },
        {
            "name": "DEADLINE COMPRESSION",
            "description": "Selected project deadline reduced by 21 days (synthetic).",
            "target_type": ScenarioTargetType.PROJECT,
            "target_id": project_fraud,
            "kind": ScenarioKind.DEADLINE_COMPRESSION,
            "assumptions": {
                "project_id": project_fraud,
                "days_reduced": 21,
            },
        },
        {
            "name": "COMBINED STRESS SCENARIO",
            "description": "Three compatible stress changes (synthetic).",
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": initiative_payment,
            "kind": ScenarioKind.COMBINED,
            "assumptions": {
                "changes": [
                    {
                        "kind": ScenarioKind.ENGINEER_UNAVAILABLE.value,
                        "engineer_id": eng_fraud,
                        "unavailable_from": _AS_OF.isoformat(),
                        "unavailable_until": (_AS_OF + timedelta(days=30)).isoformat(),
                    },
                    {
                        "kind": ScenarioKind.TEAM_CAPACITY_REDUCTION.value,
                        "team_id": team_platform,
                        "reduction_percentage": 40,
                        "effective_from": _AS_OF.isoformat(),
                        "effective_until": (_AS_OF + timedelta(days=60)).isoformat(),
                    },
                    {
                        "kind": ScenarioKind.REPOSITORY_UNAVAILABLE.value,
                        "repository_id": repo_shared,
                        "unavailable_from": _AS_OF.isoformat(),
                        "unavailable_until": (_AS_OF + timedelta(days=14)).isoformat(),
                    },
                ]
            },
        },
    ]


def _resolve_ids(session: Session) -> dict[str, str]:
    ids = {
        "eng:eng-12": _tid("eng", "eng-12"),
        "team:cloud-foundations": _tid("team", "cloud-foundations"),
        "repo:cloud-landing-zone": _tid("repo", "github", "novabank/cloud-landing-zone"),
        "repo:payments-core-svc": _tid("repo", "github", "novabank/payments-core-svc"),
        "cap:azure-platform": _tid("cap", "azure-platform"),
        "proj:rt-payments-rail": _tid("proj", "rt-payments-rail"),
        "proj:fraud-scoring-v2": _tid("proj", "fraud-scoring-v2"),
        "init:fraud-detection-uplift": _tid("init", "fraud-detection-uplift"),
        "init:payment-modernization": _tid("init", "payment-modernization"),
        "init:azure-migration": _tid("init", "azure-migration"),
    }
    # Resolve a deterministic dependency for payment project → shared repo.
    from app.db.models import enterprise as orm

    dep = (
        session.query(orm.Dependency)
        .filter(orm.Dependency.tenant_id == TENANT_ID)
        .order_by(orm.Dependency.dependency_id.asc())
        .first()
    )
    if dep is not None:
        ids["dep:payment-modernization"] = dep.dependency_id
    return ids


def seed_novabank_scenarios(session: Session) -> dict[str, Any]:
    """Create the 8 NovaBank demo scenarios (idempotent)."""
    ctx = TenantContext.require(TENANT_ID)
    uow = UnitOfWork(session)
    orch = ScenarioOrchestrationService(uow)
    ids = _resolve_ids(session)
    created_definitions = 0
    created_versions = 0
    reused_definitions = 0
    reused_versions = 0
    definition_ids: list[str] = []
    version_ids: list[str] = []

    for spec in _scenario_specs(ids):
        assumptions = dict(spec["assumptions"])
        if assumptions.get("dependency_id") == "__RESOLVE_FIRST_DEP__":
            dep_id = ids.get("dep:payment-modernization")
            if not dep_id:
                continue
            assumptions["dependency_id"] = dep_id

        before = uow.scenario_definitions.list(ctx, limit=100, offset=0)
        existing = next((d for d in before.items if d.name == spec["name"]), None)
        if existing is None:
            definition = orch.create_definition(
                ctx,
                name=spec["name"],
                description=spec["description"],
                target_type=spec["target_type"],
                target_id=spec["target_id"],
                scenario_kind=spec["kind"],
            )
            created_definitions += 1
        else:
            definition = existing
            reused_definitions += 1

        before_versions = uow.scenario_versions.list_for_definition(
            ctx, definition.scenario_definition_id, limit=10, offset=0
        ).total
        version = orch.create_version(
            ctx,
            scenario_definition_id=definition.scenario_definition_id,
            assumptions=assumptions,
            effective_from=_BASE,
            created_by_context="novabank_seed",
        )
        after_versions = uow.scenario_versions.list_for_definition(
            ctx, definition.scenario_definition_id, limit=10, offset=0
        ).total
        if after_versions > before_versions:
            created_versions += 1
        else:
            reused_versions += 1
        definition_ids.append(definition.scenario_definition_id)
        version_ids.append(version.scenario_version_id)

    session.flush()
    return {
        "tenant_id": TENANT_ID,
        "as_of_at": _AS_OF.isoformat(),
        "definitions_created": created_definitions,
        "definitions_reused": reused_definitions,
        "versions_created": created_versions,
        "versions_reused": reused_versions,
        "definition_ids": definition_ids,
        "version_ids": version_ids,
        "scenario_count": len(definition_ids),
    }
