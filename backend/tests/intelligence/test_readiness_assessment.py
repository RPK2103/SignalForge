"""Comprehensive unit tests for Phase 2 intelligence domain."""

import pytest

from app.domain.enums import (
    ConfidenceLevel,
    CoverageLevel,
    RiskFindingType,
    RiskSeverity,
)
from app.domain.models import ProjectRequirement
from app.domain.policy import get_policy
from app.services.intelligence.readiness_assessment_service import ReadinessAssessmentService
from tests.intelligence.fixtures import (
    balanced_team_request,
    duplicate_engineers_request,
    empty_team_request,
    incomplete_evidence_request,
    key_person_request,
    missing_critical_request,
    no_requirements_request,
    weak_capability_request,
)

SERVICE = ReadinessAssessmentService()


def _readiness_trace_contributions(response):
    return [
        entry.contribution
        for entry in response.decision_trace
        if entry.step == "readiness"
        and entry.component in ("requirement", "dimension", "risk_penalty", "normalization")
    ]


def _confidence_trace_contributions(response):
    return [entry.contribution for entry in response.decision_trace if entry.step == "confidence"]


class TestBalancedTeam:
    def test_high_readiness_and_confidence(self):
        response = SERVICE.assess(balanced_team_request())
        assert response.readiness_score >= 70
        assert response.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        assert not any(gap.level == CoverageLevel.MISSING for gap in response.skill_gaps)

    def test_all_coverage_levels_represented(self):
        response = SERVICE.assess(balanced_team_request())
        levels = {result.level for result in response.coverage_results}
        assert CoverageLevel.STRONG in levels or CoverageLevel.ADEQUATE in levels


class TestMissingCriticalCapability:
    def test_detects_missing_critical_gap(self):
        response = SERVICE.assess(missing_critical_request())
        critical_missing = [
            gap for gap in response.skill_gaps if gap.is_critical and gap.level == CoverageLevel.MISSING
        ]
        assert critical_missing
        assert any(
            finding.finding_type == RiskFindingType.MISSING_CRITICAL_CAPABILITY
            for finding in response.risk_findings
        )

    def test_readiness_lower_than_balanced(self):
        balanced = SERVICE.assess(balanced_team_request())
        missing = SERVICE.assess(missing_critical_request())
        assert missing.readiness_score < balanced.readiness_score


class TestWeakCapability:
    def test_detects_weak_gap(self):
        response = SERVICE.assess(weak_capability_request())
        weak = [gap for gap in response.skill_gaps if gap.level == CoverageLevel.WEAK]
        assert weak
        assert any(result.level == CoverageLevel.WEAK for result in response.coverage_results)

    def test_confidence_reduced_for_weak_critical(self):
        weak = SERVICE.assess(weak_capability_request())
        assert weak.confidence_score < 100
        assert any(
            "weak_critical" in entry.label
            for entry in weak.decision_trace
            if entry.step == "confidence"
        )


class TestKeyPersonDependency:
    def test_detects_single_person_coverage(self):
        response = SERVICE.assess(key_person_request())
        key_person_findings = [
            finding
            for finding in response.risk_findings
            if finding.finding_type == RiskFindingType.KEY_PERSON_DEPENDENCY
        ]
        assert key_person_findings
        assert any(finding.severity == RiskSeverity.HIGH for finding in key_person_findings)


class TestDuplicateEngineers:
    def test_deduplicates_team(self):
        response = SERVICE.assess(duplicate_engineers_request())
        duplicate_findings = [
            finding
            for finding in response.risk_findings
            if finding.finding_type == RiskFindingType.DUPLICATE_TEAM_MEMBER
        ]
        assert duplicate_findings


class TestEmptyTeam:
    def test_zero_readiness(self):
        response = SERVICE.assess(empty_team_request())
        assert response.readiness_score == 0
        assert response.confidence_level == ConfidenceLevel.LOW
        assert any(
            finding.finding_type == RiskFindingType.EMPTY_TEAM for finding in response.risk_findings
        )


class TestNoProjectRequirements:
    def test_empty_requirements_still_scores(self):
        response = SERVICE.assess(no_requirements_request())
        assert 0 <= response.readiness_score <= 100
        assert response.coverage_results == []
        assert response.skill_gaps == []


