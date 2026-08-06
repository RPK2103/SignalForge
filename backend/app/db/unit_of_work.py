"""Unit of Work for atomic persistence transactions."""

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from app.db.repositories.chief_of_staff_repositories import (
    CosBriefRepository,
    CosEvidenceSnapshotRepository,
    CosReviewRepository,
    CosRunRepository,
)
from app.db.repositories.connector_repositories import (
    ConnectorCheckpointRepository,
    IngestionDeadLetterRepository,
    IngestionReceiptRepository,
    PullRequestRepository,
)
from app.db.repositories.enterprise_repositories import (
    DataSourceRepository,
    DeliveryRepository,
    EngineerProfileRepository,
    EnterpriseCatalogRepository,
    EvidenceSignalRepository,
    IngestionRunRepository,
    InitiativeProjectRepository,
    OrganizationRepository,
    RelationshipRepository,
)
from app.db.repositories.graph_repositories import (
    GraphAnalysisRunRepository,
    GraphEdgeRepository,
    GraphFindingRepository,
    GraphNodeRepository,
    GraphProjectionRunRepository,
)
from app.db.repositories.observability_repositories import (
    AiEvaluationCaseRepository,
    AiEvaluationDatasetRepository,
    AiEvaluationResultRepository,
    AiEvaluationRunRepository,
    AlertEventRepository,
    MetricRollupRepository,
    PredictionQualitySnapshotRepository,
    SloDefinitionRepository,
    SloEvaluationRepository,
)
from app.db.repositories.prediction_repositories import (
    DeliveryOutcomeRepository,
    DeliveryPredictionRepository,
    PredictionDatasetManifestRepository,
    PredictionFactorRepository,
    PredictionFeatureSnapshotRepository,
    PredictionModelEvaluationRepository,
    PredictionModelRepository,
    PredictionRunRepository,
)
from app.db.repositories.scenario_repositories import (
    ScenarioDefinitionRepository,
    ScenarioFeatureOverlayRepository,
    ScenarioImpactRepository,
    ScenarioResultRepository,
    ScenarioRunRepository,
    ScenarioTriggerEventRepository,
    ScenarioVersionRepository,
    ScenarioWatchRepository,
)
from app.db.repositories.security_repositories import (
    IdentityProviderRepository,
    RoleAssignmentRepository,
    SecurityAuditEventRepository,
    SecurityPrincipalRepository,
)
from app.db.repositories.sql_repositories import (
    SqlAssessmentRepository,
    SqlAuditEventRepository,
    SqlCatalogRepository,
    SqlHumanReviewRepository,
    SqlLeadershipBriefRepository,
    SqlSimulationRepository,
)
from app.domain.tenant_context import normalize_tenant_id
from app.repositories.catalog_repository import CatalogRepository
from app.security.rls import set_transaction_tenant

T = TypeVar("T")


class UnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.catalog: CatalogRepository = SqlCatalogRepository(session)
        self.assessments = SqlAssessmentRepository(session)
        self.simulations = SqlSimulationRepository(session)
        self.reviews = SqlHumanReviewRepository(session)
        self.leadership_briefs = SqlLeadershipBriefRepository(session)
        self.audit_events = SqlAuditEventRepository(session)
        # Phase 3 enterprise data-foundation repositories (all tenant-scoped).
        self.organizations = OrganizationRepository(session)
        self.engineer_profiles = EngineerProfileRepository(session)
        self.enterprise_catalog = EnterpriseCatalogRepository(session)
        self.initiatives_projects = InitiativeProjectRepository(session)
        self.delivery = DeliveryRepository(session)
        self.relationships = RelationshipRepository(session)
        self.data_sources = DataSourceRepository(session)
        self.ingestion_runs = IngestionRunRepository(session)
        self.evidence_signals = EvidenceSignalRepository(session)
        # Phase 3 Prompt 2 connector ingestion repositories.
        self.connector_checkpoints = ConnectorCheckpointRepository(session)
        self.ingestion_receipts = IngestionReceiptRepository(session)
        self.ingestion_dead_letters = IngestionDeadLetterRepository(session)
        self.pull_requests = PullRequestRepository(session)
        # Phase 3 Prompt 3 delivery graph repositories.
        self.graph_nodes = GraphNodeRepository(session)
        self.graph_edges = GraphEdgeRepository(session)
        self.graph_projection_runs = GraphProjectionRunRepository(session)
        self.graph_analysis_runs = GraphAnalysisRunRepository(session)
        self.graph_findings = GraphFindingRepository(session)
        # Phase 3 Prompt 4 delivery prediction repositories.
        self.delivery_outcomes = DeliveryOutcomeRepository(session)
        self.prediction_feature_snapshots = PredictionFeatureSnapshotRepository(session)
        self.prediction_datasets = PredictionDatasetManifestRepository(session)
        self.prediction_models = PredictionModelRepository(session)
        self.prediction_evaluations = PredictionModelEvaluationRepository(session)
        self.prediction_runs = PredictionRunRepository(session)
        self.delivery_predictions = DeliveryPredictionRepository(session)
        self.prediction_factors = PredictionFactorRepository(session)
        # Phase 3 Prompt 5 continuous scenario intelligence repositories.
        self.scenario_definitions = ScenarioDefinitionRepository(session)
        self.scenario_versions = ScenarioVersionRepository(session)
        self.scenario_watches = ScenarioWatchRepository(session)
        self.scenario_trigger_events = ScenarioTriggerEventRepository(session)
        self.scenario_runs = ScenarioRunRepository(session)
        self.scenario_feature_overlays = ScenarioFeatureOverlayRepository(session)
        self.scenario_results = ScenarioResultRepository(session)
        self.scenario_impacts = ScenarioImpactRepository(session)
        # Phase 3 Prompt 6 AI Chief of Staff repositories.
        self.cos_evidence_snapshots = CosEvidenceSnapshotRepository(session)
        self.cos_runs = CosRunRepository(session)
        self.cos_briefs = CosBriefRepository(session)
        self.cos_reviews = CosReviewRepository(session)
        # Phase 3 Prompt 7 enterprise security repositories.
        self.identity_providers = IdentityProviderRepository(session)
        self.security_principals = SecurityPrincipalRepository(session)
        self.role_assignments = RoleAssignmentRepository(session)
        self.security_audit_events = SecurityAuditEventRepository(session)
        # Phase 3 Prompt 8 observability & AI-quality repositories.
        self.metric_rollups = MetricRollupRepository(session)
        self.slo_definitions = SloDefinitionRepository(session)
        self.slo_evaluations = SloEvaluationRepository(session)
        self.alert_events = AlertEventRepository(session)
        self.ai_evaluation_datasets = AiEvaluationDatasetRepository(session)
        self.ai_evaluation_cases = AiEvaluationCaseRepository(session)
        self.ai_evaluation_runs = AiEvaluationRunRepository(session)
        self.ai_evaluation_results = AiEvaluationResultRepository(session)
        self.prediction_quality_snapshots = PredictionQualitySnapshotRepository(session)
        # Pending telemetry flushed only after a durable commit so a rolled-back
        # transaction never reports committed-success domain samples.
        self._pending_audit_successes: int = 0
        self._pending_telemetry: list[Callable[[], None]] = []

    def note_pending_audit_success(self) -> None:
        """Queue one audit-write success sample for emission on the next commit."""
        self._pending_audit_successes += 1

    def note_pending_telemetry(self, emit: Callable[[], None]) -> None:
        """Queue a fail-open domain telemetry emission for the next durable commit."""
        self._pending_telemetry.append(emit)

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            # A failed durable commit must never leave success samples queued for a
            # later flush; clear before re-raising (mirrors rollback semantics).
            self._pending_audit_successes = 0
            self._pending_telemetry = []
            raise
        pending_audit = self._pending_audit_successes
        pending_tel = list(self._pending_telemetry)
        self._pending_audit_successes = 0
        self._pending_telemetry = []
        if pending_audit:
            # Deferred import keeps UoW free of a hard observability import cycle
            # at module load; emission is fail-open.
            from app.observability.domain import record_audit_succeeded

            for _ in range(pending_audit):
                record_audit_succeeded()
        for emit in pending_tel:
            try:
                emit()
            except Exception:  # noqa: BLE001 - telemetry never breaks commit
                pass

    def rollback(self) -> None:
        self.session.rollback()
        self._pending_audit_successes = 0
        self._pending_telemetry = []

    def execute(self, callback: Callable[["UnitOfWork"], T]) -> T:
        """Run ``callback`` then commit; roll back on failure.

        Does not establish PostgreSQL RLS tenant context. Prefer
        :meth:`execute_for_tenant` for any tenant-scoped enterprise work under
        FORCE RLS — a prior ``commit``/``rollback`` clears ``SET LOCAL`` and a
        bare ``execute`` would otherwise query without a tenant GUC.
        """
        try:
            result = callback(self)
            self.commit()
            return result
        except Exception:
            self.rollback()
            raise

    def execute_for_tenant(self, tenant_id: str, callback: Callable[["UnitOfWork"], T]) -> T:
        """Run tenant-scoped work in one transaction with RLS context.

        Lifecycle (PostgreSQL)::

            begin (implicit) → SET LOCAL signalforge.current_tenant_id
            → callback → commit | rollback

        ``tenant_id`` must be a trusted, already-authenticated boundary
        (``TenantContext`` / ``SecurityContext``), never a request body field or
        target entity id. On SQLite, tenant GUC application is a no-op.
        Commit/rollback clear transaction-local GUCs; the next call re-applies.
        """
        trusted = normalize_tenant_id(tenant_id)
        try:
            set_transaction_tenant(self.session, trusted)
            result = callback(self)
            self.commit()
            return result
        except Exception:
            self.rollback()
            raise
