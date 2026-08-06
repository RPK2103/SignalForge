"""Eight story-aligned NovaBank scenario definitions (idempotent)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.unit_of_work import UnitOfWork
from app.demo.novabank.constants import AS_OF_AT, FOUNDATIONAL_BASE, TENANT_ID
from app.demo.novabank.helpers import resolve_foundational_ids, tid
from app.demo.novabank.specification import CANONICAL_SPEC
from app.domain.scenario_enums import ScenarioKind, ScenarioTargetType
from app.domain.tenant_context import TenantContext
from app.services.scenarios.orchestration import ScenarioOrchestrationService


def _story_specs(ids: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "name": "STORY-01 FRAUD DETECTION LAUNCH RISK",
            "description": (
                "Story-01: fraud launch risk under identity/compliance constraints (synthetic)."
            ),
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": ids["init:fraud-detection-uplift"],
            "kind": ScenarioKind.COMBINED,
            "assumptions": {
                "changes": [
                    {
                        "kind": ScenarioKind.CAPABILITY_UNAVAILABLE.value,
                        "capability_id": ids["cap:fraud-modeling"],
                        "unavailable_from": AS_OF_AT.isoformat(),
                        "unavailable_until": (AS_OF_AT + timedelta(days=14)).isoformat(),
                        "affected_owner_ids": [],
                    },
                    {
                        "kind": ScenarioKind.INCIDENT_ESCALATION.value,
                        "repository_id": ids["repo:fraud-scoring"],
                        "simulated_severity": "critical",
                        "effective_from": AS_OF_AT.isoformat(),
                        "effective_until": (AS_OF_AT + timedelta(days=7)).isoformat(),
                    },
                ]
            },
        },
        {
            "name": "STORY-02 PAYMENT DEPENDENCY SLIP",
            "description": "Story-02: shared payment-platform dependency delayed (synthetic).",
            "target_type": ScenarioTargetType.PROJECT,
            "target_id": ids["proj:rt-payments-rail"],
            "kind": ScenarioKind.DEPENDENCY_DELAY,
            "assumptions": {
                "dependency_id": "__RESOLVE_PAYMENT_DEP__",
                "delay_days": 30,
            },
        },
        {
            "name": "STORY-03 AZURE CAPABILITY SHORTAGE",
            "description": (
                "Story-03: Azure capability unavailable amid overcommitted cloud team (synthetic)."
            ),
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": ids["init:azure-migration"],
            "kind": ScenarioKind.CAPABILITY_UNAVAILABLE,
            "assumptions": {
                "capability_id": ids["cap:azure-platform"],
                "unavailable_from": AS_OF_AT.isoformat(),
                "unavailable_until": (AS_OF_AT + timedelta(days=21)).isoformat(),
                "affected_owner_ids": [],
            },
        },
        {
            "name": "STORY-04 CUSTOMER COPILOT READINESS",
            "description": (
                "Story-04: customer-copilot deadline compression readiness probe (synthetic)."
            ),
            "target_type": ScenarioTargetType.PROJECT,
            "target_id": ids["proj:copilot-orchestration"],
            "kind": ScenarioKind.DEADLINE_COMPRESSION,
            "assumptions": {
                "project_id": ids["proj:copilot-orchestration"],
                "days_reduced": 21,
            },
        },
        {
            "name": "STORY-05 KEY OWNER ROLE TRANSITION",
            "description": (
                "Story-05: hypothetical role-transition unavailability for concentrated "
                "repository ownership — knowledge-continuity risk only (synthetic)."
            ),
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": ids["init:fraud-detection-uplift"],
            "kind": ScenarioKind.ENGINEER_UNAVAILABLE,
            "assumptions": {
                "engineer_id": ids["eng:eng-13"],
                "unavailable_from": AS_OF_AT.isoformat(),
                "unavailable_until": (AS_OF_AT + timedelta(days=30)).isoformat(),
            },
        },
        {
            "name": "STORY-06 INCIDENT ROADMAP DELAY",
            "description": "Story-06: incident escalation affecting roadmap delivery (synthetic).",
            "target_type": ScenarioTargetType.PROJECT,
            "target_id": ids["proj:slo-platform"],
            "kind": ScenarioKind.INCIDENT_ESCALATION,
            "assumptions": {
                "repository_id": ids["repo:payments-core-svc"],
                "simulated_severity": "critical",
                "effective_from": AS_OF_AT.isoformat(),
                "effective_until": (AS_OF_AT + timedelta(days=7)).isoformat(),
            },
        },
        {
            "name": "STORY-07 CONCENTRATED OWNERSHIP RISK",
            "description": "Story-07: concentrated ownership continuity probe (synthetic).",
            "target_type": ScenarioTargetType.PROJECT,
            "target_id": ids["proj:fraud-scoring-v2"],
            "kind": ScenarioKind.REPOSITORY_UNAVAILABLE,
            "assumptions": {
                "repository_id": ids["repo:fraud-scoring"],
                "unavailable_from": AS_OF_AT.isoformat(),
                "unavailable_until": (AS_OF_AT + timedelta(days=14)).isoformat(),
            },
        },
        {
            "name": "STORY-08 PLATFORM CAPACITY BOTTLENECK",
            "description": "Story-08: shared platform capacity reduction bottleneck (synthetic).",
            "target_type": ScenarioTargetType.INITIATIVE,
            "target_id": ids["init:payment-modernization"],
            "kind": ScenarioKind.TEAM_CAPACITY_REDUCTION,
            "assumptions": {
                "team_id": ids["team:cloud-foundations"],
                "reduction_percentage": 40,
                "effective_from": AS_OF_AT.isoformat(),
                "effective_until": (AS_OF_AT + timedelta(days=60)).isoformat(),
            },
        },
    ]


def seed_story_scenarios(session: Session) -> dict[str, Any]:
    ctx = TenantContext.require(TENANT_ID)
    uow = UnitOfWork(session)
    orch = ScenarioOrchestrationService(uow)
    ids = resolve_foundational_ids()
    # Resolve payment dependency for story-02.
    from app.db.models import enterprise as orm

    payment_dep = (
        session.query(orm.Dependency)
        .filter(
            orm.Dependency.tenant_id == TENANT_ID,
            orm.Dependency.source_id == ids["proj:rt-payments-rail"],
            orm.Dependency.target_id == ids["repo:cloud-landing-zone"],
        )
        .order_by(orm.Dependency.dependency_id.asc())
        .first()
    )
    if payment_dep is None:
        payment_dep = (
            session.query(orm.Dependency)
            .filter(orm.Dependency.tenant_id == TENANT_ID)
            .order_by(orm.Dependency.dependency_id.asc())
            .first()
        )

    created_definitions = 0
    reused_definitions = 0
    created_versions = 0
    reused_versions = 0
    definition_ids: list[str] = []

    expected_names = {s.scenario_name for s in CANONICAL_SPEC.stories}
    for spec in _story_specs(ids):
        assert spec["name"] in expected_names
        assumptions = dict(spec["assumptions"])
        if assumptions.get("dependency_id") == "__RESOLVE_PAYMENT_DEP__":
            if payment_dep is None:
                continue
            assumptions["dependency_id"] = payment_dep.dependency_id

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
        orch.create_version(
            ctx,
            scenario_definition_id=definition.scenario_definition_id,
            assumptions=assumptions,
            effective_from=FOUNDATIONAL_BASE,
            created_by_context="novabank_demo_v2",
        )
        after_versions = uow.scenario_versions.list_for_definition(
            ctx, definition.scenario_definition_id, limit=10, offset=0
        ).total
        if after_versions > before_versions:
            created_versions += 1
        else:
            reused_versions += 1
        definition_ids.append(definition.scenario_definition_id)

    session.flush()
    return {
        "tenant_id": TENANT_ID,
        "as_of_at": AS_OF_AT.isoformat(),
        "definitions_created": created_definitions,
        "definitions_reused": reused_definitions,
        "versions_created": created_versions,
        "versions_reused": reused_versions,
        "definition_ids": definition_ids,
        "scenario_count": len(definition_ids),
        "org_id": tid("org", "novabank"),
    }
