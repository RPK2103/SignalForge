"""Deterministic mitigation recommendations derived from simulation deltas."""

import hashlib
import json

from app.domain.enums import (
    CoverageLevel,
    MitigationPriority,
    MitigationType,
    RiskFindingType,
    SimulationChangeType,
    SimulationOperationType,
)
from app.domain.simulation_models import (
    CapabilityCoverageChange,
    DeterministicMitigation,
    KeyPersonDependencyChange,
    RiskFindingChange,
    SimulationOperation,
    SimulationResult,
)


class MitigationService:
    def recommend(self, result: SimulationResult) -> list[DeterministicMitigation]:
        mitigations: list[DeterministicMitigation] = []
        mitigations.extend(self._from_introduced_gaps(result))
        mitigations.extend(self._from_coverage_changes(result))
        mitigations.extend(self._from_key_person_changes(result))
        mitigations.extend(self._from_risk_changes(result))
        mitigations.extend(self._from_confidence_decline(result))
        mitigations.extend(self._from_remove_operation(result))

        deduped = self._deduplicate(mitigations)
        return sorted(deduped, key=lambda item: (item.priority.value, item.mitigation_id))

    def _from_introduced_gaps(self, result: SimulationResult) -> list[DeterministicMitigation]:
        items: list[DeterministicMitigation] = []
        for gap in result.newly_introduced_gaps:
            priority = (
                MitigationPriority.CRITICAL if gap.is_critical else MitigationPriority.HIGH
            )
            mitigation_type = (
                MitigationType.ADD_CAPABILITY_COVERAGE
                if gap.level == CoverageLevel.MISSING
                else MitigationType.STRENGTHEN_CAPABILITY_COVERAGE
            )
            items.append(
                self._build(
                    mitigation_type=mitigation_type,
                    priority=priority,
                    title=f"Address {gap.capability_name} gap",
                    action=(
                        f"Add or strengthen team coverage for {gap.capability_name} "
                        f"({gap.level.value})."
                    ),
                    rationale=(
                        f"Simulation introduced a {gap.level.value} gap for capability "
                        f"'{gap.capability_name}'."
                    ),
                    capability_id=gap.capability_id,
                    evidence_references=[f"skill_gap:{gap.capability_id}:{gap.level.value}"],
                    policy_version=result.policy_version,
                    project_id=result.project_id,
                    operation=result.operation,
                )
            )
        return items

    def _from_coverage_changes(
        self, result: SimulationResult
    ) -> list[DeterministicMitigation]:
        items: list[DeterministicMitigation] = []
        for change in result.capability_coverage_changes:
            if change.change_type not in {
                SimulationChangeType.DEGRADED,
                SimulationChangeType.MODIFIED,
            }:
                continue
            if change.proposed_level == CoverageLevel.MISSING and change.is_critical:
                items.append(
                    self._build(
                        mitigation_type=MitigationType.ADD_CAPABILITY_COVERAGE,
                        priority=MitigationPriority.CRITICAL,
                        title=f"Restore critical coverage for {change.capability_name}",
                        action=(
                            f"Restore sufficient coverage for critical capability "
                            f"{change.capability_name}."
                        ),
                        rationale=(
                            f"Coverage for '{change.capability_name}' degraded from "
                            f"{change.baseline_level.value} to {change.proposed_level.value}."
                        ),
                        capability_id=change.capability_id,
                        affected_engineer_ids=change.affected_engineer_ids,
                        evidence_references=[
                            f"coverage_change:{change.capability_id}:{change.change_type.value}"
                        ],
                        policy_version=result.policy_version,
                        project_id=result.project_id,
                        operation=result.operation,
                    )
                )
            elif change.proposed_level == CoverageLevel.WEAK:
                items.append(
                    self._build(
                        mitigation_type=MitigationType.STRENGTHEN_CAPABILITY_COVERAGE,
                        priority=MitigationPriority.MEDIUM,
                        title=f"Strengthen {change.capability_name} coverage",
                        action=f"Increase proficiency depth for {change.capability_name}.",
                        rationale=(
                            f"Capability '{change.capability_name}' weakened during simulation."
                        ),
                        capability_id=change.capability_id,
                        affected_engineer_ids=change.affected_engineer_ids,
                        evidence_references=[
                            f"coverage_change:{change.capability_id}:{change.change_type.value}"
                        ],
                        policy_version=result.policy_version,
                        project_id=result.project_id,
                        operation=result.operation,
                    )
                )
        return items

    def _from_key_person_changes(
        self, result: SimulationResult
    ) -> list[DeterministicMitigation]:
        items: list[DeterministicMitigation] = []
        for change in result.key_person_dependency_changes:
            if change.change_type != SimulationChangeType.INTRODUCED:
                continue
            priority = (
                MitigationPriority.CRITICAL if change.is_critical else MitigationPriority.HIGH
            )
            items.append(
                self._build(
                    mitigation_type=MitigationType.ESTABLISH_SECONDARY_OWNER,
                    priority=priority,
                    title=f"Establish secondary owner for {change.capability_name}",
                    action=(
                        f"Add a secondary engineer covering {change.capability_name} "
                        f"to reduce key-person dependency."
                    ),
                    rationale=(
                        f"Simulation created a single-engineer dependency on "
                        f"'{change.capability_name}'."
                    ),
                    capability_id=change.capability_id,
                    affected_engineer_ids=change.proposed_covering_engineer_ids,
                    evidence_references=[
                        f"key_person:{change.capability_id}:{change.change_type.value}"
                    ],
                    policy_version=result.policy_version,
                    project_id=result.project_id,
                    operation=result.operation,
                )
            )
        return items

    def _from_risk_changes(self, result: SimulationResult) -> list[DeterministicMitigation]:
        items: list[DeterministicMitigation] = []
        for change in result.risk_level_changes:
            if change.change_type not in {
                SimulationChangeType.INTRODUCED,
                SimulationChangeType.ESCALATED,
            }:
                continue
            if change.finding_type == RiskFindingType.INCOMPLETE_EVIDENCE:
                items.append(
                    self._build(
                        mitigation_type=MitigationType.IMPROVE_ENGINEER_EVIDENCE,
                        priority=MitigationPriority.MEDIUM,
                        title="Improve engineer evidence quality",
                        action="Collect certifications and project history for affected engineers.",
                        rationale=change.message,
                        capability_id=change.capability_id,
                        affected_engineer_ids=[change.engineer_id]
                        if change.engineer_id
                        else [],
                        evidence_references=[
                            f"risk:{change.finding_type.value}:{change.engineer_id or 'team'}"
                        ],
                        policy_version=result.policy_version,
                        project_id=result.project_id,
                        operation=result.operation,
                    )
                )
            elif change.finding_type == RiskFindingType.KEY_PERSON_DEPENDENCY:
                items.append(
                    self._build(
                        mitigation_type=MitigationType.ESTABLISH_SECONDARY_OWNER,
                        priority=MitigationPriority.HIGH,
                        title="Reduce key-person dependency risk",
                        action="Assign a backup engineer for the affected capability.",
                        rationale=change.message,
                        capability_id=change.capability_id,
                        affected_engineer_ids=[change.engineer_id]
                        if change.engineer_id
                        else [],
                        evidence_references=[
                            f"risk:{change.finding_type.value}:{change.capability_id or 'general'}"
                        ],
                        policy_version=result.policy_version,
                        project_id=result.project_id,
                        operation=result.operation,
                    )
                )
        return items

    def _from_confidence_decline(
        self, result: SimulationResult
    ) -> list[DeterministicMitigation]:
        if result.confidence_delta >= 0:
            return []
        return [
            self._build(
                mitigation_type=MitigationType.IMPROVE_ENGINEER_EVIDENCE,
                priority=MitigationPriority.MEDIUM,
                title="Address confidence decline",
                action="Improve evidence quality across the proposed team.",
                rationale=(
                    f"Simulation reduced confidence score by {abs(result.confidence_delta)} points."
                ),
                evidence_references=["confidence_delta"],
                policy_version=result.policy_version,
                project_id=result.project_id,
                operation=result.operation,
            )
        ]

    def _from_remove_operation(self, result: SimulationResult) -> list[DeterministicMitigation]:
        if result.operation.type != SimulationOperationType.REMOVE:
            return []
        if result.readiness_score_delta >= 0:
            return []

        critical_gaps = [gap for gap in result.newly_introduced_gaps if gap.is_critical]
        if not critical_gaps:
            return []

        gap = critical_gaps[0]
        return [
            self._build(
                mitigation_type=MitigationType.PRESERVE_CRITICAL_ENGINEER,
                priority=MitigationPriority.CRITICAL,
                title=f"Preserve engineer covering {gap.capability_name}",
                action=(
                    "Retain the removed engineer or replace them with equivalent "
                    f"coverage for {gap.capability_name}."
                ),
                rationale=(
                    f"Removing an engineer introduced a critical gap in {gap.capability_name}."
                ),
                capability_id=gap.capability_id,
                evidence_references=[f"remove_gap:{gap.capability_id}"],
                policy_version=result.policy_version,
                project_id=result.project_id,
                operation=result.operation,
            )
        ]

    def _build(
        self,
        *,
        mitigation_type: MitigationType,
        priority: MitigationPriority,
        title: str,
        action: str,
        rationale: str,
        policy_version: str,
        project_id: str,
        operation: SimulationOperation,
        capability_id: str | None = None,
        affected_engineer_ids: list[str] | None = None,
        evidence_references: list[str] | None = None,
    ) -> DeterministicMitigation:
        engineer_ids = sorted(affected_engineer_ids or [])
        mitigation_id = self._mitigation_id(
            mitigation_type=mitigation_type,
            project_id=project_id,
            operation=operation,
            capability_id=capability_id,
            engineer_ids=engineer_ids,
            evidence_references=evidence_references or [],
            policy_version=policy_version,
        )
        return DeterministicMitigation(
            mitigation_id=mitigation_id,
            mitigation_type=mitigation_type,
            priority=priority,
            title=title,
            action=action,
            rationale=rationale,
            capability_id=capability_id,
            affected_engineer_ids=engineer_ids,
            evidence_references=sorted(evidence_references or []),
            policy_version=policy_version,
        )

    def _mitigation_id(
        self,
        *,
        mitigation_type: MitigationType,
        project_id: str,
        operation: SimulationOperation,
        capability_id: str | None,
        engineer_ids: list[str],
        evidence_references: list[str],
        policy_version: str,
    ) -> str:
        canonical = {
            "mitigation_type": mitigation_type.value,
            "project_id": project_id.strip().lower(),
            "operation": operation.model_dump(mode="json"),
            "capability_id": capability_id,
            "engineer_ids": engineer_ids,
            "evidence_references": sorted(evidence_references),
            "policy_version": policy_version,
        }
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def _deduplicate(
        self, mitigations: list[DeterministicMitigation]
    ) -> list[DeterministicMitigation]:
        seen: set[str] = set()
        unique: list[DeterministicMitigation] = []
        for mitigation in mitigations:
            if mitigation.mitigation_id in seen:
                continue
            seen.add(mitigation.mitigation_id)
            unique.append(mitigation)
        return unique
