"""As-of feature extraction for project/initiative delivery prediction."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from app.db.models import assessment as assessment_orm
from app.db.models import enterprise as ent_orm
from app.db.models import graph as graph_orm
from app.db.models import prediction as pred_orm
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.graph_enums import (
    GRAPH_ANALYSIS_VERSION,
    GRAPH_PROJECTION_VERSION,
    GraphEdgeType,
    GraphFindingSeverity,
    GraphFindingType,
    GraphNodeType,
    GraphProjectionRunState,
)
from app.domain.prediction_constants import (
    DEFAULT_HORIZON_DAYS,
    FEATURE_SCHEMA_VERSION,
    MAX_DATA_QUALITY_WARNINGS,
    MAX_LINEAGE_ENTRIES,
    SUPPORTED_HORIZONS,
)
from app.domain.prediction_enums import (
    PredictionDataQualityWarning,
    PredictionDataScope,
    PredictionTargetType,
)
from app.domain.prediction_models import FeatureLineageEntry, PredictionFeatureSnapshot
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseNotFoundError, EnterpriseValidationError
from app.services.graph.projection_service import graph_node_id
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.feature_schema import (
    FEATURE_DEFINITIONS,
    FEATURE_NAMES,
    validate_feature_values,
)

logger = logging.getLogger("signalforge.prediction.features")

_CRITICALITY_SCORE = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.5,
    "low": 0.25,
}
_FAILED_DEPLOY = {"failed", "rolled_back"}
_WINDOW_30D = timedelta(days=30)
_TRANSFORM_VERSION = "v1"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hours_between(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 3600.0)


def _days_between(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


def _active_interval(valid_from: datetime, valid_to: datetime | None, as_of: datetime) -> bool:
    vf = _utc(valid_from)
    if vf > as_of:
        return False
    if valid_to is None:
        return True
    return _utc(valid_to) > as_of


def _work_item_state_at_cutoff(
    status: str,
    completed_at: datetime | None,
    as_of: datetime,
) -> str:
    """Classify a work item as of ``as_of`` without trusting mutable status alone.

    Completion is proven only by ``completed_at <= as_of``. Current ``done``
    status without a historical completion timestamp (or with completion after
    the cutoff) must not inject post-cutoff completion into historical features.
    """
    if status == "cancelled":
        return "cancelled"
    completed = _utc(completed_at) if completed_at is not None else None
    if completed is not None and completed <= as_of:
        return "done"
    return "open"


class FeatureExtractor:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def extract(
        self,
        ctx: TenantContext,
        target_type: PredictionTargetType,
        target_id: str,
        as_of_at: datetime,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        data_scope: PredictionDataScope = PredictionDataScope.SYNTHETIC,
    ) -> PredictionFeatureSnapshot:
        if not isinstance(ctx, TenantContext):
            raise EnterpriseValidationError("TenantContext is required")
        if horizon_days not in SUPPORTED_HORIZONS:
            raise EnterpriseValidationError(
                f"Unsupported horizon_days={horizon_days}; allowed={sorted(SUPPORTED_HORIZONS)}"
            )
        as_of = _utc(as_of_at)
        as_of_iso = as_of.isoformat()

        existing = self._find_existing(
            ctx,
            target_type=target_type,
            target_id=target_id,
            as_of=as_of,
            horizon_days=horizon_days,
        )
        if existing is not None:
            return existing

        project, initiative = self._load_target(ctx, target_type, target_id)
        project_ids, initiative_ids = self._scope_ids(
            ctx, target_type, project, initiative, target_id
        )
        target_node_id = graph_node_id(
            ctx.tenant_id,
            GraphNodeType.PROJECT
            if target_type == PredictionTargetType.PROJECT
            else GraphNodeType.INITIATIVE,
            target_id,
        )

        feature_values: dict[str, float | None] = {name: None for name in FEATURE_NAMES}
        missingness: dict[str, int] = {name: 1 for name in FEATURE_NAMES}
        lineage: list[FeatureLineageEntry] = []
        warnings: list[str] = []
        high_watermarks: dict[str, str] = {}
        readiness_snapshot_id: str | None = None

        # --- readiness (read-only Phase 2 snapshots) ---
        readiness_snapshot_id = self._extract_readiness(
            ctx,
            project=project,
            as_of=as_of,
            feature_values=feature_values,
            missingness=missingness,
            lineage=lineage,
            warnings=warnings,
        )

        # --- capability / ownership / context ---
        self._extract_capability_and_ownership(
            ctx,
            target_type=target_type,
            target_id=target_id,
            project=project,
            initiative=initiative,
            project_ids=project_ids,
            as_of=as_of,
            feature_values=feature_values,
            missingness=missingness,
            lineage=lineage,
            warnings=warnings,
        )

        # --- graph ---
        self._extract_graph_features(
            ctx,
            target_node_id=target_node_id,
            as_of=as_of,
            feature_values=feature_values,
            missingness=missingness,
            lineage=lineage,
            warnings=warnings,
            high_watermarks=high_watermarks,
        )

        # --- workflow ---
        self._extract_workflow(
            ctx,
            project_ids=project_ids,
            initiative_ids=initiative_ids,
            as_of=as_of,
            feature_values=feature_values,
            missingness=missingness,
            lineage=lineage,
            warnings=warnings,
            high_watermarks=high_watermarks,
        )

        # --- evidence / data quality ---
        evidence_cutoff = self._extract_evidence_quality(
            ctx,
            target_type=target_type,
            target_id=target_id,
            project_ids=project_ids,
            initiative_ids=initiative_ids,
            as_of=as_of,
            feature_values=feature_values,
            missingness=missingness,
            lineage=lineage,
            warnings=warnings,
            high_watermarks=high_watermarks,
        )

        # --- project context ---
        self._extract_project_context(
            project=project,
            initiative=initiative,
            target_type=target_type,
            as_of=as_of,
            feature_values=feature_values,
            missingness=missingness,
            lineage=lineage,
        )

        # Apply zero missing policy where declared
        for meta in FEATURE_DEFINITIONS:
            if feature_values[meta.name] is None and meta.missing_policy == "zero":
                feature_values[meta.name] = 0.0
                missingness[meta.name] = 1

        schema_warnings = validate_feature_values(feature_values)
        for w in schema_warnings:
            if w.startswith("below_range:") or w.startswith("above_range:"):
                warnings.append(PredictionDataQualityWarning.FEATURE_OUTSIDE_TRAINING_RANGE.value)
                break
        high_missing = sum(1 for v in missingness.values() if v == 1)
        if high_missing > len(FEATURE_NAMES) * 0.4:
            warnings.append(PredictionDataQualityWarning.HIGH_MISSINGNESS.value)

        # Bound warnings / lineage
        uniq_warnings: list[str] = []
        for w in warnings:
            if w not in uniq_warnings:
                uniq_warnings.append(w)
        uniq_warnings = uniq_warnings[:MAX_DATA_QUALITY_WARNINGS]
        lineage = lineage[:MAX_LINEAGE_ENTRIES]

        feature_hash = snapshot_hash(
            {
                "feature_values": feature_values,
                "missingness_indicators": missingness,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "as_of_at": as_of_iso,
            }
        )
        snapshot_id = build_entity_id(
            "pfs",
            ctx.tenant_id,
            target_type.value,
            target_id,
            as_of_iso,
            str(horizon_days),
            FEATURE_SCHEMA_VERSION,
        )

        snapshot = PredictionFeatureSnapshot(
            tenant_id=ctx.tenant_id,
            prediction_feature_snapshot_id=snapshot_id,
            target_type=target_type,
            target_id=target_id,
            as_of_at=as_of,
            horizon_days=horizon_days,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            feature_values=feature_values,
            missingness_indicators=missingness,
            feature_lineage=lineage,
            source_high_watermarks=high_watermarks,
            graph_projection_version=GRAPH_PROJECTION_VERSION,
            graph_analysis_version=GRAPH_ANALYSIS_VERSION,
            evidence_cutoff_at=evidence_cutoff or as_of,
            readiness_snapshot_id=readiness_snapshot_id,
            feature_hash=feature_hash,
            data_scope=data_scope,
            data_quality_warnings=uniq_warnings,
        )
        self._persist(snapshot)
        logger.info(
            "prediction.feature_snapshot.created tenant_id=%s snapshot_id=%s target=%s/%s",
            ctx.tenant_id,
            snapshot_id,
            target_type.value,
            target_id,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Persistence / lookup
    # ------------------------------------------------------------------
    def _find_existing(
        self,
        ctx: TenantContext,
        *,
        target_type: PredictionTargetType,
        target_id: str,
        as_of: datetime,
        horizon_days: int,
    ) -> PredictionFeatureSnapshot | None:
        row = self._uow.session.scalar(
            select(pred_orm.PredictionFeatureSnapshot).where(
                pred_orm.PredictionFeatureSnapshot.tenant_id == ctx.tenant_id,
                pred_orm.PredictionFeatureSnapshot.target_type == target_type.value,
                pred_orm.PredictionFeatureSnapshot.target_id == target_id,
                pred_orm.PredictionFeatureSnapshot.as_of_at == as_of,
                pred_orm.PredictionFeatureSnapshot.horizon_days == horizon_days,
                pred_orm.PredictionFeatureSnapshot.feature_schema_version == FEATURE_SCHEMA_VERSION,
            )
        )
        if row is None:
            return None
        return self._row_to_dto(row)

    def _persist(self, snapshot: PredictionFeatureSnapshot) -> None:
        payload = snapshot.model_dump(mode="json")
        # domain uses enum values already via mode=json
        row = pred_orm.PredictionFeatureSnapshot(
            prediction_feature_snapshot_id=snapshot.prediction_feature_snapshot_id,
            tenant_id=snapshot.tenant_id,
            target_type=snapshot.target_type.value,
            target_id=snapshot.target_id,
            as_of_at=snapshot.as_of_at,
            horizon_days=snapshot.horizon_days,
            feature_schema_version=snapshot.feature_schema_version,
            feature_values=payload["feature_values"],
            missingness_indicators=payload["missingness_indicators"],
            feature_lineage=payload["feature_lineage"],
            source_high_watermarks=payload["source_high_watermarks"],
            graph_projection_version=snapshot.graph_projection_version,
            graph_analysis_version=snapshot.graph_analysis_version,
            evidence_cutoff_at=snapshot.evidence_cutoff_at,
            readiness_snapshot_id=snapshot.readiness_snapshot_id,
            feature_hash=snapshot.feature_hash,
            data_scope=snapshot.data_scope.value,
            data_quality_warnings=payload["data_quality_warnings"],
        )
        self._uow.session.add(row)
        self._uow.session.flush()

    @staticmethod
    def _row_to_dto(row: pred_orm.PredictionFeatureSnapshot) -> PredictionFeatureSnapshot:
        lineage = [
            FeatureLineageEntry.model_validate(entry)
            if not isinstance(entry, FeatureLineageEntry)
            else entry
            for entry in (row.feature_lineage or [])
        ]
        return PredictionFeatureSnapshot(
            tenant_id=row.tenant_id,
            prediction_feature_snapshot_id=row.prediction_feature_snapshot_id,
            target_type=PredictionTargetType(row.target_type),
            target_id=row.target_id,
            as_of_at=_utc(row.as_of_at),
            horizon_days=row.horizon_days,
            feature_schema_version=row.feature_schema_version,
            feature_values=dict(row.feature_values or {}),
            missingness_indicators={
                k: int(v) for k, v in (row.missingness_indicators or {}).items()
            },
            feature_lineage=lineage,
            source_high_watermarks=dict(row.source_high_watermarks or {}),
            graph_projection_version=row.graph_projection_version,
            graph_analysis_version=row.graph_analysis_version,
            evidence_cutoff_at=_utc(row.evidence_cutoff_at),
            readiness_snapshot_id=row.readiness_snapshot_id,
            feature_hash=row.feature_hash,
            data_scope=PredictionDataScope(row.data_scope),
            data_quality_warnings=list(row.data_quality_warnings or []),
            created_at=_utc(row.created_at) if row.created_at else None,
        )

    # ------------------------------------------------------------------
    # Target loading
    # ------------------------------------------------------------------
    def _load_target(
        self,
        ctx: TenantContext,
        target_type: PredictionTargetType,
        target_id: str,
    ) -> tuple[ent_orm.EnterpriseProject | None, ent_orm.Initiative | None]:
        if target_type == PredictionTargetType.PROJECT:
            project = self._uow.session.scalar(
                select(ent_orm.EnterpriseProject).where(
                    ent_orm.EnterpriseProject.tenant_id == ctx.tenant_id,
                    ent_orm.EnterpriseProject.enterprise_project_id == target_id,
                )
            )
            if project is None:
                raise EnterpriseNotFoundError("Project not found for this tenant")
            initiative = None
            if project.initiative_id:
                initiative = self._uow.session.scalar(
                    select(ent_orm.Initiative).where(
                        ent_orm.Initiative.tenant_id == ctx.tenant_id,
                        ent_orm.Initiative.initiative_id == project.initiative_id,
                    )
                )
            return project, initiative

        initiative = self._uow.session.scalar(
            select(ent_orm.Initiative).where(
                ent_orm.Initiative.tenant_id == ctx.tenant_id,
                ent_orm.Initiative.initiative_id == target_id,
            )
        )
        if initiative is None:
            raise EnterpriseNotFoundError("Initiative not found for this tenant")
        return None, initiative

    def _scope_ids(
        self,
        ctx: TenantContext,
        target_type: PredictionTargetType,
        project: ent_orm.EnterpriseProject | None,
        initiative: ent_orm.Initiative | None,
        target_id: str,
    ) -> tuple[list[str], list[str]]:
        if target_type == PredictionTargetType.PROJECT:
            assert project is not None
            initiative_ids = [project.initiative_id] if project.initiative_id else []
            return [project.enterprise_project_id], initiative_ids

        assert initiative is not None
        projects = self._uow.session.scalars(
            select(ent_orm.EnterpriseProject).where(
                ent_orm.EnterpriseProject.tenant_id == ctx.tenant_id,
                ent_orm.EnterpriseProject.initiative_id == target_id,
            )
        ).all()
        return [p.enterprise_project_id for p in projects], [initiative.initiative_id]

    # ------------------------------------------------------------------
    # Feature family extractors
    # ------------------------------------------------------------------
    def _set(
        self,
        feature_values: dict[str, float | None],
        missingness: dict[str, int],
        name: str,
        value: float | None,
        *,
        present: bool,
    ) -> None:
        feature_values[name] = value
        missingness[name] = 0 if present and value is not None else 1

    def _lineage_add(
        self,
        lineage: list[FeatureLineageEntry],
        *,
        feature_name: str,
        entity_type: str,
        entity_id: str,
        timestamp: datetime | None,
        rule: str,
    ) -> None:
        if len(lineage) >= MAX_LINEAGE_ENTRIES:
            return
        lineage.append(
            FeatureLineageEntry(
                feature_name=feature_name,
                source_entity_type=entity_type,
                source_entity_id=entity_id[:64],
                source_timestamp=timestamp,
                transformation_rule=rule[:128],
                transformation_version=_TRANSFORM_VERSION,
            )
        )

    def _extract_readiness(
        self,
        ctx: TenantContext,
        *,
        project: ent_orm.EnterpriseProject | None,
        as_of: datetime,
        feature_values: dict[str, float | None],
        missingness: dict[str, int],
        lineage: list[FeatureLineageEntry],
        warnings: list[str],
    ) -> str | None:
        legacy_id = project.legacy_project_id if project is not None else None
        if not legacy_id:
            warnings.append(PredictionDataQualityWarning.INSUFFICIENT_HISTORY.value)
            return None

        row = self._uow.session.scalar(
            select(assessment_orm.Assessment)
            .where(
                assessment_orm.Assessment.project_id == legacy_id.strip().lower(),
                assessment_orm.Assessment.created_at <= as_of,
            )
            .order_by(
                assessment_orm.Assessment.created_at.desc(),
                assessment_orm.Assessment.assessment_record_id.desc(),
            )
            .limit(1)
        )
        if row is None:
            warnings.append(PredictionDataQualityWarning.INSUFFICIENT_HISTORY.value)
            return None

        self._set(
            feature_values,
            missingness,
            "readiness_score_at_cutoff",
            float(row.readiness_score),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "assessment_confidence_at_cutoff",
            float(row.confidence_score),
            present=True,
        )
        self._lineage_add(
            lineage,
            feature_name="readiness_score_at_cutoff",
            entity_type="assessment",
            entity_id=str(row.assessment_record_id),
            timestamp=_utc(row.created_at),
            rule="latest_assessment_before_cutoff",
        )
        self._lineage_add(
            lineage,
            feature_name="assessment_confidence_at_cutoff",
            entity_type="assessment",
            entity_id=str(row.assessment_record_id),
            timestamp=_utc(row.created_at),
            rule="latest_assessment_before_cutoff",
        )

        critical_risks = self._uow.session.scalars(
            select(assessment_orm.AssessmentRiskFinding).where(
                assessment_orm.AssessmentRiskFinding.assessment_record_id
                == row.assessment_record_id,
                assessment_orm.AssessmentRiskFinding.severity == "critical",
            )
        ).all()
        self._set(
            feature_values,
            missingness,
            "unresolved_critical_risk_count",
            float(len(critical_risks)),
            present=True,
        )
        return str(row.assessment_record_id)

    def _extract_capability_and_ownership(
        self,
        ctx: TenantContext,
        *,
        target_type: PredictionTargetType,
        target_id: str,
        project: ent_orm.EnterpriseProject | None,
        initiative: ent_orm.Initiative | None,
        project_ids: list[str],
        as_of: datetime,
        feature_values: dict[str, float | None],
        missingness: dict[str, int],
        lineage: list[FeatureLineageEntry],
        warnings: list[str],
    ) -> None:
        subject_type = "project" if target_type == PredictionTargetType.PROJECT else "initiative"
        # Filter by created_at <= as_of so requirements added after cutoff cannot
        # enter historical ownership/coverage features.
        requirements = list(
            self._uow.session.scalars(
                select(ent_orm.CapabilityRequirement).where(
                    ent_orm.CapabilityRequirement.tenant_id == ctx.tenant_id,
                    ent_orm.CapabilityRequirement.subject_type == subject_type,
                    ent_orm.CapabilityRequirement.subject_id == target_id,
                    ent_orm.CapabilityRequirement.created_at <= as_of,
                )
            ).all()
        )
        # Also include project requirements when target is initiative
        if target_type == PredictionTargetType.INITIATIVE and project_ids:
            requirements.extend(
                self._uow.session.scalars(
                    select(ent_orm.CapabilityRequirement).where(
                        ent_orm.CapabilityRequirement.tenant_id == ctx.tenant_id,
                        ent_orm.CapabilityRequirement.subject_type == "project",
                        ent_orm.CapabilityRequirement.subject_id.in_(project_ids),
                        ent_orm.CapabilityRequirement.created_at <= as_of,
                    )
                ).all()
            )

        ownerships = list(
            self._uow.session.scalars(
                select(ent_orm.Ownership).where(ent_orm.Ownership.tenant_id == ctx.tenant_id)
            ).all()
        )
        active_ownerships = [
            o for o in ownerships if _active_interval(o.valid_from, o.valid_to, as_of)
        ]

        resource_ids = {target_id, *project_ids}
        if initiative is not None:
            resource_ids.add(initiative.initiative_id)

        scoped = [
            o
            for o in active_ownerships
            if o.resource_id in resource_ids
            or (
                o.resource_type == "capability"
                and any(r.capability_id == o.resource_id for r in requirements)
            )
        ]

        engineer_owners = {
            o.owner_id for o in scoped if o.owner_type in {"engineer_profile", "engineer"}
        }
        team_owners = {o.owner_id for o in scoped if o.owner_type == "team"}
        self._set(
            feature_values,
            missingness,
            "active_engineer_owner_count",
            float(len(engineer_owners)),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "active_team_owner_count",
            float(len(team_owners)),
            present=True,
        )

        by_resource: dict[str, int] = defaultdict(int)
        for o in scoped:
            by_resource[o.resource_id] += 1
        redundancy = sum(by_resource.values()) / len(by_resource) if by_resource else None
        self._set(
            feature_values,
            missingness,
            "ownership_redundancy",
            float(redundancy) if redundancy is not None else None,
            present=redundancy is not None,
        )

        owned_caps = {o.resource_id for o in active_ownerships if o.resource_type == "capability"}
        required_ids = {r.capability_id for r in requirements}
        covered = required_ids & owned_caps if required_ids else set()
        coverage = (len(covered) / len(required_ids)) if required_ids else None
        self._set(
            feature_values,
            missingness,
            "capability_coverage",
            float(coverage) if coverage is not None else None,
            present=coverage is not None,
        )
        self._set(
            feature_values,
            missingness,
            "required_capability_count",
            float(len(required_ids)),
            present=True,
        )

        critical_reqs = [r for r in requirements if r.criticality == "critical"]
        critical_gaps = sum(1 for r in critical_reqs if r.capability_id not in owned_caps)
        self._set(
            feature_values,
            missingness,
            "critical_capability_gap_count",
            float(critical_gaps),
            present=True,
        )

        critical_cap_ids = {r.capability_id for r in critical_reqs}
        crit_owners = {
            o.owner_id
            for o in active_ownerships
            if o.resource_type == "capability" and o.resource_id in critical_cap_ids
        }
        self._set(
            feature_values,
            missingness,
            "critical_capability_owner_count",
            float(len(crit_owners)),
            present=True,
        )

        availabilities = list(
            self._uow.session.scalars(
                select(ent_orm.Availability).where(
                    ent_orm.Availability.tenant_id == ctx.tenant_id,
                    ent_orm.Availability.start_time <= as_of,
                    ent_orm.Availability.end_time > as_of,
                )
            ).all()
        )
        unavailable = 0
        for eid in engineer_owners:
            windows = [
                a
                for a in availabilities
                if a.target_id == eid and a.target_type in {"engineer_profile", "engineer"}
            ]
            if any(
                (a.availability_percentage is not None and a.availability_percentage < 50)
                for a in windows
            ):
                unavailable += 1
        unavailable_ratio = unavailable / len(engineer_owners) if engineer_owners else None
        self._set(
            feature_values,
            missingness,
            "unavailable_owner_ratio",
            float(unavailable_ratio) if unavailable_ratio is not None else None,
            present=unavailable_ratio is not None,
        )

        team_ids = set(team_owners)
        if project is not None and project.owning_team_id:
            team_ids.add(project.owning_team_id)
        team_ratios: list[float] = []
        for tid in team_ids:
            windows = [a for a in availabilities if a.target_id == tid and a.target_type == "team"]
            if not windows:
                continue
            pcts = [
                (a.availability_percentage / 100.0)
                for a in windows
                if a.availability_percentage is not None
            ]
            if pcts:
                team_ratios.append(sum(pcts) / len(pcts))
        team_ratio = sum(team_ratios) / len(team_ratios) if team_ratios else None
        self._set(
            feature_values,
            missingness,
            "team_availability_ratio",
            float(team_ratio) if team_ratio is not None else None,
            present=team_ratio is not None,
        )

        missing_owner = 1.0 if not engineer_owners and not team_owners else 0.0
        self._set(
            feature_values,
            missingness,
            "missing_owner_indicator",
            missing_owner,
            present=True,
        )
        if missing_owner == 1.0:
            warnings.append(PredictionDataQualityWarning.MISSING_OWNER.value)

        if scoped:
            self._lineage_add(
                lineage,
                feature_name="active_engineer_owner_count",
                entity_type="ownership",
                entity_id=scoped[0].ownership_id,
                timestamp=_utc(scoped[0].valid_from),
                rule="active_ownership_at_cutoff",
            )

    def _extract_graph_features(
        self,
        ctx: TenantContext,
        *,
        target_node_id: str,
        as_of: datetime,
        feature_values: dict[str, float | None],
        missingness: dict[str, int],
        lineage: list[FeatureLineageEntry],
        warnings: list[str],
        high_watermarks: dict[str, str],
    ) -> None:
        edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx, active_at=as_of, max_edges=5000
        )
        if not edges:
            warnings.append(PredictionDataQualityWarning.GRAPH_UNAVAILABLE.value)

        dep_types = {GraphEdgeType.DEPENDS_ON, GraphEdgeType.BLOCKS}
        dep_edges = [e for e in edges if e.edge_type in dep_types]
        touching = [
            e
            for e in dep_edges
            if e.source_node_id == target_node_id or e.target_node_id == target_node_id
        ]
        self._set(
            feature_values,
            missingness,
            "active_dependency_count",
            float(len(touching)),
            present=True,
        )

        # Bounded outbound depth
        outgoing: dict[str, list[str]] = defaultdict(list)
        for e in dep_edges:
            outgoing[e.source_node_id].append(e.target_node_id)
        depth = 0
        seen = {target_node_id}
        queue: deque[tuple[str, int]] = deque([(target_node_id, 0)])
        while queue:
            node, d = queue.popleft()
            depth = max(depth, d)
            if d >= 12:
                continue
            for nbr in outgoing.get(node, []):
                if nbr not in seen:
                    seen.add(nbr)
                    queue.append((nbr, d + 1))
        self._set(feature_values, missingness, "dependency_depth", float(depth), present=True)

        findings_page = self._uow.graph_findings.list_findings(
            ctx, active_at=as_of, limit=500, offset=0
        )
        findings = [
            f
            for f in findings_page.items
            if target_node_id == f.primary_node_id or target_node_id in (f.affected_node_ids or [])
        ]

        def count_type(ftype: GraphFindingType) -> float:
            return float(sum(1 for f in findings if f.finding_type == ftype))

        self._set(
            feature_values,
            missingness,
            "cross_team_dependency_count",
            count_type(GraphFindingType.CROSS_TEAM_DEPENDENCY),
            present=True,
        )
        cycle = 1.0 if count_type(GraphFindingType.DEPENDENCY_CYCLE) > 0 else 0.0
        self._set(
            feature_values,
            missingness,
            "active_dependency_cycle_indicator",
            cycle,
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "repository_ownership_concentration_count",
            count_type(GraphFindingType.REPOSITORY_OWNERSHIP_CONCENTRATION),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "capability_ownership_concentration_count",
            count_type(GraphFindingType.CAPABILITY_OWNERSHIP_CONCENTRATION),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "single_person_dependency_count",
            count_type(GraphFindingType.SINGLE_PERSON_DEPENDENCY),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "availability_blast_radius_count",
            count_type(GraphFindingType.AVAILABILITY_BLAST_RADIUS),
            present=True,
        )

        # Affected critical initiatives via node lookup
        affected_nodes = set()
        for f in findings:
            affected_nodes.add(f.primary_node_id)
            affected_nodes.update(f.affected_node_ids or [])
        initiative_entity_ids: set[str] = set()
        if affected_nodes:
            nodes = self._uow.session.scalars(
                select(graph_orm.DeliveryGraphNode).where(
                    graph_orm.DeliveryGraphNode.tenant_id == ctx.tenant_id,
                    graph_orm.DeliveryGraphNode.graph_node_id.in_(sorted(affected_nodes)),
                    graph_orm.DeliveryGraphNode.node_type == GraphNodeType.INITIATIVE.value,
                )
            ).all()
            initiative_entity_ids = {n.entity_id for n in nodes}
        critical_count = 0
        if initiative_entity_ids:
            crit = self._uow.session.scalars(
                select(ent_orm.Initiative).where(
                    ent_orm.Initiative.tenant_id == ctx.tenant_id,
                    ent_orm.Initiative.initiative_id.in_(sorted(initiative_entity_ids)),
                    ent_orm.Initiative.criticality == "critical",
                )
            ).all()
            critical_count = len(crit)
        self._set(
            feature_values,
            missingness,
            "affected_critical_initiative_count",
            float(critical_count),
            present=True,
        )

        sev_counts = {
            GraphFindingSeverity.CRITICAL: 0,
            GraphFindingSeverity.HIGH: 0,
            GraphFindingSeverity.MEDIUM: 0,
            GraphFindingSeverity.LOW: 0,
        }
        unresolved_actor = 0
        for f in findings:
            if f.severity in sev_counts:
                sev_counts[f.severity] += 1
            for w in f.data_quality_warnings or []:
                val = w.value if hasattr(w, "value") else str(w)
                if val == "unresolved_actor_identity":
                    unresolved_actor += 1
        self._set(
            feature_values,
            missingness,
            "finding_severity_critical_count",
            float(sev_counts[GraphFindingSeverity.CRITICAL]),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "finding_severity_high_count",
            float(sev_counts[GraphFindingSeverity.HIGH]),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "finding_severity_medium_count",
            float(sev_counts[GraphFindingSeverity.MEDIUM]),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "finding_severity_low_count",
            float(sev_counts[GraphFindingSeverity.LOW]),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "unresolved_actor_identity_count",
            float(unresolved_actor),
            present=True,
        )

        if findings:
            self._lineage_add(
                lineage,
                feature_name="finding_severity_critical_count",
                entity_type="graph_finding",
                entity_id=findings[0].graph_finding_id,
                timestamp=_utc(findings[0].detected_at),
                rule="active_findings_at_cutoff",
            )
            high_watermarks["graph_finding"] = max(
                (_utc(f.detected_at).isoformat() for f in findings),
                default=as_of.isoformat(),
            )

        # Projection age
        proj = self._uow.session.scalar(
            select(graph_orm.GraphProjectionRun)
            .where(
                graph_orm.GraphProjectionRun.tenant_id == ctx.tenant_id,
                graph_orm.GraphProjectionRun.state == GraphProjectionRunState.SUCCEEDED.value,
                graph_orm.GraphProjectionRun.completed_at.isnot(None),
                graph_orm.GraphProjectionRun.completed_at <= as_of,
            )
            .order_by(graph_orm.GraphProjectionRun.completed_at.desc())
            .limit(1)
        )
        if proj is not None and proj.completed_at is not None:
            age = _hours_between(as_of, _utc(proj.completed_at))
            self._set(
                feature_values,
                missingness,
                "graph_projection_age_hours",
                float(age),
                present=True,
            )
            high_watermarks["graph_projection"] = _utc(proj.completed_at).isoformat()
            if age > 72:
                warnings.append(PredictionDataQualityWarning.GRAPH_NOT_CURRENT.value)
        else:
            warnings.append(PredictionDataQualityWarning.GRAPH_UNAVAILABLE.value)

    def _extract_workflow(
        self,
        ctx: TenantContext,
        *,
        project_ids: list[str],
        initiative_ids: list[str],
        as_of: datetime,
        feature_values: dict[str, float | None],
        missingness: dict[str, int],
        lineage: list[FeatureLineageEntry],
        warnings: list[str],
        high_watermarks: dict[str, str],
    ) -> None:
        wi_filters = [ent_orm.WorkItem.tenant_id == ctx.tenant_id]
        scope_clauses = []
        if project_ids:
            scope_clauses.append(ent_orm.WorkItem.enterprise_project_id.in_(project_ids))
        if initiative_ids:
            scope_clauses.append(ent_orm.WorkItem.initiative_id.in_(initiative_ids))
        if scope_clauses:
            wi_filters.append(or_(*scope_clauses))
        else:
            # No scoped projects under initiative — empty workflow
            for name in (
                "open_work_item_count",
                "overdue_work_item_count",
                "blocked_work_item_count",
                "deployment_count_30d",
                "failed_deployment_count_30d",
                "incident_count_30d",
                "unresolved_incident_count",
                "pr_open_count",
                "unreviewed_pr_count",
            ):
                self._set(feature_values, missingness, name, 0.0, present=True)
            return

        work_items = list(
            self._uow.session.scalars(
                select(ent_orm.WorkItem).where(
                    and_(*wi_filters),
                    or_(
                        ent_orm.WorkItem.source_created_at.is_(None),
                        ent_orm.WorkItem.source_created_at <= as_of,
                    ),
                )
            ).all()
        )
        # Historical open/done from completed_at only — never trust mutable status
        # alone (status may flip to done after the cutoff without a past timestamp).
        open_items = []
        done_items = []
        for wi in work_items:
            state = _work_item_state_at_cutoff(wi.status, wi.completed_at, as_of)
            if state == "done":
                done_items.append(wi)
            elif state == "open":
                open_items.append(wi)

        self._set(
            feature_values,
            missingness,
            "open_work_item_count",
            float(len(open_items)),
            present=True,
        )

        sprint_ids = {wi.sprint_id for wi in open_items if wi.sprint_id}
        sprints_by_id: dict[str, ent_orm.Sprint] = {}
        if sprint_ids:
            for s in self._uow.session.scalars(
                select(ent_orm.Sprint).where(
                    ent_orm.Sprint.tenant_id == ctx.tenant_id,
                    ent_orm.Sprint.sprint_id.in_(sorted(sprint_ids)),
                )
            ).all():
                sprints_by_id[s.sprint_id] = s
        overdue = 0
        for wi in open_items:
            if not wi.sprint_id:
                continue
            sprint = sprints_by_id.get(wi.sprint_id)
            if sprint is not None and _utc(sprint.end_time) < as_of:
                overdue += 1
        self._set(
            feature_values,
            missingness,
            "overdue_work_item_count",
            float(overdue),
            present=True,
        )

        # Blocked via graph BLOCKS edges onto work-item nodes
        wi_node_ids = {
            graph_node_id(ctx.tenant_id, GraphNodeType.WORK_ITEM, wi.work_item_id)
            for wi in open_items
        }
        blocked = 0
        if wi_node_ids:
            block_edges = self._uow.graph_edges.list_active_edges_for_traversal(
                ctx,
                active_at=as_of,
                edge_types=[GraphEdgeType.BLOCKS],
                max_edges=5000,
            )
            blocked_nodes = {
                e.target_node_id for e in block_edges if e.target_node_id in wi_node_ids
            }
            blocked = len(blocked_nodes)
        self._set(
            feature_values,
            missingness,
            "blocked_work_item_count",
            float(blocked),
            present=True,
        )

        ages = []
        for wi in open_items:
            created = wi.source_created_at or wi.source_updated_at
            if created is not None:
                ages.append(_days_between(as_of, _utc(created)))
        self._set(
            feature_values,
            missingness,
            "work_item_aging_days_avg",
            (sum(ages) / len(ages)) if ages else None,
            present=bool(ages),
        )

        # Sprint completion across scoped work items with sprint linkage
        with_sprint = [wi for wi in work_items if wi.sprint_id]
        all_sprint_ids = {wi.sprint_id for wi in with_sprint if wi.sprint_id}
        if all_sprint_ids:
            for s in self._uow.session.scalars(
                select(ent_orm.Sprint).where(
                    ent_orm.Sprint.tenant_id == ctx.tenant_id,
                    ent_orm.Sprint.sprint_id.in_(sorted(all_sprint_ids)),
                )
            ).all():
                sprints_by_id[s.sprint_id] = s
        relevant = []
        for wi in with_sprint:
            sprint = sprints_by_id.get(wi.sprint_id or "")
            if sprint is None:
                continue
            # Include sprints that had started by cutoff; do not trust mutable
            # sprint.state (may close after cutoff).
            if _utc(sprint.start_time) <= as_of:
                relevant.append(wi)
        done_n = 0
        open_n = 0
        for wi in relevant:
            state = _work_item_state_at_cutoff(wi.status, wi.completed_at, as_of)
            if state == "done":
                done_n += 1
            elif state == "open":
                open_n += 1
        denom = done_n + open_n
        ratio = (done_n / denom) if denom else None
        self._set(
            feature_values,
            missingness,
            "sprint_completion_ratio",
            float(ratio) if ratio is not None else None,
            present=ratio is not None,
        )

        # Repositories in scope via team membership and ownership
        repos = list(
            self._uow.session.scalars(
                select(ent_orm.Repository).where(ent_orm.Repository.tenant_id == ctx.tenant_id)
            ).all()
        )
        ownerships = list(
            self._uow.session.scalars(
                select(ent_orm.Ownership).where(
                    ent_orm.Ownership.tenant_id == ctx.tenant_id,
                    ent_orm.Ownership.resource_type == "repository",
                )
            ).all()
        )
        repo_ids: set[str] = set()
        resource_scope = set(project_ids) | set(initiative_ids)
        team_ids = {wi.team_id for wi in work_items if wi.team_id}
        for r in repos:
            if r.owning_team_id and r.owning_team_id in team_ids:
                repo_ids.add(r.repository_id)
        for o in ownerships:
            if not _active_interval(o.valid_from, o.valid_to, as_of):
                continue
            if o.owner_id in resource_scope or o.owner_id in team_ids:
                repo_ids.add(o.resource_id)

        self._set(
            feature_values,
            missingness,
            "repository_count",
            float(len(repo_ids)),
            present=True,
        )
        self._set(
            feature_values,
            missingness,
            "participating_team_count",
            float(len(team_ids)),
            present=True,
        )

        # Pull requests
        pr_query = select(ent_orm.PullRequest).where(
            ent_orm.PullRequest.tenant_id == ctx.tenant_id,
            or_(
                ent_orm.PullRequest.created_at_source.is_(None),
                ent_orm.PullRequest.created_at_source <= as_of,
            ),
        )
        if repo_ids:
            pr_query = pr_query.where(ent_orm.PullRequest.repository_id.in_(sorted(repo_ids)))
        prs = list(self._uow.session.scalars(pr_query).all()) if repo_ids else []
        open_prs = []
        for pr in prs:
            closed = pr.closed_at_source or pr.merged_at_source
            if closed is not None and _utc(closed) <= as_of:
                continue
            if pr.state == "open" or (
                pr.state != "merged"
                and (pr.closed_at_source is None or _utc(pr.closed_at_source) > as_of)
            ):
                open_prs.append(pr)
        self._set(
            feature_values,
            missingness,
            "pr_open_count",
            float(len(open_prs)),
            present=True,
        )
        pr_ages = []
        for pr in open_prs:
            if pr.created_at_source:
                pr_ages.append(_days_between(as_of, _utc(pr.created_at_source)))
        self._set(
            feature_values,
            missingness,
            "pr_age_days_avg",
            (sum(pr_ages) / len(pr_ages)) if pr_ages else None,
            present=bool(pr_ages),
        )

        review_edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx,
            active_at=as_of,
            edge_types=[GraphEdgeType.REVIEWS],
            max_edges=5000,
        )
        reviewed_pr_nodes = {e.target_node_id for e in review_edges} | {
            e.source_node_id for e in review_edges
        }
        unreviewed = 0
        for pr in open_prs:
            node = graph_node_id(ctx.tenant_id, GraphNodeType.PULL_REQUEST, pr.pull_request_id)
            if node not in reviewed_pr_nodes:
                unreviewed += 1
        self._set(
            feature_values,
            missingness,
            "unreviewed_pr_count",
            float(unreviewed),
            present=True,
        )

        # Review latency from merged/closed PRs at or before cutoff
        latencies: list[float] = []
        for pr in prs:
            end = pr.merged_at_source or pr.closed_at_source
            if end is None or pr.created_at_source is None:
                continue
            end_u = _utc(end)
            if end_u > as_of:
                continue
            latencies.append(_days_between(end_u, _utc(pr.created_at_source)))
        self._set(
            feature_values,
            missingness,
            "review_latency_days_avg",
            (sum(latencies) / len(latencies)) if latencies else None,
            present=bool(latencies),
        )

        window_start = as_of - _WINDOW_30D
        dep_scope = []
        if project_ids:
            dep_scope.append(ent_orm.Deployment.enterprise_project_id.in_(project_ids))
        if repo_ids:
            dep_scope.append(ent_orm.Deployment.repository_id.in_(sorted(repo_ids)))
        dep_filters = [
            ent_orm.Deployment.tenant_id == ctx.tenant_id,
            ent_orm.Deployment.started_at <= as_of,
            ent_orm.Deployment.started_at >= window_start,
        ]
        if dep_scope:
            dep_filters.append(or_(*dep_scope))
        deployments = (
            list(self._uow.session.scalars(select(ent_orm.Deployment).where(*dep_filters)).all())
            if dep_scope
            else []
        )
        usable_deps: list[tuple[str, ent_orm.Deployment]] = []
        for d in deployments:
            if d.completed_at is not None and _utc(d.completed_at) > as_of:
                usable_deps.append(("pending", d))
            else:
                usable_deps.append((d.status, d))
        self._set(
            feature_values,
            missingness,
            "deployment_count_30d",
            float(len(usable_deps)),
            present=True,
        )
        failed = sum(1 for status, _ in usable_deps if status in _FAILED_DEPLOY)
        self._set(
            feature_values,
            missingness,
            "failed_deployment_count_30d",
            float(failed),
            present=True,
        )

        inc_scope = []
        if project_ids:
            inc_scope.append(ent_orm.Incident.enterprise_project_id.in_(project_ids))
        if repo_ids:
            inc_scope.append(ent_orm.Incident.repository_id.in_(sorted(repo_ids)))
        inc_filters = [
            ent_orm.Incident.tenant_id == ctx.tenant_id,
            ent_orm.Incident.started_at <= as_of,
        ]
        if inc_scope:
            inc_filters.append(or_(*inc_scope))
        incidents = (
            list(self._uow.session.scalars(select(ent_orm.Incident).where(*inc_filters)).all())
            if inc_scope
            else []
        )
        incidents_30d = [i for i in incidents if _utc(i.started_at) >= window_start]
        self._set(
            feature_values,
            missingness,
            "incident_count_30d",
            float(len(incidents_30d)),
            present=True,
        )
        unresolved = 0
        for i in incidents:
            resolved = _utc(i.resolved_at) if i.resolved_at else None
            if resolved is None or resolved > as_of:
                unresolved += 1
        self._set(
            feature_values,
            missingness,
            "unresolved_incident_count",
            float(unresolved),
            present=True,
        )

        if work_items:
            self._lineage_add(
                lineage,
                feature_name="open_work_item_count",
                entity_type="work_item",
                entity_id=work_items[0].work_item_id,
                timestamp=_utc(work_items[0].source_created_at)
                if work_items[0].source_created_at
                else as_of,
                rule="open_at_cutoff",
            )
            stamps = [
                _utc(wi.source_updated_at).isoformat()
                for wi in work_items
                if wi.source_updated_at is not None and _utc(wi.source_updated_at) <= as_of
            ]
            if stamps:
                high_watermarks["work_item"] = max(stamps)

        missing_team = sum(1 for wi in work_items if not wi.team_id)
        missing_team += sum(
            1 for r in repos if r.repository_id in repo_ids and not r.owning_team_id
        )
        self._set(
            feature_values,
            missingness,
            "missing_team_mapping_count",
            float(missing_team),
            present=True,
        )

    def _extract_evidence_quality(
        self,
        ctx: TenantContext,
        *,
        target_type: PredictionTargetType,
        target_id: str,
        project_ids: list[str],
        initiative_ids: list[str],
        as_of: datetime,
        feature_values: dict[str, float | None],
        missingness: dict[str, int],
        lineage: list[FeatureLineageEntry],
        warnings: list[str],
        high_watermarks: dict[str, str],
    ) -> datetime | None:
        subject_ids = {target_id, *project_ids, *initiative_ids}
        signals = list(
            self._uow.session.scalars(
                select(ent_orm.EvidenceSignal).where(
                    ent_orm.EvidenceSignal.tenant_id == ctx.tenant_id,
                    ent_orm.EvidenceSignal.observed_at <= as_of,
                    ent_orm.EvidenceSignal.subject_id.in_(sorted(subject_ids)),
                )
            ).all()
        )
        evidence_cutoff = None
        if signals:
            evidence_cutoff = max(_utc(s.observed_at) for s in signals)
            age = _hours_between(as_of, evidence_cutoff)
            self._set(
                feature_values,
                missingness,
                "evidence_freshness_age_hours",
                float(age),
                present=True,
            )
            high_watermarks["evidence_signal"] = evidence_cutoff.isoformat()
            if age > 168:
                warnings.append(PredictionDataQualityWarning.STALE_EVIDENCE.value)
            self._lineage_add(
                lineage,
                feature_name="evidence_freshness_age_hours",
                entity_type="evidence_signal",
                entity_id=signals[0].evidence_signal_id,
                timestamp=evidence_cutoff,
                rule="max_observed_at_before_cutoff",
            )
        window_start = as_of - _WINDOW_30D
        vol = sum(1 for s in signals if _utc(s.observed_at) >= window_start)
        self._set(
            feature_values,
            missingness,
            "evidence_volume_30d",
            float(vol),
            present=True,
        )

        sources = list(
            self._uow.session.scalars(
                select(ent_orm.DataSource).where(
                    ent_orm.DataSource.tenant_id == ctx.tenant_id,
                    or_(
                        ent_orm.DataSource.archived_at.is_(None),
                        ent_orm.DataSource.archived_at > as_of,
                    ),
                )
            ).all()
        )
        if sources:
            synced = 0
            stale = 0
            for src in sources:
                # Staleness from timestamps as-of cutoff only — never current
                # freshness_state (mutable post-cutoff enum).
                last = src.last_successful_sync_at or src.last_ingestion_time
                last_utc = _utc(last) if last is not None else None
                if last_utc is not None and last_utc <= as_of:
                    synced += 1
                    if (as_of - last_utc).total_seconds() > src.stale_after_seconds:
                        stale += 1
                else:
                    stale += 1
            self._set(
                feature_values,
                missingness,
                "source_coverage_ratio",
                float(synced / len(sources)),
                present=True,
            )
            self._set(
                feature_values,
                missingness,
                "stale_source_count",
                float(stale),
                present=True,
            )
            if stale > 0:
                warnings.append(PredictionDataQualityWarning.STALE_SOURCE.value)
        else:
            self._set(feature_values, missingness, "source_coverage_ratio", None, present=False)
            self._set(feature_values, missingness, "stale_source_count", 0.0, present=True)

        open_wi = feature_values.get("open_work_item_count") or 0.0
        incomplete = 1.0 if vol < 1 or (vol < 3 and open_wi == 0.0) else 0.0
        self._set(
            feature_values,
            missingness,
            "incomplete_history_indicator",
            incomplete,
            present=True,
        )
        if incomplete == 1.0:
            warnings.append(PredictionDataQualityWarning.INCOMPLETE_HISTORY.value)

        return evidence_cutoff

    def _extract_project_context(
        self,
        *,
        project: ent_orm.EnterpriseProject | None,
        initiative: ent_orm.Initiative | None,
        target_type: PredictionTargetType,
        as_of: datetime,
        feature_values: dict[str, float | None],
        missingness: dict[str, int],
        lineage: list[FeatureLineageEntry],
    ) -> None:
        if project is not None:
            score = _CRITICALITY_SCORE.get(project.criticality, 0.5)
            self._set(
                feature_values,
                missingness,
                "project_criticality_score",
                score,
                present=True,
            )
            start = project.planned_start
            end = project.planned_target
            if start and end:
                self._set(
                    feature_values,
                    missingness,
                    "planned_duration_days",
                    _days_between(_utc(end), _utc(start)),
                    present=True,
                )
            else:
                self._set(feature_values, missingness, "planned_duration_days", None, present=False)
            if start:
                self._set(
                    feature_values,
                    missingness,
                    "project_age_days_at_cutoff",
                    _days_between(as_of, _utc(start)),
                    present=True,
                )
            else:
                self._set(
                    feature_values, missingness, "project_age_days_at_cutoff", None, present=False
                )
            self._lineage_add(
                lineage,
                feature_name="project_criticality_score",
                entity_type="project",
                entity_id=project.enterprise_project_id,
                timestamp=as_of,
                rule="criticality_ordinal_map",
            )
        else:
            self._set(feature_values, missingness, "project_criticality_score", None, present=False)
            if target_type == PredictionTargetType.INITIATIVE and initiative is not None:
                start = initiative.planned_start
                end = initiative.planned_target
                if start and end:
                    self._set(
                        feature_values,
                        missingness,
                        "planned_duration_days",
                        _days_between(_utc(end), _utc(start)),
                        present=True,
                    )
                else:
                    self._set(
                        feature_values, missingness, "planned_duration_days", None, present=False
                    )
                if start:
                    self._set(
                        feature_values,
                        missingness,
                        "project_age_days_at_cutoff",
                        _days_between(as_of, _utc(start)),
                        present=True,
                    )
                else:
                    self._set(
                        feature_values,
                        missingness,
                        "project_age_days_at_cutoff",
                        None,
                        present=False,
                    )

        if initiative is not None:
            score = _CRITICALITY_SCORE.get(initiative.criticality, 0.5)
            self._set(
                feature_values,
                missingness,
                "initiative_criticality_score",
                score,
                present=True,
            )
        else:
            self._set(
                feature_values, missingness, "initiative_criticality_score", None, present=False
            )
