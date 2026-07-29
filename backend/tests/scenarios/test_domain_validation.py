"""Domain and validation tests for Continuous Scenario Intelligence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.scenario_enums import ScenarioKind
from app.services.enterprise.exceptions import EnterpriseValidationError
from app.services.scenarios.validation import normalize_assumptions, specification_hash

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def test_normalize_engineer_unavailable():
    result = normalize_assumptions(
        ScenarioKind.ENGINEER_UNAVAILABLE,
        {
            "engineer_id": "eng_abc",
            "unavailable_from": AS_OF.isoformat(),
            "unavailable_until": (AS_OF + timedelta(days=30)).isoformat(),
        },
    )
    assert result["kind"] == "engineer_unavailable"
    assert len(result["changes"]) == 1


def test_reject_invalid_percentage():
    with pytest.raises(EnterpriseValidationError):
        normalize_assumptions(
            ScenarioKind.TEAM_CAPACITY_REDUCTION,
            {
                "team_id": "team_x",
                "reduction_percentage": 0,
                "effective_from": AS_OF.isoformat(),
                "effective_until": (AS_OF + timedelta(days=10)).isoformat(),
            },
        )


def test_reject_invalid_delay():
    with pytest.raises(EnterpriseValidationError):
        normalize_assumptions(
            ScenarioKind.DEPENDENCY_DELAY,
            {"dependency_id": "dep_x", "delay_days": 200},
        )


def test_reject_secret_keys():
    with pytest.raises(EnterpriseValidationError):
        normalize_assumptions(
            ScenarioKind.ENGINEER_UNAVAILABLE,
            {
                "engineer_id": "eng_abc",
                "password": "secret",
                "unavailable_from": AS_OF.isoformat(),
                "unavailable_until": (AS_OF + timedelta(days=5)).isoformat(),
            },
        )


def test_reject_recursive_combined():
    with pytest.raises(EnterpriseValidationError):
        normalize_assumptions(
            ScenarioKind.COMBINED,
            {
                "changes": [
                    {
                        "kind": "combined",
                        "changes": [],
                    }
                ]
            },
        )


def test_reject_duplicate_combined_changes():
    change = {
        "kind": "dependency_delay",
        "dependency_id": "dep_x",
        "delay_days": 10,
    }
    with pytest.raises(EnterpriseValidationError):
        normalize_assumptions(ScenarioKind.COMBINED, {"changes": [change, dict(change)]})


def test_specification_hash_order_independent():
    a = {
        "changes": [
            {"kind": "dependency_delay", "dependency_id": "dep_a", "delay_days": 5},
            {"kind": "dependency_delay", "dependency_id": "dep_b", "delay_days": 6},
        ]
    }
    b = {
        "changes": [
            {"kind": "dependency_delay", "dependency_id": "dep_b", "delay_days": 6},
            {"kind": "dependency_delay", "dependency_id": "dep_a", "delay_days": 5},
        ]
    }
    h1 = specification_hash(
        tenant_id="novabank",
        scenario_kind=ScenarioKind.COMBINED,
        target_type="project",
        target_id="proj_x",
        assumptions=a,
    )
    h2 = specification_hash(
        tenant_id="novabank",
        scenario_kind=ScenarioKind.COMBINED,
        target_type="project",
        target_id="proj_x",
        assumptions=b,
    )
    assert h1 == h2
