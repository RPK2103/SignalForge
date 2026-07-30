"""Service-layer authorization (Phase 3 Prompt 7).

Deny-by-default. Authorization is a pure function of the passed
:class:`SecurityContext`, the required :class:`Permission`, and the resource's
tenant. It never consults hidden global state, so a direct service call without a
context fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.security.context import SecurityContext
from app.security.enums import AuthorizationDecision, Permission
from app.security.exceptions import AuthorizationError


@dataclass(frozen=True, slots=True)
class AuthorizationOutcome:
    decision: AuthorizationDecision
    reason_code: str

    @property
    def allowed(self) -> bool:
        return self.decision is AuthorizationDecision.ALLOW


class AuthorizationService:
    """Stateless permission checker."""

    def check(
        self,
        context: SecurityContext | None,
        permission: Permission,
        resource_tenant_id: str,
    ) -> AuthorizationOutcome:
        if context is None:
            return AuthorizationOutcome(AuthorizationDecision.DENY, "no_security_context")
        if not resource_tenant_id or resource_tenant_id != context.tenant_id:
            return AuthorizationOutcome(AuthorizationDecision.DENY, "tenant_mismatch")
        if permission not in context.permissions:
            return AuthorizationOutcome(AuthorizationDecision.DENY, "missing_permission")
        return AuthorizationOutcome(AuthorizationDecision.ALLOW, "granted")

    def require(
        self,
        context: SecurityContext | None,
        permission: Permission,
        resource_tenant_id: str,
    ) -> None:
        """Raise :class:`AuthorizationError` unless the permission is granted."""
        outcome = self.check(context, permission, resource_tenant_id)
        if not outcome.allowed:
            raise AuthorizationError(
                "Access denied for the requested operation",
                reason_code=outcome.reason_code,
            )

    def require_context(
        self,
        context: SecurityContext | None,
        permission: Permission,
    ) -> None:
        """Deny-by-default service-boundary check for the caller's own tenant.

        None-safe: an absent context fails closed (``no_security_context``) rather
        than raising an ``AttributeError``. Use this at application-service entry
        points that operate within the authenticated principal's own tenant.
        """
        resource_tenant = context.tenant_id if context is not None else ""
        self.require(context, permission, resource_tenant)
