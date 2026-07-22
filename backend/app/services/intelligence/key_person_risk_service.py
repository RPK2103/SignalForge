"""Detects single-person capability dependencies and related risks."""

from app.domain.enums import CoverageLevel, RiskFindingType, RiskSeverity
from app.domain.models import CoverageResult, EngineerProfile, RiskFinding, TeamComposition


class KeyPersonRiskService:
    def analyze(
        self,
        coverage_results: list[CoverageResult],
        team: TeamComposition,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []

        if not team.engineers:
            findings.append(
                RiskFinding(
                    finding_type=RiskFindingType.EMPTY_TEAM,
                    severity=RiskSeverity.HIGH,
                    message="Team composition is empty; no capability coverage possible.",
                )
            )
            return findings

        for result in coverage_results:
            if result.level == CoverageLevel.MISSING and result.is_critical:
                findings.append(
                    RiskFinding(
                        finding_type=RiskFindingType.MISSING_CRITICAL_CAPABILITY,
                        severity=RiskSeverity.HIGH,
                        capability_id=result.capability_id,
                        message=(
                            f"Critical capability '{result.capability_name}' has no team coverage."
                        ),
                    )
                )
            elif result.level == CoverageLevel.WEAK and result.is_critical:
                findings.append(
                    RiskFinding(
                        finding_type=RiskFindingType.WEAK_CAPABILITY,
                        severity=RiskSeverity.MEDIUM,
                        capability_id=result.capability_id,
                        message=(
                            f"Critical capability '{result.capability_name}' is weakly covered "
                            f"(proficiency {result.team_proficiency}/100)."
                        ),
                    )
                )
            elif len(result.covering_engineer_ids) == 1 and result.level != CoverageLevel.MISSING:
                engineer_id = result.covering_engineer_ids[0]
                engineer_name = self._engineer_name(team.engineers, engineer_id)
                severity = RiskSeverity.HIGH if result.is_critical else RiskSeverity.MEDIUM
                findings.append(
                    RiskFinding(
                        finding_type=RiskFindingType.KEY_PERSON_DEPENDENCY,
                        severity=severity,
                        capability_id=result.capability_id,
                        engineer_id=engineer_id,
                        message=(
                            f"Capability '{result.capability_name}' depends on a single engineer "
                            f"({engineer_name})."
                        ),
                    )
                )

        for engineer in team.engineers:
            if not engineer.has_certifications or not engineer.has_project_history:
                findings.append(
                    RiskFinding(
                        finding_type=RiskFindingType.INCOMPLETE_EVIDENCE,
                        severity=RiskSeverity.LOW,
                        engineer_id=engineer.id,
                        message=(
                            f"Engineer '{engineer.name}' has incomplete evidence "
                            f"(certifications={engineer.has_certifications}, "
                            f"projects={engineer.has_project_history})."
                        ),
                    )
                )

        return findings

    def _engineer_name(self, engineers: list[EngineerProfile], engineer_id: str) -> str:
        for engineer in engineers:
            if engineer.id == engineer_id:
                return engineer.name
        return engineer_id
