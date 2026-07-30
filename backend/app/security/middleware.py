"""HTTP security middleware (Phase 3 Prompt 7).

- ``AuthenticationMiddleware`` enforces DEFAULT-DENY authentication: every route
  requires a verified bearer principal EXCEPT an explicit public allowlist
  (``/`` and ``/health``, plus environment-aware documentation and static-UI
  paths supplied by the application). Legacy root routers and any future route
  are therefore authenticated automatically rather than depending on a manually
  maintained protected-prefix list that a new route could silently bypass. It
  records authentication-failure audit events and stashes the principal +
  correlation id on ``request.state`` for downstream dependencies.
- ``SecurityHeadersMiddleware`` adds safe response headers (environment-aware).

Tokens are never logged or echoed; only stable failure categories are surfaced.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.db.unit_of_work import UnitOfWork
from app.security.audit import SecurityAuditService
from app.security.providers import get_authentication_service

_CORRELATION_HEADER = "X-Correlation-ID"

# Minimal always-public allowlist. The application may extend this (e.g. with
# documentation endpoints when docs are enabled, or a static-UI prefix), but it
# must be explicit — there is no wildcard and no anonymous fallback.
_DEFAULT_PUBLIC_PATHS = frozenset({"/", "/health"})


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        public_paths: Iterable[str] | None = None,
        public_prefixes: Iterable[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._public_paths = (
            frozenset(public_paths) if public_paths is not None else _DEFAULT_PUBLIC_PATHS
        )
        self._public_prefixes = tuple(public_prefixes or ())

    def _is_public(self, path: str) -> bool:
        if path in self._public_paths:
            return True
        return any(
            path == prefix or path.startswith(prefix.rstrip("/") + "/")
            for prefix in self._public_prefixes
        )

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(_CORRELATION_HEADER) or uuid.uuid4().hex
        request.state.correlation_id = correlation_id

        # CORS preflight carries no credentials and must not be authenticated.
        # DEFAULT-DENY: any path not on the explicit public allowlist is protected.
        if request.method == "OPTIONS" or self._is_public(request.url.path):
            response = await call_next(request)
            response.headers.setdefault(_CORRELATION_HEADER, correlation_id)
            return response

        token = _extract_bearer(request)
        result = get_authentication_service().authenticate(token)
        if not result.succeeded:
            self._audit_failure(request, result, correlation_id)
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Authentication required",
                    "status_code": 401,
                    "error_type": "authentication_failed",
                },
                headers={
                    _CORRELATION_HEADER: correlation_id,
                    "WWW-Authenticate": "Bearer",
                },
            )

        request.state.auth_principal = result.principal
        response = await call_next(request)
        response.headers.setdefault(_CORRELATION_HEADER, correlation_id)
        return response

    @staticmethod
    def _audit_failure(request: Request, result, correlation_id: str) -> None:
        from app.db.session import get_session_factory

        category = result.failure_category
        if category is None:
            return
        try:
            session = get_session_factory()()
        except Exception:  # noqa: BLE001 - DB unavailable must not mask the 401
            return
        try:
            SecurityAuditService(UnitOfWork(session)).record_authentication_failure(
                category=category,
                correlation_id=correlation_id,
                request_method=request.method,
                request_path=request.url.path,
                source_ip=_client_ip(request),
            )
            session.commit()
        except Exception:  # noqa: BLE001 - best-effort; never leak or crash
            session.rollback()
        finally:
            session.close()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, hsts_enabled: bool) -> None:
        super().__init__(app)
        self._hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        if request.url.path.startswith(("/api/v2", "/api/v3")):
            response.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate")
        if self._hsts_enabled:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
