"""Security-layer exceptions mapped to controlled API errors.

These extend ``PersistenceError`` so the already-registered FastAPI exception
handler serializes them into the standard error envelope without leaking
provider internals or token contents.
"""

from __future__ import annotations

from app.security.enums import AuthenticationFailureCategory
from app.services.persistence.exceptions import PersistenceError


class SecurityError(PersistenceError):
    error_type = "security_error"
    status_code = 500


class AuthenticationError(SecurityError):
    """Caller identity could not be verified. Always maps to a safe 401."""

    error_type = "authentication_failed"
    status_code = 401

    def __init__(
        self,
        message: str = "Authentication failed",
        *,
        category: AuthenticationFailureCategory,
    ) -> None:
        super().__init__(message)
        self.category = category


class AuthorizationError(SecurityError):
    """Verified caller lacks the required permission for the target tenant."""

    error_type = "authorization_denied"
    status_code = 403

    def __init__(self, message: str = "Access denied", *, reason_code: str = "forbidden") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class TenantSelectionError(SecurityError):
    """Selected tenant is not an active membership of the verified principal.

    Externally indistinguishable from a not-found resource: callers must not be
    able to probe tenant existence, so this maps to a 404.
    """

    error_type = "resource_not_found"
    status_code = 404


class SecurityConfigError(SecurityError):
    """Invalid or unsafe security configuration. Fatal at startup (fail-closed)."""

    error_type = "security_config_error"
    status_code = 500
