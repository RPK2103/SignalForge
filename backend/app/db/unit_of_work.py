"""Unit of Work for atomic persistence transactions."""

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

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
from app.db.repositories.chief_of_staff_repositories import (
    CosBriefRepository,
    CosEvidenceSnapshotRepository,
    CosReviewRepository,
    CosRunRepository,
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
from app.db.repositories.sql_repositories import (
    SqlAssessmentRepository,
    SqlAuditEventRepository,
    SqlCatalogRepository,
    SqlHumanReviewRepository,
    SqlLeadershipBriefRepository,
    SqlSimulationRepository,
)
from app.repositories.catalog_repository import CatalogRepository

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

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def execute(self, callback: Callable[["UnitOfWork"], T]) -> T:
        try:
            result = callback(self)
            self.commit()
            return result
        except Exception:
            self.rollback()
            raise
