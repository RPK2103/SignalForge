"""Permission-coverage introspection and the sensitive-operation registry.

This module exists to detect a specific class of broken-access-control bug: a
permission defined in the RBAC matrix that is never actually enforced by any
reachable code path (route, application service or an explicitly documented
service/CLI-only or deferred operation).

Two sources of truth are combined by ``tests/security/test_permission_coverage``:

1. Dynamic route introspection (:func:`route_enforced_permissions`) walks the
   live FastAPI application and reports which permissions are enforced by
   ``require_permission`` route dependencies. This is real enforcement, not a
   string comment.
2. An explicit, versioned :data:`SENSITIVE_PERMISSION_ENFORCEMENT` registry that
   classifies every sensitive permission as route-, service-, or CLI-enforced,
   or documents it as deferred with no reachable unsecured call path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.security.enums import Permission

COVERAGE_REGISTRY_VERSION = "2026-07-31.1"


class EnforcementKind(str, Enum):
    """Where a sensitive permission is enforced."""

    ROUTE = "route"  # enforced by a reachable HTTP route dependency
    SERVICE = "service"  # enforced at an application-service boundary
    CLI = "cli"  # enforced by an authenticated internal CLI execution context
    DEFERRED = "deferred"  # no reachable operation yet; documented, no unsecured path


@dataclass(frozen=True)
class Enforcement:
    kind: EnforcementKind
    sites: tuple[str, ...]
    note: str = ""


# The sensitive permissions whose enforcement MUST be accounted for. This mirrors
# the audit checklist ("at minimum ...") plus every write/generate permission.
SENSITIVE_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.ENTERPRISE_MANAGE,
        Permission.CONNECTORS_SYNC,
        Permission.CONNECTORS_MANAGE,
        Permission.GRAPH_REBUILD,
        Permission.PREDICTIONS_TRAIN,
        Permission.PREDICTIONS_VALIDATE,
        Permission.PREDICTIONS_PROMOTE,
        Permission.SCENARIOS_RUN,
        Permission.SCENARIOS_MANAGE_WATCHES,
        Permission.CHIEF_OF_STAFF_GENERATE,
        Permission.CHIEF_OF_STAFF_REVIEW,
        Permission.SECURITY_AUDIT_READ,
        Permission.SECURITY_ROLES_MANAGE,
        Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE,
        Permission.OBSERVABILITY_MANAGE,
        Permission.AI_QUALITY_EVALUATE,
    }
)


# Explicit, reviewed classification of every sensitive permission. Route-enforced
# entries are cross-checked against live introspection; service-enforced entries
# are cross-checked against the application-service source, both by the coverage
# test in tests/security/test_permission_coverage.py.
SENSITIVE_PERMISSION_ENFORCEMENT: dict[Permission, Enforcement] = {
    Permission.ENTERPRISE_MANAGE: Enforcement(
        EnforcementKind.ROUTE,
        ("POST /api/v2/assessments", "AssessmentPersistenceService.create_assessment"),
        note="Persisting an assessment; route + service boundary both re-check.",
    ),
    Permission.CONNECTORS_MANAGE: Enforcement(
        EnforcementKind.ROUTE,
        ("POST /api/v3/data-sources", "IngestionService.register_data_source"),
    ),
    Permission.CONNECTORS_SYNC: Enforcement(
        EnforcementKind.ROUTE,
        (
            "POST /api/v3/ingestion-runs",
            "POST /api/v3/ingestion-runs/{id}/complete",
            "POST /api/v3/evidence-signals",
            "IngestionService.start_run/complete_run/append_evidence",
        ),
    ),
    Permission.SCENARIOS_RUN: Enforcement(
        EnforcementKind.ROUTE,
        (
            "POST /api/v2/simulations/simulate",
            "POST /api/v2/simulation-records",
            "POST /simulate (legacy)",
            "SimulationPersistenceService.create_simulation",
        ),
    ),
    Permission.CHIEF_OF_STAFF_GENERATE: Enforcement(
        EnforcementKind.ROUTE,
        (
            "POST /api/v2/assessments/{id}/leadership-brief",
            "POST /generate-insight (legacy)",
            "POST /copilot (legacy)",
            "LeadershipBriefPersistenceService.generate_leadership_brief",
        ),
    ),
    Permission.CHIEF_OF_STAFF_REVIEW: Enforcement(
        EnforcementKind.ROUTE,
        (
            "POST /api/v2/assessments/{id}/leadership-brief/reviews",
            "HumanReviewPersistenceService.add_review",
        ),
    ),
    # Security administration + audit read are HTTP-reachable but authorization is
    # enforced at the SecurityAdministrationService boundary (the routes only
    # marshal input/output). Verified against the service source by the test.
    Permission.SECURITY_AUDIT_READ: Enforcement(
        EnforcementKind.SERVICE,
        ("GET /api/v3/security/audit-events", "SecurityAdministrationService.read_audit"),
    ),
    Permission.SECURITY_ROLES_MANAGE: Enforcement(
        EnforcementKind.SERVICE,
        (
            "POST /api/v3/security/role-assignments",
            "DELETE /api/v3/security/role-assignments/{id}",
            "SecurityAdministrationService.assign_role/revoke_role/create_principal",
        ),
    ),
    Permission.SECURITY_IDENTITY_PROVIDERS_MANAGE: Enforcement(
        EnforcementKind.SERVICE,
        (
            "PUT /api/v3/security/identity-providers",
            "SecurityAdministrationService.upsert_identity_provider/list_identity_providers",
        ),
    ),
    # Model/graph/scenario execution is intentionally NOT exposed over HTTP (the
    # v3 predictions/graph/scenarios routers are read-only). These execute inside
    # trusted internal batch/CLI processes, so there is no unsecured HTTP call
    # path. Adding an explicit service-layer permission gate to these Prompt 4/5
    # execution services is tracked as deferred follow-up (out of scope for the
    # Prompt 7 broken-access-control remediation, which concerns reachable routes).
    Permission.GRAPH_REBUILD: Enforcement(
        EnforcementKind.DEFERRED,
        ("GraphOrchestration (batch/CLI); v3 delivery-graph router is read-only",),
        note="No HTTP mutation route; deferred service-layer gate.",
    ),
    Permission.PREDICTIONS_TRAIN: Enforcement(
        EnforcementKind.DEFERRED,
        ("PredictionOrchestrationService.train (batch/CLI); v3 predictions router is read-only",),
        note="No HTTP mutation route; deferred service-layer gate.",
    ),
    Permission.PREDICTIONS_VALIDATE: Enforcement(
        EnforcementKind.DEFERRED,
        ("PredictionOrchestrationService.validate_pipeline (batch/CLI); read-only over HTTP",),
        note="No HTTP mutation route; deferred service-layer gate.",
    ),
    Permission.PREDICTIONS_PROMOTE: Enforcement(
        EnforcementKind.DEFERRED,
        ("PredictionOrchestrationService.promote (batch/CLI); read-only over HTTP",),
        note="No HTTP mutation route; deferred service-layer gate.",
    ),
    Permission.SCENARIOS_MANAGE_WATCHES: Enforcement(
        EnforcementKind.DEFERRED,
        (
            "ScenarioOrchestrationService.create_watch (batch/CLI); "
            "v3 scenarios router is read-only",
        ),
        note="No HTTP mutation route; deferred service-layer gate.",
    ),
    # Prompt 8 observability + AI quality: both route- and service-enforced.
    Permission.OBSERVABILITY_MANAGE: Enforcement(
        EnforcementKind.ROUTE,
        (
            "POST /api/v3/observability/alerts/{alert_id}/acknowledge",
            "ObservabilityService.acknowledge_alert/resolve_alert/upsert_slo_definition",
        ),
        note="Route + service boundary both re-check; audited state changes.",
    ),
    Permission.AI_QUALITY_EVALUATE: Enforcement(
        EnforcementKind.ROUTE,
        (
            "POST /api/v3/observability/ai-quality/evaluate",
            "AiQualityService.run_release_evaluation",
        ),
        note="Route + service boundary both re-check; audited evaluation runs.",
    ),
}


def _iter_dependants(dependant: Dependant):
    """Depth-first walk of a route's dependant tree."""
    yield dependant
    for sub in dependant.dependencies:
        yield from _iter_dependants(sub)


def route_enforced_permissions(app: FastAPI) -> dict[Permission, set[str]]:
    """Return the permissions enforced by each route, from live introspection.

    Maps a :class:`Permission` to the set of ``METHOD path`` strings whose
    dependency tree contains a ``require_permission(permission)`` closure.
    """
    enforced: dict[Permission, set[str]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(route.methods or [])
        label = f"{','.join(methods)} {route.path}"
        for dep in _iter_dependants(route.dependant):
            call = dep.call
            permission = getattr(call, "__signalforge_required_permission__", None)
            if isinstance(permission, Permission):
                enforced.setdefault(permission, set()).add(label)
    return enforced
