"""Unit tests for individual intelligence services."""

from app.domain.enums import CoverageLevel
from app.services.intelligence.capability_coverage_service import CapabilityCoverageService
from app.services.intelligence.skill_gap_service import SkillGapService
from tests.intelligence.fixtures import (
    balanced_team_request,
    missing_critical_request,
    weak_capability_request,
)


def test_capability_coverage_service_covers_all_requirements():
    request = balanced_team_request()
    results = CapabilityCoverageService().analyze(request.project, request.team)
    assert len(results) == 3
    assert all(result.level != CoverageLevel.MISSING for result in results)


def test_skill_gap_service_identifies_missing():
    request = missing_critical_request()
    coverage = CapabilityCoverageService().analyze(request.project, request.team)
    gaps = SkillGapService().analyze(coverage)
    assert any(gap.level == CoverageLevel.MISSING for gap in gaps)


def test_skill_gap_service_identifies_weak():
    request = weak_capability_request()
    coverage = CapabilityCoverageService().analyze(request.project, request.team)
    gaps = SkillGapService().analyze(coverage)
    assert any(gap.level == CoverageLevel.WEAK for gap in gaps)