class TestIncompleteEngineerEvidence:
    def test_reduces_confidence(self):
        response = SERVICE.assess(incomplete_evidence_request())
        assert response.confidence_score < get_policy().CONFIDENCE_BASE
        assert any(
            finding.finding_type == RiskFindingType.INCOMPLETE_EVIDENCE
            for finding in response.risk_findings
        )


class TestScoreBoundaries:
    @pytest.mark.parametrize(
        "request_factory",
        [
            balanced_team_request,
            missing_critical_request,
            weak_capability_request,
            key_person_request,
            empty_team_request,
            no_requirements_request,
            incomplete_evidence_request,
        ],
    )
    def test_readiness_within_bounds(self, request_factory):
        response = SERVICE.assess(request_factory())
        assert 0 <= response.readiness_score <= 100

    @pytest.mark.parametrize(
        "request_factory",
        [
            balanced_team_request,
            missing_critical_request,
            weak_capability_request,
            key_person_request,
            empty_team_request,
        ],
    )
    def test_confidence_within_bounds(self, request_factory):
        response = SERVICE.assess(request_factory())
        assert 0 <= response.confidence_score <= 100


class TestDeterministicRepeatability:
    def test_same_input_same_output(self):
        request = balanced_team_request()
        first = SERVICE.assess(request)
        second = SERVICE.assess(request)
        assert first.readiness_score == second.readiness_score
        assert first.confidence_score == second.confidence_score
        assert first.decision_trace == second.decision_trace


class TestDecisionTraceReconciliation:
    def test_readiness_dimension_contributions_present(self):
        response = SERVICE.assess(balanced_team_request())
        dimension_entries = [
            entry for entry in response.decision_trace if entry.component == "dimension"
        ]
        assert len(dimension_entries) == 5

    def test_policy_version_on_trace_entries(self):
        response = SERVICE.assess(balanced_team_request())
        policy = get_policy()
        assert all(entry.policy_version == policy.POLICY_VERSION for entry in response.decision_trace)

    def test_readiness_trace_has_requirement_entries(self):
        response = SERVICE.assess(balanced_team_request())
        requirement_entries = [
            entry for entry in response.decision_trace if entry.component == "requirement"
        ]
        assert len(requirement_entries) == len(response.coverage_results)

    def test_readiness_contributions_reconcile_to_final_score(self):
        response = SERVICE.assess(balanced_team_request())
        readiness_total = sum(
            entry.contribution
            for entry in response.decision_trace
            if entry.step == "readiness"
        )
        assert round(readiness_total, 2) == float(response.readiness_score)

    def test_confidence_contributions_reconcile_to_final_score(self):
        response = SERVICE.assess(balanced_team_request())
        confidence_total = sum(
            entry.contribution
            for entry in response.decision_trace
            if entry.step == "confidence"
        )
        assert round(confidence_total, 2) == float(response.confidence_score)


class TestBoundedEnums:
    def test_coverage_levels_bounded(self):
        response = SERVICE.assess(balanced_team_request())
        allowed = {level.value for level in CoverageLevel}
        for result in response.coverage_results:
            assert result.level.value in allowed

    def test_confidence_level_bounded(self):
        response = SERVICE.assess(balanced_team_request())
        assert response.confidence_level in ConfidenceLevel

    def test_risk_severity_bounded(self):
        response = SERVICE.assess(key_person_request())
        allowed = {severity.value for severity in RiskSeverity}
        for finding in response.risk_findings:
            assert finding.severity.value in allowed


class TestServiceIsolation:
    def test_services_do_not_import_private_functions(self):
        import inspect
        import app.services.intelligence as intelligence

        for name in intelligence.__all__:
            module = getattr(intelligence, name)
            if inspect.isclass(module):
                source_file = inspect.getfile(module)
                assert "services/intelligence" in source_file.replace("\\", "/")


class TestWeightedRequirements:
    def test_heavy_weight_dominates_score(self):
        request = balanced_team_request()
        request.project.requirements = [
            ProjectRequirement(capability_id="azure", weight=3.0, critical=True),
            ProjectRequirement(capability_id="generative_ai", weight=0.5, critical=True),
        ]
        request.team.engineers = [request.team.engineers[0]]
        covered = SERVICE.assess(request)
        request.project.requirements[0].weight = 0.5
        request.project.requirements[1].weight = 3.0
        request.team.engineers[0].capabilities = [
            cap for cap in request.team.engineers[0].capabilities if cap.capability_id == "azure"
        ]
        partial = SERVICE.assess(request)
        assert covered.readiness_score != partial.readiness_score
