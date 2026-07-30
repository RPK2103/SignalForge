"""Temporal evidence assembly for Chief of Staff packages.

Reads immutable Prompt 1–5 outputs. Never recalculates readiness, graph findings,
predictions, or scenario impacts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.chief_of_staff_constants import (
    EVIDENCE_SCHEMA_VERSION,
    MAX_DETERMINISTIC_RISKS,
    MAX_EVIDENCE_SIGNALS,
    MAX_EVIDENCE_SUMMARY_CHARS,
    MAX_GRAPH_FINDINGS,
    MAX_SCENARIO_IMPACTS,
    MAX_SCENARIO_RUNS,
)
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffTargetType,
    EvidenceEntryType,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffEvidencePackage,
    ChiefOfStaffRequest,
    DeterministicChangeRecord,
    EvidenceEntry,
    FreshnessSummary,
    PredictionProvenanceSummary,
    PriorBriefReference,
    ScenarioComparability,
    TargetLifecycleInfo,
    TruncationMetadata,
)
from app.domain.enterprise_enums import EnterpriseEntityType
from app.domain.prediction_enums import EstimateKind
from app.domain.tenant_context import TenantContext
from app.services.chief_of_staff.canonicalization import attach_package_hash
from app.services.chief_of_staff.decision_options import compute_decision_options
from app.services.chief_of_staff.evidence_ids import build_evidence_id
from app.services.chief_of_staff.ordering import order_by_event_then_id, severity_rank
from app.services.chief_of_staff.prompt_injection import normalize_untrusted_text
from app.services.enterprise.exceptions import (
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)

_NOT_FOUND = "Resource not found for this tenant"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _payload_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _entry(
    *,
    evidence_type: EvidenceEntryType,
    tenant_id: str,
    source_type: str,
    source_record_id: str,
    summary: str,
    semantic_classification: str,
    provenance: str,
    source_event_time: datetime | None = None,
    observed_at: datetime | None = None,
    ingested_at: datetime | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    extra_hash_parts: tuple[str, ...] = (),
) -> EvidenceEntry:
    eid = build_evidence_id(evidence_type, tenant_id, source_record_id, *extra_hash_parts)
    return EvidenceEntry(
        evidence_id=eid,
        evidence_type=evidence_type,
        source_type=source_type,
        source_record_id=source_record_id,
        source_event_time=source_event_time,
        observed_at=observed_at,
        ingested_at=ingested_at,
        valid_from=valid_from,
        valid_to=valid_to,
        summary=normalize_untrusted_text(summary, MAX_EVIDENCE_SUMMARY_CHARS),
        semantic_classification=semantic_classification,
        provenance=provenance,
        payload_hash=_payload_hash(tenant_id, source_record_id, summary[:200], *extra_hash_parts),
        tenant_id=tenant_id,
    )


class EvidenceAssemblyService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def assemble(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
    ) -> ChiefOfStaffEvidencePackage:
        if request.tenant_id != ctx.tenant_id:
            raise EnterpriseValidationError("Request tenant does not match context")

        as_of = _utc(request.as_of_at)
        now = datetime.now(timezone.utc)
        if as_of > now:
            raise EnterpriseValidationError("as_of_at must not be in the future")

        lifecycle = self._load_target(ctx, request.target_type, request.target_id, as_of)
        missing: list[str] = []
        contradictions: list[str] = []
        entries: list[EvidenceEntry] = []

        target_entry = _entry(
            evidence_type=EvidenceEntryType.TARGET_METADATA,
            tenant_id=ctx.tenant_id,
            source_type=request.target_type.value,
            source_record_id=request.target_id,
            summary=(
                f"{lifecycle.display_name} ({request.target_type.value}) "
                f"criticality={lifecycle.criticality or 'unknown'} "
                f"state={lifecycle.lifecycle_state}"
            ),
            semantic_classification="target_metadata",
            provenance="enterprise_catalog",
            source_event_time=lifecycle.valid_from or as_of,
            valid_from=lifecycle.valid_from,
            valid_to=lifecycle.valid_to,
        )
        entries.append(target_entry)

        findings, finding_trunc = self._load_graph_findings(ctx, request, as_of, missing)
        assessment_entry, assessment_risks, readiness_score, assessment_confidence = (
            self._load_assessment(ctx, request, as_of, missing)
        )
        if assessment_risks:
            total_risks = len(assessment_risks)
            truncated_risks = total_risks > MAX_DETERMINISTIC_RISKS
            risks = assessment_risks[:MAX_DETERMINISTIC_RISKS]
            risk_trunc = (truncated_risks, total_risks)
        else:
            # Graph findings may surface as delivery risks only when no assessment
            # risks exist. They never substitute for readiness/assessment confidence.
            risks, risk_trunc = self._risks_from_findings(findings, ctx, missing)
        signals, signal_trunc = self._load_evidence_signals(ctx, request, as_of, missing)
        prediction_summary, pred_entry = self._load_prediction(ctx, request, as_of, missing)
        (
            scenario_runs,
            scenario_results,
            scenario_impacts,
            scen_run_trunc,
            scen_imp_trunc,
            comparability,
        ) = self._load_scenarios(ctx, request, as_of, missing)

        if assessment_entry:
            entries.append(assessment_entry)
        entries.extend(risks)
        entries.extend(findings)
        entries.extend(signals)
        if pred_entry:
            entries.append(pred_entry)
        entries.extend(scenario_runs)
        entries.extend(scenario_results)
        entries.extend(scenario_impacts)

        freshness = self._freshness_summary(signals, as_of)
        freshness_entry = _entry(
            evidence_type=EvidenceEntryType.FRESHNESS_SUMMARY,
            tenant_id=ctx.tenant_id,
            source_type="freshness",
            source_record_id=f"freshness:{request.target_id}",
            summary=(
                f"overall={freshness.overall_state}; stale={freshness.stale_source_count}; "
                f"aging={freshness.aging_source_count}; fresh={freshness.fresh_source_count}"
            ),
            semantic_classification=freshness.overall_state,
            provenance="freshness_policy",
            source_event_time=as_of,
        )
        entries.append(freshness_entry)

        for idx, warning in enumerate(sorted(missing)):
            entries.append(
                _entry(
                    evidence_type=EvidenceEntryType.MISSING_DATA_WARNING,
                    tenant_id=ctx.tenant_id,
                    source_type="missingness",
                    source_record_id=f"missing:{idx}:{request.target_id}",
                    summary=warning,
                    semantic_classification="missing_data",
                    provenance="evidence_assembly",
                    source_event_time=as_of,
                    extra_hash_parts=(warning,),
                )
            )

        truncation = TruncationMetadata(
            risks_truncated=risk_trunc[0],
            risks_total=risk_trunc[1],
            risks_included=len(risks),
            graph_findings_truncated=finding_trunc[0],
            graph_findings_total=finding_trunc[1],
            graph_findings_included=len(findings),
            evidence_signals_truncated=signal_trunc[0],
            evidence_signals_total=signal_trunc[1],
            evidence_signals_included=len(signals),
            scenario_runs_truncated=scen_run_trunc[0],
            scenario_runs_total=scen_run_trunc[1],
            scenario_runs_included=len(scenario_runs),
            scenario_impacts_truncated=scen_imp_trunc[0],
            scenario_impacts_total=scen_imp_trunc[1],
            scenario_impacts_included=len(scenario_impacts),
        )
        if truncation.any_truncated:
            entries.append(
                _entry(
                    evidence_type=EvidenceEntryType.TRUNCATION_METADATA,
                    tenant_id=ctx.tenant_id,
                    source_type="truncation",
                    source_record_id=f"truncation:{request.target_id}",
                    summary=(
                        "Evidence truncated under package bounds; "
                        f"risks={truncation.risks_included}/"
                        f"{truncation.risks_total}, "
                        f"findings={truncation.graph_findings_included}/"
                        f"{truncation.graph_findings_total}, "
                        f"signals={truncation.evidence_signals_included}/"
                        f"{truncation.evidence_signals_total}"
                    ),
                    semantic_classification="truncation",
                    provenance="evidence_assembly",
                    source_event_time=as_of,
                )
            )

        prior_ref, changes = self._prior_and_changes(ctx, request, as_of, entries)
        if prior_ref:
            entries.append(
                _entry(
                    evidence_type=EvidenceEntryType.PRIOR_BRIEF_REFERENCE,
                    tenant_id=ctx.tenant_id,
                    source_type="prior_brief",
                    source_record_id=prior_ref.brief_id,
                    summary=(
                        f"Prior brief {prior_ref.brief_id} as_of={prior_ref.as_of_at.isoformat()} "
                        f"hash={prior_ref.evidence_package_hash[:12]}"
                    ),
                    semantic_classification="prior_brief",
                    provenance="chief_of_staff",
                    source_event_time=prior_ref.as_of_at,
                )
            )
        for change in changes:
            entries.append(
                _entry(
                    evidence_type=EvidenceEntryType.DETERMINISTIC_CHANGE,
                    tenant_id=ctx.tenant_id,
                    source_type="change",
                    source_record_id=change.change_id,
                    summary=change.summary,
                    semantic_classification=change.change_class,
                    provenance="deterministic_diff",
                    source_event_time=as_of,
                    extra_hash_parts=(change.change_class, change.summary),
                )
            )

        package_meta = _entry(
            evidence_type=EvidenceEntryType.PACKAGE_METADATA,
            tenant_id=ctx.tenant_id,
            source_type="package",
            source_record_id=f"package:{request.intent.value}:{request.target_id}",
            summary=(
                f"schema={EVIDENCE_SCHEMA_VERSION}; intent={request.intent.value}; "
                f"as_of={as_of.isoformat()}"
            ),
            semantic_classification="package_metadata",
            provenance="evidence_assembly",
            source_event_time=as_of,
        )
        entries.append(package_meta)

        # Stable evidence ordering: type, event time desc, evidence_id asc.
        entries = order_by_event_then_id(
            order_by_event_then_id(entries, event_attr="source_event_time", id_attr="evidence_id"),
            event_attr="source_event_time",
            id_attr="evidence_id",
        )
        entries = sorted(
            entries,
            key=lambda e: (
                e.evidence_type.value,
                -(e.source_event_time.timestamp() if e.source_event_time else float("-inf")),
                e.evidence_id,
            ),
        )

        package = ChiefOfStaffEvidencePackage(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            tenant_id=ctx.tenant_id,
            target_type=request.target_type,
            target_id=request.target_id,
            target_stable_id=lifecycle.target_id,
            as_of_at=as_of,
            intent=request.intent,
            horizon_days=request.horizon_days,
            target_lifecycle=lifecycle,
            readiness_score=readiness_score,
            assessment_confidence=assessment_confidence,
            assessment_evidence_id=assessment_entry.evidence_id if assessment_entry else None,
            deterministic_risks=risks,
            graph_findings=findings,
            prediction=prediction_summary,
            prediction_evidence_id=pred_entry.evidence_id if pred_entry else None,
            scenario_runs=scenario_runs,
            scenario_impacts=scenario_impacts,
            scenario_comparability=comparability,
            evidence_signals=signals,
            freshness_summary=freshness,
            missing_data_warnings=sorted(missing),
            contradiction_warnings=sorted(contradictions),
            prior_brief=prior_ref,
            deterministic_changes=changes,
            decision_option_candidates=[],
            truncation=truncation,
            evidence_entries=entries,
            package_hash="",
        )
        # Decision options need package evidence_entries present.
        options = compute_decision_options(package)
        option_entries: list[EvidenceEntry] = []
        for opt in options:
            option_entries.append(
                _entry(
                    evidence_type=EvidenceEntryType.DECISION_OPTION_CANDIDATE,
                    tenant_id=ctx.tenant_id,
                    source_type="decision_option",
                    source_record_id=opt.option_type.value,
                    summary=f"{opt.option_type.value}: {opt.rationale}",
                    semantic_classification="advisory_option",
                    provenance=f"decision-options-v1:{opt.option_type.value}",
                    source_event_time=as_of,
                    extra_hash_parts=(str(opt.eligible), opt.rationale),
                )
            )
        all_entries = sorted(
            list(package.evidence_entries) + option_entries,
            key=lambda e: (
                e.evidence_type.value,
                -(e.source_event_time.timestamp() if e.source_event_time else float("-inf")),
                e.evidence_id,
            ),
        )
        package = package.model_copy(
            update={
                "decision_option_candidates": options,
                "evidence_entries": all_entries,
            }
        )
        return attach_package_hash(package)

    def _load_target(
        self,
        ctx: TenantContext,
        target_type: ChiefOfStaffTargetType,
        target_id: str,
        as_of: datetime,
    ) -> TargetLifecycleInfo:
        if target_type == ChiefOfStaffTargetType.PROJECT:
            project = self._uow.initiatives_projects.get_project(ctx, target_id)
            if project is None:
                raise EnterpriseNotFoundError(_NOT_FOUND)
            if project.archived_at is not None and _utc(project.archived_at) <= as_of:
                raise EnterpriseNotFoundError(_NOT_FOUND)
            return TargetLifecycleInfo(
                target_type=target_type,
                target_id=project.enterprise_project_id,
                display_name=normalize_untrusted_text(project.name, 200),
                lifecycle_state=str(
                    project.status.value if hasattr(project.status, "value") else project.status
                ),
                valid_from=project.planned_start,
                valid_to=project.planned_target,
                archived_at=project.archived_at,
                criticality=str(
                    project.criticality.value
                    if hasattr(project.criticality, "value")
                    else project.criticality
                ),
            )
        initiative = self._uow.initiatives_projects.get_initiative(ctx, target_id)
        if initiative is None:
            raise EnterpriseNotFoundError(_NOT_FOUND)
        if initiative.archived_at is not None and _utc(initiative.archived_at) <= as_of:
            raise EnterpriseNotFoundError(_NOT_FOUND)
        return TargetLifecycleInfo(
            target_type=target_type,
            target_id=initiative.initiative_id,
            display_name=normalize_untrusted_text(initiative.name, 200),
            lifecycle_state=str(
                initiative.status.value
                if hasattr(initiative.status, "value")
                else initiative.status
            ),
            valid_from=initiative.planned_start,
            valid_to=initiative.planned_target,
            archived_at=initiative.archived_at,
            criticality=str(
                initiative.criticality.value
                if hasattr(initiative.criticality, "value")
                else initiative.criticality
            ),
        )

    def _load_assessment(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
        as_of: datetime,
        missing: list[str],
    ) -> tuple[EvidenceEntry | None, list[EvidenceEntry], float | None, float | None]:
        """Load cutoff-scoped Phase 2 assessment when a legacy project link exists.

        Never recalculates readiness or confidence. Includes immutable assessment
        evidence when present; otherwise records explicit unavailability.
        """
        from sqlalchemy import select

        from app.db.models.assessment import Assessment, AssessmentRiskFinding

        if request.target_type != ChiefOfStaffTargetType.PROJECT:
            missing.append("Readiness assessment unavailable for initiative targets")
            return None, [], None, None

        project = self._uow.initiatives_projects.get_project(ctx, request.target_id)
        if project is None or not project.legacy_project_id:
            missing.append("No readiness assessment available at cutoff")
            return None, [], None, None

        legacy_id = project.legacy_project_id.strip().lower()
        row = self._uow.session.scalar(
            select(Assessment)
            .where(
                Assessment.project_id == legacy_id,
                Assessment.created_at <= as_of,
            )
            .order_by(
                Assessment.created_at.desc(),
                Assessment.assessment_record_id.desc(),
            )
            .limit(1)
        )
        if row is None:
            missing.append("No readiness assessment available at cutoff")
            return None, [], None, None

        record_id = str(row.assessment_record_id)
        assessment_entry = _entry(
            evidence_type=EvidenceEntryType.READINESS_ASSESSMENT,
            tenant_id=ctx.tenant_id,
            source_type="assessment",
            source_record_id=record_id,
            summary=(
                f"readiness={row.readiness_score}; assessment_confidence={row.confidence_score}; "
                f"confidence_level={row.confidence_level}; policy={row.policy_version}"
            ),
            semantic_classification="readiness_assessment",
            provenance=f"assessment_hash:{row.result_snapshot_hash[:16]}",
            source_event_time=row.created_at,
            observed_at=row.created_at,
        )
        risk_rows = list(
            self._uow.session.scalars(
                select(AssessmentRiskFinding).where(
                    AssessmentRiskFinding.assessment_record_id == row.assessment_record_id
                )
            ).all()
        )
        risk_rows.sort(
            key=lambda r: (
                severity_rank(str(r.severity)),
                r.finding_type,
                str(r.id),
            )
        )
        risk_entries = [
            _entry(
                evidence_type=EvidenceEntryType.ASSESSMENT_RISK,
                tenant_id=ctx.tenant_id,
                source_type="assessment_risk",
                source_record_id=f"{record_id}:{risk.id}",
                summary=f"{risk.severity}: {risk.message}",
                semantic_classification=risk.finding_type,
                provenance=f"assessment:{record_id}",
                source_event_time=row.created_at,
                extra_hash_parts=(str(risk.severity), risk.finding_type),
            )
            for risk in risk_rows
        ]
        return (
            assessment_entry,
            risk_entries,
            float(row.readiness_score),
            float(row.confidence_score),
        )

    def _load_graph_findings(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
        as_of: datetime,
        missing: list[str],
    ) -> tuple[list[EvidenceEntry], tuple[bool, int]]:
        page = self._uow.graph_findings.list_findings(
            ctx, active_at=as_of, status=None, limit=100, offset=0
        )
        # Filter to findings whose primary/affected nodes relate to target.
        # Fail closed when no target nodes are found — never include unrelated findings.
        target_nodes = self._uow.graph_nodes.list_nodes(ctx, active_at=as_of, limit=200, offset=0)
        related_node_ids = {
            n.graph_node_id
            for n in target_nodes.items
            if getattr(n, "entity_id", None) == request.target_id
            or getattr(n, "stable_entity_id", None) == request.target_id
        }
        if not related_node_ids:
            missing.append("No graph nodes for target at cutoff; graph findings omitted")
            return [], (False, 0)

        # One-hop expansion via edges so work-item/team findings tied to the
        # target project/initiative are included without tenant-wide leakage.
        expanded = set(related_node_ids)
        edges = self._uow.graph_edges.list_edges(ctx, active_at=as_of, limit=500, offset=0)
        for edge in edges.items:
            if edge.source_node_id in related_node_ids:
                expanded.add(edge.target_node_id)
            if edge.target_node_id in related_node_ids:
                expanded.add(edge.source_node_id)
        related_node_ids = expanded

        selected = []
        for finding in page.items:
            affected = set(finding.affected_node_ids or [])
            affected.add(finding.primary_node_id)
            if affected.isdisjoint(related_node_ids):
                continue
            selected.append(finding)

        selected.sort(
            key=lambda f: (
                severity_rank(
                    str(f.severity.value if hasattr(f.severity, "value") else f.severity)
                ),
                -(f.detected_at.timestamp() if f.detected_at else float("-inf")),
                f.graph_finding_id,
            )
        )
        total = len(selected)
        truncated = total > MAX_GRAPH_FINDINGS
        selected = selected[:MAX_GRAPH_FINDINGS]
        entries = [
            _entry(
                evidence_type=EvidenceEntryType.GRAPH_FINDING,
                tenant_id=ctx.tenant_id,
                source_type="graph_finding",
                source_record_id=f.graph_finding_id,
                summary=f"{f.title}: {f.explanation}",
                semantic_classification=str(
                    f.finding_type.value if hasattr(f.finding_type, "value") else f.finding_type
                ),
                provenance=f"graph_rule:{f.rule_id}:{f.rule_version}",
                source_event_time=f.detected_at,
                observed_at=f.last_observed_at,
                valid_from=f.detected_at,
                valid_to=f.resolved_at,
            )
            for f in selected
        ]
        return entries, (truncated, total)

    def _risks_from_findings(
        self,
        findings: list[EvidenceEntry],
        ctx: TenantContext,
        missing: list[str],
    ) -> tuple[list[EvidenceEntry], tuple[bool, int]]:
        risks = []
        for finding_entry in findings:
            risks.append(
                finding_entry.model_copy(
                    update={
                        "evidence_type": EvidenceEntryType.ASSESSMENT_RISK,
                        "evidence_id": build_evidence_id(
                            EvidenceEntryType.ASSESSMENT_RISK,
                            ctx.tenant_id,
                            finding_entry.source_record_id,
                            "risk_view",
                        ),
                        "semantic_classification": "deterministic_risk",
                    }
                )
            )
        if not risks:
            missing.append("No deterministic risk findings available at cutoff")
        total = len(risks)
        truncated = total > MAX_DETERMINISTIC_RISKS
        risks = risks[:MAX_DETERMINISTIC_RISKS]
        return risks, (truncated, total)

    def _load_risks_from_graph_and_signals(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
        as_of: datetime,
        missing: list[str],
    ) -> tuple[list[EvidenceEntry], tuple[bool, int]]:
        findings, _ = self._load_graph_findings(ctx, request, as_of, missing)
        return self._risks_from_findings(findings, ctx, missing)

    def _load_evidence_signals(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
        as_of: datetime,
        missing: list[str],
    ) -> tuple[list[EvidenceEntry], tuple[bool, int]]:
        subject_type = (
            EnterpriseEntityType.PROJECT
            if request.target_type == ChiefOfStaffTargetType.PROJECT
            else EnterpriseEntityType.INITIATIVE
        )
        # Fetch enough rows to allow temporal filtering; order is reapplied after cutoff.
        page = self._uow.evidence_signals.list_by_subject(
            ctx, subject_type, request.target_id, limit=200, offset=0
        )
        eligible = [
            s
            for s in page.items
            if _utc(s.event_time) <= as_of and (s.expires_at is None or _utc(s.expires_at) > as_of)
        ]
        eligible.sort(
            key=lambda s: (
                -(s.event_time.timestamp() if s.event_time else float("-inf")),
                s.evidence_signal_id,
            )
        )
        total = len(eligible)
        truncated = total > MAX_EVIDENCE_SIGNALS
        if truncated:
            missing.append(
                f"Evidence signals truncated to {MAX_EVIDENCE_SIGNALS} of {total} at cutoff"
            )
        eligible = eligible[:MAX_EVIDENCE_SIGNALS]
        entries = [
            _entry(
                evidence_type=EvidenceEntryType.EVIDENCE_SIGNAL,
                tenant_id=ctx.tenant_id,
                source_type=str(
                    s.signal_type.value if hasattr(s.signal_type, "value") else s.signal_type
                ),
                source_record_id=s.evidence_signal_id,
                summary=f"signal={s.signal_type} source_record={s.source_record_id}",
                semantic_classification="evidence_signal",
                provenance=f"data_source:{s.data_source_id}",
                source_event_time=s.event_time,
                observed_at=s.observed_at,
                ingested_at=s.ingested_at,
            )
            for s in eligible
        ]
        return entries, (truncated, total)

    def _load_prediction(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
        as_of: datetime,
        missing: list[str],
    ) -> tuple[PredictionProvenanceSummary | None, EvidenceEntry | None]:
        page = self._uow.delivery_predictions.list_for_target(
            ctx,
            request.target_type.value,
            request.target_id,
            limit=50,
            offset=0,
        )
        candidates = [
            p
            for p in page.items
            if _utc(p.as_of_at) <= as_of
            and (request.horizon_days is None or p.horizon_days == request.horizon_days)
        ]
        candidates.sort(
            key=lambda p: (
                -(p.as_of_at.timestamp()),
                p.delivery_prediction_id,
            )
        )
        if not candidates:
            if request.intent == ChiefOfStaffIntent.DELIVERY_PREDICTION_BRIEF:
                missing.append("No delivery prediction available at cutoff for requested horizon")
            return None, None
        pred = candidates[0]
        model_state = None
        model_promoted = False
        if pred.model_id:
            model = self._uow.prediction_models.get(ctx, pred.model_id)
            if model is not None:
                model_state = str(
                    model.state.value if hasattr(model.state, "value") else model.state
                )
                model_promoted = model_state == "active"

        notes = []
        if pred.estimate_kind == EstimateKind.UNCALIBRATED_SCORE:
            notes.append("estimate_kind=uncalibrated_score; probability unavailable")
            notes.append("score is not a calibrated probability")
        if not model_promoted:
            notes.append("model was not promoted to active for this estimate")
        if str(getattr(pred.data_scope, "value", pred.data_scope)) in {"synthetic", "demo"}:
            notes.append("synthetic/demo scoped data")

        probability_value = (
            None
            if pred.estimate_kind == EstimateKind.UNCALIBRATED_SCORE
            else pred.probability_of_delivery_success
        )
        summary = PredictionProvenanceSummary(
            prediction_id=pred.delivery_prediction_id,
            estimate_kind=pred.estimate_kind,
            probability=probability_value,
            uncalibrated_score=pred.uncalibrated_risk_score,
            model_id=pred.model_id,
            model_state=model_state,
            model_was_promoted=model_promoted,
            horizon_days=pred.horizon_days,
            as_of_at=pred.as_of_at,
            notes=notes,
        )
        entry = _entry(
            evidence_type=EvidenceEntryType.DELIVERY_PREDICTION,
            tenant_id=ctx.tenant_id,
            source_type="delivery_prediction",
            source_record_id=pred.delivery_prediction_id,
            summary=(
                f"estimate_kind={pred.estimate_kind.value}; "
                f"score={pred.uncalibrated_risk_score}; "
                f"probability={probability_value}; "
                f"horizon={pred.horizon_days}; model_state={model_state}"
            ),
            semantic_classification=pred.estimate_kind.value,
            provenance=f"prediction_hash:{pred.prediction_hash[:16]}",
            source_event_time=pred.as_of_at,
        )
        return summary, entry

    def _load_scenarios(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
        as_of: datetime,
        missing: list[str],
    ) -> tuple[
        list[EvidenceEntry],
        list[EvidenceEntry],
        list[EvidenceEntry],
        tuple[bool, int],
        tuple[bool, int],
        ScenarioComparability | None,
    ]:
        runs = []
        if request.scenario_run_ids:
            for run_id in request.scenario_run_ids:
                run = self._uow.scenario_runs.get(ctx, run_id)
                if run is None:
                    raise EnterpriseNotFoundError(_NOT_FOUND)
                if (
                    run.target_id != request.target_id
                    or run.target_type != request.target_type.value
                ):
                    raise EnterpriseNotFoundError(_NOT_FOUND)
                if _utc(run.as_of_at) > as_of:
                    raise EnterpriseValidationError("Scenario run as_of_at is after request cutoff")
                if str(getattr(run.state, "value", run.state)) not in {
                    "succeeded",
                    "partial",
                    "skipped_no_change",
                }:
                    missing.append("Scenario run not completed at cutoff")
                    continue
                runs.append(run)
        elif request.intent != ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF:
            page = self._uow.scenario_runs.list_for_target(
                ctx,
                request.target_type.value,
                request.target_id,
                limit=20,
                offset=0,
            )
            runs = [
                r
                for r in page.items
                if _utc(r.as_of_at) <= as_of
                and str(getattr(r.state, "value", r.state))
                in {"succeeded", "partial", "skipped_no_change"}
            ]

        runs.sort(key=lambda r: (-r.as_of_at.timestamp(), r.scenario_run_id))
        total_runs = len(runs)
        trunc_runs = total_runs > MAX_SCENARIO_RUNS
        runs = runs[:MAX_SCENARIO_RUNS]

        run_entries = [
            _entry(
                evidence_type=EvidenceEntryType.SCENARIO_RUN,
                tenant_id=ctx.tenant_id,
                source_type="scenario_run",
                source_record_id=r.scenario_run_id,
                summary=(
                    f"scenario_run={r.scenario_run_id}; horizon={r.horizon_days}; state={r.state}"
                ),
                semantic_classification="scenario_run",
                provenance=f"run_input_hash:{(r.run_input_hash or '')[:16]}",
                source_event_time=r.as_of_at,
            )
            for r in runs
        ]

        impact_entries: list[EvidenceEntry] = []
        result_entries: list[EvidenceEntry] = []
        estimate_kinds: list[str] = []
        for r in runs:
            result = self._uow.scenario_results.get_by_run(ctx, r.scenario_run_id)
            if result is not None:
                for kind_attr in ("baseline_estimate_kind", "simulated_estimate_kind"):
                    kind = getattr(result, kind_attr, None)
                    if kind is not None:
                        estimate_kinds.append(str(getattr(kind, "value", kind)))
                result_entries.append(
                    _entry(
                        evidence_type=EvidenceEntryType.SCENARIO_RESULT,
                        tenant_id=ctx.tenant_id,
                        source_type="scenario_result",
                        source_record_id=result.scenario_result_id,
                        summary=(
                            f"baseline_kind={getattr(result, 'baseline_estimate_kind', None)}; "
                            f"simulated_kind={getattr(result, 'simulated_estimate_kind', None)}"
                        ),
                        semantic_classification="scenario_result",
                        provenance=f"scenario_run:{r.scenario_run_id}",
                        source_event_time=r.as_of_at,
                    )
                )
            impacts_page = self._uow.scenario_impacts.list_for_run(
                ctx, r.scenario_run_id, limit=100, offset=0
            )
            for impact in impacts_page.items:
                impact_entries.append(
                    _entry(
                        evidence_type=EvidenceEntryType.SCENARIO_IMPACT,
                        tenant_id=ctx.tenant_id,
                        source_type="scenario_impact",
                        source_record_id=impact.scenario_impact_id,
                        summary=normalize_untrusted_text(
                            str(getattr(impact, "explanation", None) or impact.scenario_impact_id),
                            MAX_EVIDENCE_SUMMARY_CHARS,
                        ),
                        semantic_classification=str(
                            getattr(getattr(impact, "impact_type", None), "value", "impact")
                        ),
                        provenance=f"scenario_run:{r.scenario_run_id}",
                        source_event_time=r.as_of_at,
                    )
                )

        impact_entries.sort(key=lambda e: e.evidence_id)
        total_impacts = len(impact_entries)
        trunc_impacts = total_impacts > MAX_SCENARIO_IMPACTS
        impact_entries = impact_entries[:MAX_SCENARIO_IMPACTS]

        comparability = None
        if request.intent == ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF:
            unique_kinds = sorted(set(estimate_kinds))
            comparable = len(unique_kinds) <= 1 and len(runs) >= 2
            reason = (
                "Comparable scenario runs share estimate kind"
                if comparable
                else "Scenario estimate kinds differ or insufficient completed runs"
            )
            if len(unique_kinds) > 1:
                reason = "Incomparable estimate kinds; numeric estimate delta forbidden"
                comparable = False
            comparability = ScenarioComparability(
                comparable=comparable,
                reason=reason,
                estimate_kinds=unique_kinds,
                shared_horizon_days=runs[0].horizon_days if runs else None,
            )
            if not runs:
                missing.append("No completed scenario runs available for comparison")

        return (
            run_entries,
            result_entries,
            impact_entries,
            (trunc_runs, total_runs),
            (trunc_impacts, total_impacts),
            comparability,
        )

    def _freshness_summary(self, signals: list[EvidenceEntry], as_of: datetime) -> FreshnessSummary:
        if not signals:
            return FreshnessSummary(overall_state="never_synced", notes=["No evidence signals"])
        times = [s.source_event_time for s in signals if s.source_event_time]
        oldest = min(times) if times else None
        newest = max(times) if times else None
        stale = 0
        aging = 0
        fresh = 0
        for s in signals:
            if s.source_event_time is None:
                continue
            age_days = (as_of - _utc(s.source_event_time)).total_seconds() / 86400.0
            if age_days > 30:
                stale += 1
            elif age_days > 7:
                aging += 1
            else:
                fresh += 1
        overall = "fresh"
        if stale:
            overall = "stale"
        elif aging:
            overall = "aging"
        return FreshnessSummary(
            overall_state=overall,
            oldest_event_time=oldest,
            newest_event_time=newest,
            stale_source_count=stale,
            aging_source_count=aging,
            fresh_source_count=fresh,
        )

    def _prior_and_changes(
        self,
        ctx: TenantContext,
        request: ChiefOfStaffRequest,
        as_of: datetime,
        current_entries: list[EvidenceEntry],
    ) -> tuple[PriorBriefReference | None, list[DeterministicChangeRecord]]:
        if not request.prior_brief_id:
            return None, []
        brief = self._uow.cos_briefs.get(ctx, request.prior_brief_id)
        if brief is None:
            raise EnterpriseNotFoundError(_NOT_FOUND)
        prior_target_type = (
            brief.target_type.value
            if hasattr(brief.target_type, "value")
            else str(brief.target_type)
        )
        if prior_target_type != request.target_type.value or brief.target_id != request.target_id:
            # Same-tenant wrong-target prior is externally equivalent to missing.
            raise EnterpriseNotFoundError(_NOT_FOUND)
        if _utc(brief.as_of_at) >= as_of:
            raise EnterpriseValidationError(
                "prior brief as_of_at must be earlier than request cutoff"
            )
        snapshot = self._uow.cos_evidence_snapshots.require(ctx, brief.evidence_snapshot_id)
        prior_package = ChiefOfStaffEvidencePackage.model_validate(snapshot.package_json)
        prior_ref = PriorBriefReference(
            brief_id=brief.brief_id,
            run_id=brief.run_id,
            as_of_at=brief.as_of_at,
            evidence_package_hash=snapshot.package_hash,
            output_hash=brief.output_hash,
            intent=brief.intent,
        )
        prior_ids = {e.evidence_id for e in prior_package.evidence_entries}
        current_ids = {e.evidence_id for e in current_entries}
        prior_by_id = {e.evidence_id: e for e in prior_package.evidence_entries}
        current_by_id = {e.evidence_id: e for e in current_entries}
        changes: list[DeterministicChangeRecord] = []
        for eid in sorted(current_ids - prior_ids):
            entry = current_by_id[eid]
            changes.append(
                DeterministicChangeRecord(
                    change_id=f"add:{eid}",
                    change_class="addition",
                    evidence_type=entry.evidence_type,
                    current_evidence_id=eid,
                    prior_evidence_id=None,
                    summary=f"Added evidence {entry.evidence_type.value}",
                )
            )
        for eid in sorted(prior_ids - current_ids):
            entry = prior_by_id[eid]
            changes.append(
                DeterministicChangeRecord(
                    change_id=f"rem:{eid}",
                    change_class="removal",
                    evidence_type=entry.evidence_type,
                    current_evidence_id=None,
                    prior_evidence_id=eid,
                    summary=f"Removed evidence {entry.evidence_type.value}",
                )
            )
        for eid in sorted(current_ids & prior_ids):
            cur = current_by_id[eid]
            prev = prior_by_id[eid]
            if cur.payload_hash != prev.payload_hash:
                changes.append(
                    DeterministicChangeRecord(
                        change_id=f"chg:{eid}",
                        change_class="material_change",
                        evidence_type=cur.evidence_type,
                        current_evidence_id=eid,
                        prior_evidence_id=eid,
                        summary=f"Material change in {cur.evidence_type.value}",
                    )
                )
        changes.sort(key=lambda c: c.change_id)
        return prior_ref, changes[:50]
