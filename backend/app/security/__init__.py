"""Enterprise security foundation (Phase 3 Prompt 7).

Provider-independent authentication, deny-by-default RBAC, service-layer
authorization, append-only security auditing, and PostgreSQL row-level-security
helpers.

IMPORTANT SECURITY BOUNDARIES:
- The pre-existing ``X-SignalForge-Tenant-ID`` header is a *tenant selector*, not
  authentication. After Prompt 7 a verified principal must be established first,
  and the selected tenant must be one of the principal's active memberships.
- ``local_development`` and ``test`` authentication modes are impossible in
  production and are enforced fail-closed at startup.
- SQLite does not enforce row-level security. RLS is PostgreSQL-only defense in
  depth; SQLite isolation relies on the tenant-scoped repository/service layer.
"""
