"""Enterprise-layer exceptions.

These extend the existing ``PersistenceError`` hierarchy so the already-registered
FastAPI exception handler serializes them into the standard error envelope.
"""

from app.services.persistence.exceptions import PersistenceError


class EnterpriseError(PersistenceError):
    error_type = "enterprise_error"
    status_code = 500


class TenantContextError(EnterpriseError):
    """Missing or malformed tenant context at a service/API boundary."""

    error_type = "tenant_context_error"
    status_code = 400


class EnterpriseNotFoundError(EnterpriseError):
    """Tenant-qualified record does not exist (also used for non-disclosure)."""

    error_type = "enterprise_not_found"
    status_code = 404


class CrossTenantAccessError(EnterpriseError):
    """A write attempted to associate a record with another tenant's entity."""

    error_type = "cross_tenant_access_rejected"
    status_code = 422


class EnterpriseConflictError(EnterpriseError):
    """Unique/deduplication conflict."""

    error_type = "enterprise_conflict"
    status_code = 409


class EnterpriseValidationError(EnterpriseError):
    error_type = "enterprise_validation_error"
    status_code = 422
