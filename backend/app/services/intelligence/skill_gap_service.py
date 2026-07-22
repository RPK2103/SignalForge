"""Identifies missing and weak capability gaps."""

from app.domain.enums import CoverageLevel
from app.domain.models import CoverageResult, SkillGap


class SkillGapService:
    def analyze(self, coverage_results: list[CoverageResult]) -> list[SkillGap]:
        gaps: list[SkillGap] = []

        for result in coverage_results:
            if result.level in (CoverageLevel.MISSING, CoverageLevel.WEAK):
                gaps.append(
                    SkillGap(
                        capability_id=result.capability_id,
                        capability_name=result.capability_name,
                        category=result.category,
                        level=result.level,
                        is_critical=result.is_critical,
                        weight=result.weight,
                        covering_engineer_count=len(result.covering_engineer_ids),
                    )
                )

        return gaps

    def critical_gaps(self, gaps: list[SkillGap]) -> list[SkillGap]:
        return [gap for gap in gaps if gap.is_critical]

    def missing_gaps(self, gaps: list[SkillGap]) -> list[SkillGap]:
        return [gap for gap in gaps if gap.level == CoverageLevel.MISSING]

    def weak_gaps(self, gaps: list[SkillGap]) -> list[SkillGap]:
        return [gap for gap in gaps if gap.level == CoverageLevel.WEAK]
