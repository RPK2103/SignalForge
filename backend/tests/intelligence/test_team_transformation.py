"""Unit tests for team transformation semantics."""

import copy

import pytest

from app.domain.simulation_models import (
    AddSimulationOperation,
    CompareSimulationOperation,
    RemoveSimulationOperation,
    ReplaceSimulationOperation,
)
from app.services.simulation.exceptions import SimulationValidationError
from app.services.simulation.team_transformation import TeamTransformationService
from tests.intelligence.fixtures import balanced_team_request


SERVICE = TeamTransformationService()


def _baseline_ids():
    request = balanced_team_request()
    return [engineer.id for engineer in request.team.engineers]


class TestAddOperation:
    def test_add_valid_engineer(self):
        ids = SERVICE.compute_proposed_ids(_baseline_ids(), AddSimulationOperation(engineer_id="arjun"))
        assert ids == ["arjun", "kavi", "vikram"]

    def test_duplicate_addition_rejected(self):
        with pytest.raises(SimulationValidationError) as exc:
            SERVICE.compute_proposed_ids(_baseline_ids(), AddSimulationOperation(engineer_id="kavi"))
        assert exc.value.status_code == 409


class TestRemoveOperation:
    def test_remove_existing_engineer(self):
        ids = SERVICE.compute_proposed_ids(_baseline_ids(), RemoveSimulationOperation(engineer_id="kavi"))
        assert ids == ["vikram"]

    def test_remove_absent_engineer_rejected(self):
        with pytest.raises(SimulationValidationError) as exc:
            SERVICE.compute_proposed_ids(_baseline_ids(), RemoveSimulationOperation(engineer_id="arjun"))
        assert exc.value.status_code == 409

    def test_remove_final_engineer_allowed(self):
        ids = SERVICE.compute_proposed_ids(["kavi"], RemoveSimulationOperation(engineer_id="kavi"))
        assert ids == []


class TestReplaceOperation:
    def test_replace_valid(self):
        ids = SERVICE.compute_proposed_ids(
            _baseline_ids(),
            ReplaceSimulationOperation(remove_engineer_id="kavi", add_engineer_id="arjun"),
        )
        assert ids == ["arjun", "vikram"]

    def test_replace_absent_outgoing_rejected(self):
        with pytest.raises(SimulationValidationError):
            SERVICE.compute_proposed_ids(
                _baseline_ids(),
                ReplaceSimulationOperation(remove_engineer_id="arjun", add_engineer_id="kavi"),
            )

    def test_replace_same_engineer_rejected(self):
        with pytest.raises(SimulationValidationError) as exc:
            SERVICE.compute_proposed_ids(
                _baseline_ids(),
                ReplaceSimulationOperation(remove_engineer_id="kavi", add_engineer_id="kavi"),
            )
        assert exc.value.status_code == 400

    def test_replace_already_present_rejected(self):
        with pytest.raises(SimulationValidationError) as exc:
            SERVICE.compute_proposed_ids(
                _baseline_ids(),
                ReplaceSimulationOperation(remove_engineer_id="kavi", add_engineer_id="vikram"),
            )
        assert exc.value.status_code == 409


class TestCompareOperation:
    def test_compare_different_teams(self):
        ids = SERVICE.compute_proposed_ids(
            _baseline_ids(),
            CompareSimulationOperation(proposed_engineer_ids=["arjun"]),
        )
        assert ids == ["arjun"]

    def test_compare_same_logical_team(self):
        baseline = _baseline_ids()
        ids = SERVICE.compute_proposed_ids(
            baseline,
            CompareSimulationOperation(proposed_engineer_ids=["vikram", "kavi"]),
        )
        assert ids == baseline

    def test_compare_reordered_same_team(self):
        baseline = _baseline_ids()
        ids = SERVICE.compute_proposed_ids(
            baseline,
            CompareSimulationOperation(proposed_engineer_ids=["vikram", "kavi"]),
        )
        assert ids == baseline

    def test_compare_empty_proposed_team(self):
        ids = SERVICE.compute_proposed_ids(
            _baseline_ids(),
            CompareSimulationOperation(proposed_engineer_ids=[]),
        )
        assert ids == []

    def test_compare_duplicate_ids_rejected(self):
        with pytest.raises(SimulationValidationError):
            SERVICE.compute_proposed_ids(
                _baseline_ids(),
                CompareSimulationOperation(proposed_engineer_ids=["kavi", "kavi"]),
            )


class TestBaselineImmutability:
    def test_baseline_ids_not_mutated(self):
        baseline = _baseline_ids()
        original = copy.copy(baseline)
        SERVICE.compute_proposed_ids(baseline, RemoveSimulationOperation(engineer_id="kavi"))
        assert baseline == original
