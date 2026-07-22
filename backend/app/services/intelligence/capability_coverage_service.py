"""Deterministic capability coverage analysis for a team against project requirements."""

from app.domain.capability_registry import get_capability
from app.domain.enums import CapabilityCategory, CoverageLevel
from app.domain.evidence import (
    capability_display_name,
    classify_coverage_level,
    team_proficiency_for_capability,
)
from app.domain.models import CoverageResult, ProjectProfile, TeamComposition


class CapabilityCoverageService:
    def analyze(
        self,
        project: ProjectProfile,
        team: TeamComposition,
    ) -> list[CoverageResult]:
        results: list[CoverageResult] = []

        for requirement in project.requirements:
            definition = get_capability(requirement.capability_id)
            if definition is not None:
                category = definition.category
                name = definition.name
            else:
                category = CapabilityCategory.DELIVERY_EXECUTION
                name = capability_display_name(requirement.capability_id)

            proficiency, covering_ids = team_proficiency_for_capability(
                team.engineers,
                requirement.capability_id,
            )
            level = classify_coverage_level(proficiency, len(covering_ids))

            results.append(
                CoverageResult(
                    capability_id=requirement.capability_id,
                    capability_name=name,
                    category=category,
                    level=level,
                    team_proficiency=proficiency,
                    covering_engineer_ids=covering_ids,
                    is_critical=requirement.critical,
                    weight=requirement.weight,
                )
            )

        return results

    def covered_capability_ids(self, coverage_results: list[CoverageResult]) -> list[str]:
        return [
            result.capability_id
            for result in coverage_results
            if result.level != CoverageLevel.MISSING
        ]

    def missing_capability_ids(self, coverage_results: list[CoverageResult]) -> list[str]:
        return [
            result.capability_id
            for result in coverage_results
            if result.level == CoverageLevel.MISSING
        ]
