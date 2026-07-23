"""Canonical evidence package construction from persisted assessment snapshots."""

from __future__ import annotations

from uuid import UUID

from app.domain.leadership_brief_models import (
    EvidenceRiskFinding,
    EvidenceTraceEntry,
    LeadershipBriefEvidencePackage,
)
from app.schemas.api_v2 import ReadinessAssessResponse
from app.services.leadership_brief.evidence_ids import (
    build_risk_evidence_id,
    build_trace_evidence_id,
)
from app.services.persistence.snapshot_service import canonical_json, snapshot_hash


def build_evidence_package(
    *,
    assessment_record_id: UUID,
    result: ReadinessAssessResponse,
    latest_review_state: str | None = None,
) -> LeadershipBriefEvidencePackage:
    risk_findings = sorted(
        [
            EvidenceRiskFinding(
                evidence_id=build_risk_evidence_id(finding),
                finding_type=finding.finding_type.value,
                severity=finding.severity.value,
                capability_id=finding.capability_id,
                engineer_id=finding.engineer_id,
                message=finding.message,
            )
            for finding in result.risk_findings
        ],
        key=lambda item: item.evidence_id,
    )
    decision_trace = [
        EvidenceTraceEntry(
            evidence_id=build_trace_evidence_id(entry),
            step=entry.step,
            component=entry.component,
            label=entry.label,
            value=entry.value,
            contribution=entry.contribution,
            policy_version=entry.policy_version,
        )
        for entry in result.decision_trace
    ]
    team_member_ids = sorted({engineer.id for engineer in result.team})
    return LeadershipBriefEvidencePackage(
        assessment_record_id=str(assessment_record_id),
        assessment_id=result.assessment_id,
        project_id=result.project_id,
        project_name=result.project_name,
        team_member_ids=team_member_ids,
        readiness_score=result.readiness_score,
        confidence_score=result.confidence_score,
        confidence_level=result.confidence_level.value,
        policy_version=result.policy_version,
        dimension_scores=[
            item.model_dump(mode="json") for item in result.dimension_scores
        ],
        skill_gaps=[item.model_dump(mode="json") for item in result.skill_gaps],
        capability_coverage=[
            item.model_dump(mode="json") for item in result.coverage_results
        ],
        risk_findings=risk_findings,
        decision_trace=decision_trace,
        deterministic_summary=result.summary,
        latest_review_state=latest_review_state,
    )


def evidence_package_to_canonical_dict(package: LeadershipBriefEvidencePackage) -> dict:
    return package.model_dump(mode="json")


def evidence_package_hash(package: LeadershipBriefEvidencePackage) -> str:
    return snapshot_hash(evidence_package_to_canonical_dict(package))


def canonical_evidence_json(package: LeadershipBriefEvidencePackage) -> str:
    return canonical_json(evidence_package_to_canonical_dict(package))
