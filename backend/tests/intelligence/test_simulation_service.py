"""Unit tests for team simulation service behavior."""

import copy

from app.domain.simulation_models import (
    AddSimulationOperation,
    CompareSimulationOperation,
    RemoveSimulationOperation,
    ReplaceSimulationOperation,
)
from app.services.team_simulation_service import TeamSimulationService
from tests.intelligence.fixtures import balanced_team_request

SERVICE = TeamSimulationService()


def _simulate(operation, baseline=None, proposed=None):
    request = balanced_team_request()
    baseline_engineers = baseline or list(request.team.engineers)
    if proposed is None:
        from app.services.simulation.team_transformation import TeamTransformationService

        proposed_ids = TeamTransformationService().compute_proposed_ids(
            [engineer.id for engineer in baseline_engineers],
            operation,
        )
        by_id = {engineer.id: engineer for engineer in request.team.engineers}
        for engineer_id in proposed_ids:
            if engineer_id not in by_id:
                from app.repositories.mock_catalog_repository import MockCatalogRepository

                engineer = MockCatalogRepository().get_domain_engineer_by_id(engineer_id)
                if engineer is not None:
                    by_id[engineer_id] = engineer
        proposed_engineers = [by_id[engineer_id] for engineer_id in proposed_ids]
    else:
        proposed_engineers = proposed

    return SERVICE.simulate(
        project=request.project,
        baseline_engineers=baseline_engineers,
        proposed_engineers=proposed_engineers,
        operation=operation,
    )


class TestRemoveEngineer:
    def test_remove_critical_engineer_declines_readiness(self):
        result = _simulate(RemoveSimulationOperation(engineer_id="kavi"))
        assert result.readiness_score_delta < 0

    def test_remove_non_critical_engineer_when_supported(self):
        result = _simulate(RemoveSimulationOperation(engineer_id="vikram"))
        assert isinstance(result.readiness_score_delta, int)


class TestAddEngineer:
    def test_add_missing_specialist(self):
        result = _simulate(AddSimulationOperation(engineer_id="arjun"))
        assert len(result.proposed_team.engineer_ids) == 3


class TestReplaceEngineer:
    def test_replace_changes_team(self):
        result = _simulate(
            ReplaceSimulationOperation(remove_engineer_id="kavi", add_engineer_id="arjun")
        )
        assert "arjun" in result.proposed_team.engineer_ids
        assert "kavi" not in result.proposed_team.engineer_ids


class TestCompareOperation:
    def test_unchanged_scenario_zero_deltas(self):
        baseline = balanced_team_request().team.engineers
        result = _simulate(
            CompareSimulationOperation(
                proposed_engineer_ids=[engineer.id for engineer in baseline]
            ),
            baseline=baseline,
            proposed=baseline,
        )
        assert result.readiness_score_delta == 0
        assert result.confidence_delta == 0
        assert result.newly_introduced_gaps == []
        assert result.resolved_gaps == []

    def test_empty_proposed_team(self):
        result = _simulate(
            CompareSimulationOperation(proposed_engineer_ids=[]),
            proposed=[],
        )
        assert result.proposed_team.engineer_ids == []


class TestDeterminism:
    def test_repeated_simulation_equality(self):
        first = _simulate(RemoveSimulationOperation(engineer_id="kavi"))
        second = _simulate(RemoveSimulationOperation(engineer_id="kavi"))
        assert first.model_dump() == second.model_dump()

    def test_baseline_not_mutated(self):
        request = balanced_team_request()
        baseline_copy = copy.deepcopy(request.team.engineers)
        _simulate(RemoveSimulationOperation(engineer_id="kavi"), baseline=baseline_copy)
        assert [engineer.id for engineer in baseline_copy] == ["kavi", "vikram"]


class TestDecisionTraceReconciliation:
    def test_readiness_trace_delta_reconciles(self):
        result = _simulate(RemoveSimulationOperation(engineer_id="kavi"))
        readiness_delta = sum(
            entry.contribution_delta
            for entry in result.decision_trace_delta
            if entry.step == "readiness"
        )
        assert round(readiness_delta, 2) == float(result.readiness_score_delta)

    def test_confidence_trace_delta_reconciles(self):
        result = _simulate(RemoveSimulationOperation(engineer_id="kavi"))
        confidence_delta = sum(
            entry.contribution_delta
            for entry in result.decision_trace_delta
            if entry.step == "confidence"
        )
        assert round(confidence_delta, 2) == float(result.confidence_delta)
