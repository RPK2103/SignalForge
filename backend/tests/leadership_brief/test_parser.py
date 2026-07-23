"""Leadership Brief parser tests."""

import pytest

from app.domain.leadership_brief_models import ProviderMode
from app.services.leadership_brief.parser import parse_leadership_brief
from app.services.leadership_brief.provider_interface import (
    ProviderMalformedOutputError,
    ProviderSchemaError,
)
from tests.leadership_brief.conftest import sample_evidence_package, valid_brief_from_package


class TestParser:
    def test_valid_json(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        parsed = parse_leadership_brief(brief.model_dump_json())
        assert parsed.decision == brief.decision

    def test_malformed_json(self):
        with pytest.raises(ProviderMalformedOutputError):
            parse_leadership_brief("{not-json")

    def test_markdown_fenced_json(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        with pytest.raises(ProviderMalformedOutputError):
            parse_leadership_brief(f"```json\n{brief.model_dump_json()}\n```")

    def test_missing_field(self):
        package = sample_evidence_package()
        payload = valid_brief_from_package(package).model_dump()
        payload.pop("decision")
        with pytest.raises(ProviderSchemaError):
            parse_leadership_brief(__import__("json").dumps(payload))

    def test_unknown_enum(self):
        package = sample_evidence_package()
        payload = valid_brief_from_package(package).model_dump()
        payload["decision"] = "approve_now"
        with pytest.raises(ProviderSchemaError):
            parse_leadership_brief(__import__("json").dumps(payload))

    def test_empty_mandatory_field(self):
        package = sample_evidence_package()
        payload = valid_brief_from_package(package).model_dump()
        payload["executive_summary"] = ""
        with pytest.raises(ProviderSchemaError):
            parse_leadership_brief(__import__("json").dumps(payload))

    def test_invalid_nested_action(self):
        package = sample_evidence_package()
        payload = valid_brief_from_package(package).model_dump()
        payload["staffing_actions"][0]["evidence_references"] = []
        with pytest.raises(ProviderSchemaError):
            parse_leadership_brief(__import__("json").dumps(payload))

    def test_unexpected_field(self):
        package = sample_evidence_package()
        payload = valid_brief_from_package(package).model_dump()
        payload["readiness_score"] = 99
        with pytest.raises(ProviderSchemaError):
            parse_leadership_brief(__import__("json").dumps(payload))

    def test_empty_provider_response(self):
        with pytest.raises(ProviderMalformedOutputError):
            parse_leadership_brief("")

    def test_provider_mode_validation(self):
        package = sample_evidence_package()
        brief = valid_brief_from_package(package)
        brief = brief.model_copy(update={"provider_mode": ProviderMode.DETERMINISTIC_FALLBACK})
        with pytest.raises(ProviderSchemaError):
            parse_leadership_brief(brief.model_dump_json())
