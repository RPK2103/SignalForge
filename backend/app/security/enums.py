"""Enumerations for the enterprise security domain (Phase 3 Prompt 7)."""

from __future__ import annotations

from enum import Enum


class PrincipalType(str, Enum):
    """Kind of authenticated caller. ``service_principal`` is NOT a role."""

    USER = "user"
    SERVICE_PRINCIPAL = "service_principal"


class AuthenticationMode(str, Enum):
    """Authentication provider selection.

    - ``entra_oidc``: Microsoft Entra-compatible OIDC/JWT validation (production).
    - ``local_development``: signed short-lived developer JWTs (never production).
    - ``test``: deterministic in-process test tokens (never outside tests).
    """

    ENTRA_OIDC = "entra_oidc"
    LOCAL_DEVELOPMENT = "local_development"
    TEST = "test"


class AuthenticationFailureCategory(str, Enum):
    """Stable, secret-safe taxonomy for authentication failures.

    Categories are intentionally coarse so they can be logged and audited
    without ever revealing token contents.
    """

    MISSING_TOKEN = "missing_token"
    MALFORMED_TOKEN = "malformed_token"
    UNSUPPORTED_ALGORITHM = "unsupported_algorithm"
    INVALID_SIGNATURE = "invalid_signature"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    INVALID_ISSUER = "invalid_issuer"
    INVALID_AUDIENCE = "invalid_audience"
    UNKNOWN_TENANT = "unknown_tenant"
    MISSING_SUBJECT = "missing_subject"
    UNKNOWN_KEY_ID = "unknown_key_id"
    JWKS_UNAVAILABLE = "jwks_unavailable"
    JWKS_MALFORMED = "jwks_malformed"
    TOKEN_TOO_LARGE = "token_too_large"
    MODE_NOT_PERMITTED = "mode_not_permitted"
    PROVIDER_ERROR = "provider_error"


class PrincipalStatus(str, Enum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class IdentityProviderType(str, Enum):
    ENTRA_OIDC = "entra_oidc"
    LOCAL_DEVELOPMENT = "local_development"
    TEST = "test"


class AuthorizationDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class SecurityRole(str, Enum):
    """Deny-by-default RBAC roles. Unknown roles grant nothing."""

    TENANT_ADMIN = "tenant_admin"
    EXECUTIVE_READER = "executive_reader"
    ENGINEERING_LEADER = "engineering_leader"
    INTELLIGENCE_ANALYST = "intelligence_analyst"
    INTEGRATION_OPERATOR = "integration_operator"
    SECURITY_AUDITOR = "security_auditor"


class Permission(str, Enum):
    """Versioned, explicit permissions. No implicit inheritance."""

    # Enterprise
    ENTERPRISE_READ = "enterprise.read"
    ENTERPRISE_MANAGE = "enterprise.manage"
    # Connectors
    CONNECTORS_READ = "connectors.read"
    CONNECTORS_SYNC = "connectors.sync"
    CONNECTORS_MANAGE = "connectors.manage"
    # Delivery graph
    GRAPH_READ = "graph.read"
    GRAPH_REBUILD = "graph.rebuild"
    # Prediction
    PREDICTIONS_READ = "predictions.read"
    PREDICTIONS_TRAIN = "predictions.train"
    PREDICTIONS_VALIDATE = "predictions.validate"
    PREDICTIONS_PROMOTE = "predictions.promote"
    # Scenarios
    SCENARIOS_READ = "scenarios.read"
    SCENARIOS_RUN = "scenarios.run"
    SCENARIOS_MANAGE_WATCHES = "scenarios.manage_watches"
    # Chief of Staff
    CHIEF_OF_STAFF_READ = "chief_of_staff.read"
    CHIEF_OF_STAFF_GENERATE = "chief_of_staff.generate"
    CHIEF_OF_STAFF_REVIEW = "chief_of_staff.review"
    # Security
    SECURITY_AUDIT_READ = "security.audit.read"
    SECURITY_ROLES_MANAGE = "security.roles.manage"
    SECURITY_IDENTITY_PROVIDERS_MANAGE = "security.identity_providers.manage"


class SecurityAuditAction(str, Enum):
    """Stable action taxonomy for append-only security audit events."""

    AUTHENTICATION_FAILURE = "authentication.failure"
    AUTHORIZATION_DENIED = "authorization.denied"
    ROLE_ASSIGNMENT_CREATED = "security.role_assignment.created"
    ROLE_ASSIGNMENT_REVOKED = "security.role_assignment.revoked"
    IDENTITY_PROVIDER_CHANGED = "security.identity_provider.changed"
    CONNECTOR_CONFIGURED = "connectors.configured"
    CONNECTOR_SYNC_INITIATED = "connectors.sync_initiated"
    GRAPH_REBUILD_INITIATED = "graph.rebuild_initiated"
    PREDICTION_TRAINED = "predictions.trained"
    PREDICTION_VALIDATED = "predictions.validated"
    PREDICTION_PROMOTED = "predictions.promoted"
    SCENARIO_EXECUTED = "scenarios.executed"
    SCENARIO_WATCH_MUTATED = "scenarios.watch_mutated"
    CHIEF_OF_STAFF_GENERATED = "chief_of_staff.generated"
    CHIEF_OF_STAFF_REVIEWED = "chief_of_staff.reviewed"


class AuditWriteResult(str, Enum):
    WRITTEN = "written"
    FAILED = "failed"
