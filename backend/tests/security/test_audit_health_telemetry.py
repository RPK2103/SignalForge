"""Security-audit health telemetry integration (Phase 3 Prompt 8 remediation).

Proves the Prompt 7 security-audit write boundary emits bounded health telemetry
(required/succeeded/failed/fail-closed) while its fail-closed contract is fully
preserved. Telemetry never replaces the audit event and telemetry-export failure
never weakens fail-closed behavior.
"""

from __future__ import annotations

import pytest

from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.security.audit import AuditWriteError, SecurityAuditService
from app.security.context import internal_system_context
from app.security.enums import Permission, SecurityAuditAction, SecurityRole


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def _ctx():
    return internal_system_context(
        "novabank",
        correlation_id="audit-health",
        roles=frozenset({SecurityRole.TENANT_ADMIN}),
    )


def test_required_audit_write_success_emits_health(uow, obs_provider):
    audit = SecurityAuditService(uow)
    record = audit.record_sensitive_action(
        _ctx(),
        action=SecurityAuditAction.ROLE_ASSIGNMENT_CREATED,
        permission=Permission.SECURITY_ROLES_MANAGE,
        resource_type="role_assignment",
        resource_id="ra-1",
    )
    uow.commit()
    assert record is not None
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_REQUIRED) == 1
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_SUCCEEDED) == 1
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_FAILED) == 0
    assert obs_provider.counter_total(MetricName.AUDIT_FAIL_CLOSED_MUTATIONS) == 0


def test_fail_closed_write_failure_emits_and_raises(uow, obs_provider):
    audit = SecurityAuditService(uow)

    class _BoomEvents:
        def append(self, **kwargs):
            raise RuntimeError("db down")

    audit._uow.security_audit_events = _BoomEvents()  # type: ignore[assignment]

    with pytest.raises(AuditWriteError):
        audit.record_sensitive_action(
            _ctx(),
            action=SecurityAuditAction.PREDICTION_PROMOTED,
            permission=Permission.PREDICTIONS_PROMOTE,  # fail-closed permission
            resource_type="prediction_model",
            resource_id="m-1",
        )

    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_FAILED) == 1
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_SUCCEEDED) == 0
    assert obs_provider.counter_total(MetricName.AUDIT_FAIL_CLOSED_MUTATIONS) == 1


def test_best_effort_write_failure_does_not_raise_but_is_measured(uow, obs_provider):
    audit = SecurityAuditService(uow)

    class _BoomEvents:
        def append(self, **kwargs):
            raise RuntimeError("db down")

    audit._uow.security_audit_events = _BoomEvents()  # type: ignore[assignment]

    # A non fail-closed permission is best-effort: returns None, never raises.
    result = audit.record_sensitive_action(
        internal_system_context(
            "novabank",
            correlation_id="c",
            roles=frozenset({SecurityRole.INTEGRATION_OPERATOR}),
        ),
        action=SecurityAuditAction.CONNECTOR_CONFIGURED,
        permission=Permission.CONNECTORS_MANAGE,
        resource_type="data_source",
        resource_id="ds-1",
    )
    assert result is None
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_FAILED) == 1
    assert obs_provider.counter_total(MetricName.AUDIT_FAIL_CLOSED_MUTATIONS) == 0


def test_telemetry_provider_failure_keeps_audit_fail_closed(uow):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("telemetry boom")

    set_observability_provider(ExplodingProvider())
    try:
        audit = SecurityAuditService(uow)

        class _BoomEvents:
            def append(self, **kwargs):
                raise RuntimeError("db down")

        audit._uow.security_audit_events = _BoomEvents()  # type: ignore[assignment]

        # Even when telemetry itself fails, the fail-closed contract holds.
        with pytest.raises(AuditWriteError):
            audit.record_sensitive_action(
                _ctx(),
                action=SecurityAuditAction.PREDICTION_PROMOTED,
                permission=Permission.PREDICTIONS_PROMOTE,
                resource_type="prediction_model",
                resource_id="m-2",
            )
    finally:
        reset_observability_provider()


def test_rollback_does_not_emit_audit_success(uow, obs_provider):
    audit = SecurityAuditService(uow)
    record = audit.record_sensitive_action(
        _ctx(),
        action=SecurityAuditAction.ROLE_ASSIGNMENT_CREATED,
        permission=Permission.SECURITY_ROLES_MANAGE,
        resource_type="role_assignment",
        resource_id="ra-rollback",
    )
    assert record is not None
    # Required is counted at the append boundary; success waits for commit.
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_REQUIRED) == 1
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_SUCCEEDED) == 0
    uow.rollback()
    assert obs_provider.counter_total(MetricName.AUDIT_WRITES_SUCCEEDED) == 0
