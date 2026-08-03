from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v2.router import router as api_v2_router
from app.api.v3.dependencies import require_permission
from app.api.v3.router import router as api_v3_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import configure_logging, log_startup
from app.core.paths import DASHBOARD_DIR
from app.observability.middleware import RequestTelemetryMiddleware
from app.observability.runtime import init_observability, reset_observability_provider
from app.routes.copilot import router as copilot_router
from app.routes.engineer import router as engineer_router
from app.routes.insight import router as insight_router
from app.routes.predictor import router as predictor_router
from app.routes.project_fit import router as project_fit_router
from app.routes.risk import router as risk_router
from app.routes.simulator import router as simulator_router
from app.routes.team import router as team_router
from app.security.config import validate_startup_security
from app.security.enums import Permission
from app.security.middleware import AuthenticationMiddleware, SecurityHeadersMiddleware

settings = get_settings()
configure_logging(settings)

# Fail closed at startup: production must have complete Entra authentication
# configuration and safe CORS/host settings. This raises before serving traffic.
security_settings = validate_startup_security()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Selecting the observability provider must never break core startup: a missing
    # exporter/SDK degrades to the in-memory/no-op provider (see build_provider).
    init_observability(settings)
    log_startup(settings, dashboard_dir=str(DASHBOARD_DIR))
    yield
    reset_observability_provider()
    from app.db.session import reset_engine

    reset_engine()


# Documentation endpoints are configurable and disabled/hidden in production.
_docs_enabled = security_settings.docs_enabled
app = FastAPI(
    title="SignalForge API",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

register_exception_handlers(app)

# Middleware stack (outermost added last). Security headers wrap everything;
# host validation and CORS run before authentication; authentication is
# DEFAULT-DENY — every route requires a verified bearer principal except the
# explicit public allowlist below.
_public_paths = {"/", "/health"}
if _docs_enabled:
    # Documentation is public ONLY when the environment-aware docs setting enables
    # it (never in production, where these URLs are also unregistered).
    _public_paths |= {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
app.add_middleware(
    AuthenticationMiddleware,
    public_paths=_public_paths,
    # Static single-page-app assets are served unauthenticated; the SPA then
    # authenticates its API calls with a bearer token.
    public_prefixes=("/dashboard",),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-SignalForge-Tenant-ID",
        "X-Correlation-ID",
        "traceparent",
    ],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=security_settings.trusted_hosts)
app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=security_settings.hsts_enabled)
# Request telemetry is added LAST so it is the OUTERMOST middleware: it observes
# every response (including the 401 returned by authentication and 403/422 from
# exception handlers), owns correlation-ID sanitization, and records HTTP metrics
# with correct status semantics (401/403 are security denials, never 5xx).
app.add_middleware(RequestTelemetryMiddleware)

app.mount(
    "/dashboard",
    StaticFiles(directory=str(DASHBOARD_DIR), html=True),
    name="dashboard",
)

# Legacy root routers (Phase 1) are deterministic compute endpoints. They are
# authenticated by the default-deny middleware and RBAC-gated here at their
# application-service entry point (the route). The permission reflects the
# semantic operation; see architecture/phase-3-enterprise-security-scale.md.
_ENTERPRISE_READ = [Depends(require_permission(Permission.ENTERPRISE_READ))]
_PREDICTIONS_READ = [Depends(require_permission(Permission.PREDICTIONS_READ))]
_SCENARIOS_RUN = [Depends(require_permission(Permission.SCENARIOS_RUN))]
_COS_GENERATE = [Depends(require_permission(Permission.CHIEF_OF_STAFF_GENERATE))]

app.include_router(engineer_router, tags=["Engineer Analysis"], dependencies=_ENTERPRISE_READ)
app.include_router(project_fit_router, tags=["Project Fit"], dependencies=_ENTERPRISE_READ)
app.include_router(risk_router, tags=["Risk Assessment"], dependencies=_ENTERPRISE_READ)
app.include_router(team_router, tags=["Team Recommendation"], dependencies=_ENTERPRISE_READ)
app.include_router(insight_router, tags=["Executive Insight"], dependencies=_COS_GENERATE)
app.include_router(simulator_router, tags=["Staffing Simulator"], dependencies=_SCENARIOS_RUN)
app.include_router(
    predictor_router, tags=["Delivery Success Predictor"], dependencies=_PREDICTIONS_READ
)
app.include_router(copilot_router, tags=["AI Leadership Copilot"], dependencies=_COS_GENERATE)
app.include_router(api_v2_router)
app.include_router(api_v3_router)


@app.get("/")
def root():
    return {"message": "SignalForge backend is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}
