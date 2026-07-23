"""Grounding validator tests."""

import pytest

from app.domain.leadership_brief_models import ProviderMode
from app.services.leadership_brief.grounding_validator import (
    GroundingValidationError,
    validate_grounding,
)
from tests.leadership_brief.conftest import sample_evidence_package, valid_brief_from_package


class TestGroundingValidator:
    def test_valid_evidence_references(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)

    def test_unknown_risk_reference(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief.top_risks[0].evidence_references = ["risk:deadbeefdeadbeef"]
        brief.evidence_references = ["risk:deadbeefdeadbeef"]
        with pytest.raises(GroundingValidationError):
            validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)

    def test_unknown_trace_reference(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief.top_risks[0].evidence_references = ["trace:deadbeefdeadbeef"]
        brief.evidence_references = ["trace:deadbeefdeadbeef"]
        with pytest.raises(GroundingValidationError):
            validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)

    def test_missing_evidence_on_risk(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief.top_risks[0].evidence_references = []
        with pytest.raises(GroundingValidationError):
            validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)

    def test_unknown_capability_id(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief.staffing_actions[0].capability_id = "unknown-capability"
        with pytest.raises(GroundingValidationError):
            validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)

    def test_unknown_engineer_id(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief.staffing_actions[0].engineer_ids = ["unknown-engineer"]
        with pytest.raises(GroundingValidationError):
            validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)

    def test_incorrect_top_level_reference_union(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief.evidence_references = []
        with pytest.raises(GroundingValidationError):
            validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)

    def test_provider_mode_mismatch(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        with pytest.raises(GroundingValidationError):
            validate_grounding(
                brief,
                package,
                expected_provider_mode=ProviderMode.DETERMINISTIC_FALLBACK,
            )

    def test_unsupported_structured_metric(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief.executive_summary = "Delivery confidence is 999/100 based on new analysis."
        with pytest.raises(GroundingValidationError):
            validate_grounding(brief, package, expected_provider_mode=ProviderMode.AZURE_OPENAI)
