"""Regression tests for shared deterministic identifier builders."""

from app.domain.policy import DEFAULT_POLICY_VERSION
from app.domain.simulation_models import RemoveSimulationOperation
from app.services.identifiers import build_assessment_id, build_simulation_id


class TestKnownAssessmentIds:
    def test_kavi_vikram_team(self):
        assert (
            build_assessment_id(
                "azure_ai_migration",
                ["kavi", "vikram"],
                DEFAULT_POLICY_VERSION,
            )
            == "4fdffba9e7673277"
        )

    def test_kavi_vikram_arjun_team(self):
        assert (
            build_assessment_id(
                "azure_ai_migration",
                ["kavi", "vikram", "arjun"],
                DEFAULT_POLICY_VERSION,
            )
            == "3cf399e4f0a26bf0"
        )

    def test_engineer_order_independent(self):
        forward = build_assessment_id(
            "azure_ai_migration",
            ["kavi", "vikram", "arjun"],
            DEFAULT_POLICY_VERSION,
        )
        reversed_ids = build_assessment_id(
            "azure_ai_migration",
            ["arjun", "vikram", "kavi"],
            DEFAULT_POLICY_VERSION,
        )
        assert forward == reversed_ids


class TestKnownSimulationIds:
    def test_remove_kavi_operation(self):
        assert (
            build_simulation_id(
                project_id="azure_ai_migration",
                baseline_engineer_ids=["kavi", "vikram"],
                operation=RemoveSimulationOperation(engineer_id="kavi"),
                proposed_engineer_ids=["vikram"],
                policy_version=DEFAULT_POLICY_VERSION,
            )
            == "2669a4307f0bef8b"
        )

    def test_simulation_id_differs_from_assessment_id(self):
        assessment_id = build_assessment_id(
            "azure_ai_migration",
            ["kavi", "vikram"],
            DEFAULT_POLICY_VERSION,
        )
        simulation_id = build_simulation_id(
            project_id="azure_ai_migration",
            baseline_engineer_ids=["kavi", "vikram"],
            operation=RemoveSimulationOperation(engineer_id="kavi"),
            proposed_engineer_ids=["vikram"],
            policy_version=DEFAULT_POLICY_VERSION,
        )
        assert simulation_id != assessment_id
