"""Unit tests for deterministic simulation identifiers."""

from app.domain.simulation_models import (
    AddSimulationOperation,
    CompareSimulationOperation,
    RemoveSimulationOperation,
)
from app.domain.policy import DEFAULT_POLICY_VERSION
from app.services.simulation.simulation_id import build_simulation_id


def _sim_id(**overrides):
    defaults = {
        "project_id": "azure_ai_migration",
        "baseline_engineer_ids": ["kavi", "vikram"],
        "operation": RemoveSimulationOperation(engineer_id="kavi"),
        "proposed_engineer_ids": ["vikram"],
        "policy_version": DEFAULT_POLICY_VERSION,
    }
    defaults.update(overrides)
    return build_simulation_id(**defaults)


class TestSimulationIdDeterminism:
    def test_identical_logical_simulation_same_id(self):
        assert _sim_id() == _sim_id()

    def test_reordered_baseline_same_id(self):
        first = _sim_id(baseline_engineer_ids=["kavi", "vikram", "arjun"])
        second = _sim_id(baseline_engineer_ids=["arjun", "kavi", "vikram"])
        assert first == second

    def test_reordered_proposed_same_id(self):
        operation = CompareSimulationOperation(proposed_engineer_ids=["kavi", "vikram"])
        first = _sim_id(
            operation=operation,
            proposed_engineer_ids=["kavi", "vikram"],
        )
        second = _sim_id(
            operation=CompareSimulationOperation(proposed_engineer_ids=["vikram", "kavi"]),
            proposed_engineer_ids=["vikram", "kavi"],
        )
        assert first == second

    def test_different_operation_different_id(self):
        remove_id = _sim_id(operation=RemoveSimulationOperation(engineer_id="kavi"))
        add_id = _sim_id(
            operation=AddSimulationOperation(engineer_id="arjun"),
            proposed_engineer_ids=["kavi", "vikram", "arjun"],
        )
        assert remove_id != add_id

    def test_different_project_different_id(self):
        assert _sim_id() != _sim_id(project_id="other_project")

    def test_different_proposed_team_different_id(self):
        assert _sim_id(proposed_engineer_ids=["vikram"]) != _sim_id(
            proposed_engineer_ids=["arjun"]
        )

    def test_policy_version_participates(self):
        assert _sim_id(policy_version="v1") != _sim_id(policy_version="v2")

    def test_id_length_matches_assessment_convention(self):
        assert len(_sim_id()) == 16

    def test_not_equal_to_assessment_id(self):
        from app.services.identifiers import build_assessment_id

        assessment_id = build_assessment_id(
            "azure_ai_migration",
            ["kavi", "vikram"],
            DEFAULT_POLICY_VERSION,
        )
        assert _sim_id() != assessment_id
