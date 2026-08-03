"""Chief-of-Staff generation telemetry integration (Phase 3 Prompt 8 remediation).

Drives the real ``ChiefOfStaffOrchestrator.generate`` pipeline and asserts exactly
one generation-count metric per call plus bounded, content-free failure/fallback
categories. No prompt text, evidence or citation IDs may appear as attributes.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffFailureCategory,
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
    DecisionOptionType,
    EvidenceEntryType,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffEvidencePackage,
    DecisionOptionCandidate,
    EvidenceEntry,
    FreshnessSummary,
    TargetLifecycleInfo,
    TruncationMetadata,
)
from app.observability.attributes import ALLOWED_ATTRIBUTES
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.services.chief_of_staff.orchestration import ChiefOfStaffOrchestrator
from app.services.chief_of_staff.provider_interface import (
    CosProviderGenerationResult,
    CosProviderSchemaError,
    CosProviderTimeoutError,
)

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
PACKAGE_ID = "snap-telemetry"


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def _package() -> ChiefOfStaffEvidencePackage:
    entries = [
        EvidenceEntry(
            evidence_id="pkg:1",
            evidence_type=EvidenceEntryType.PACKAGE_METADATA,
            source_type="package",
            source_record_id="pkg",
            summary="package",
            semantic_classification="package_metadata",
            provenance="test",
            payload_hash="b" * 16,
            tenant_id="novabank",
            source_event_time=AS_OF,
        ),
        EvidenceEntry(
            evidence_id="tgt:1",
            evidence_type=EvidenceEntryType.TARGET_METADATA,
            source_type="project",
            source_record_id="proj-1",
            summary="Demo project",
            semantic_classification="target_metadata",
            provenance="test",
            payload_hash="c" * 16,
            tenant_id="novabank",
            source_event_time=AS_OF,
        ),
    ]
    return ChiefOfStaffEvidencePackage(
        tenant_id="novabank",
        target_type=ChiefOfStaffTargetType.PROJECT,
        target_id="proj-1",
        target_stable_id="proj-1",
        as_of_at=AS_OF,
        intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
        target_lifecycle=TargetLifecycleInfo(
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="proj-1",
            display_name="Demo",
        ),
        freshness_summary=FreshnessSummary(overall_state="fresh"),
        truncation=TruncationMetadata(),
        evidence_entries=entries,
        decision_option_candidates=[
            DecisionOptionCandidate(
                option_type=DecisionOptionType.CONTINUE_MONITORING,
                eligible=True,
                rationale="monitor",
                supporting_evidence_ids=["pkg:1"],
            )
        ],
        package_hash=PACKAGE_ID,
    )


class _FailingProvider:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(self, *, evidence_package_json: str, prompt_bundle):
        raise self._exc


class _RawProvider:
    def __init__(self, raw: str) -> None:
        self._raw = raw

    def generate(self, *, evidence_package_json: str, prompt_bundle):
        return CosProviderGenerationResult(
            raw_content=self._raw,
            provider_mode=ChiefOfStaffProviderMode.AZURE_OPENAI,
            duration_ms=12,
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            model_deployment_id="test-deploy",
        )


def _settings_ai_on() -> Settings:
    return Settings(
        AI_ENABLED=True,
        AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
        AZURE_OPENAI_API_KEY="test-key",
        AZURE_OPENAI_DEPLOYMENT="test-deploy",
    )


def _generate(orch: ChiefOfStaffOrchestrator):
    return orch.generate(
        _package(),
        evidence_package_hash=PACKAGE_ID,
        requested_provider=ChiefOfStaffProviderMode.AZURE_OPENAI,
    )


def test_deterministic_fallback_when_ai_disabled_emits_one_generation(obs_provider):
    orch = ChiefOfStaffOrchestrator(settings=Settings(AI_ENABLED=False))
    _generate(orch)
    assert obs_provider.counter_total(MetricName.COS_GENERATIONS) == 1
    assert (
        obs_provider.counter_total(
            MetricName.COS_GENERATIONS, provider_type="deterministic_fallback"
        )
        == 1
    )
    assert obs_provider.counter_total(MetricName.COS_FALLBACKS) == 1


def test_provider_timeout_maps_to_fallback_category(obs_provider):
    orch = ChiefOfStaffOrchestrator(
        settings=_settings_ai_on(), azure_provider=_FailingProvider(CosProviderTimeoutError("t"))
    )
    _generate(orch)
    assert obs_provider.counter_total(MetricName.COS_GENERATIONS) == 1
    assert obs_provider.counter_total(MetricName.COS_FALLBACKS) == 1
    assert (
        obs_provider.counter_total(
            MetricName.COS_FALLBACKS,
            fallback_category=ChiefOfStaffFailureCategory.TIMEOUT.value,
        )
        == 1
    )


def test_schema_failure_recorded_and_falls_back(obs_provider):
    orch = ChiefOfStaffOrchestrator(
        settings=_settings_ai_on(),
        azure_provider=_FailingProvider(CosProviderSchemaError("schema")),
    )
    _generate(orch)
    assert obs_provider.counter_total(MetricName.COS_SCHEMA_FAILURES) == 1
    assert obs_provider.counter_total(MetricName.COS_GENERATIONS) == 1


def test_malformed_output_recorded_as_parse_failure(obs_provider):
    orch = ChiefOfStaffOrchestrator(settings=_settings_ai_on(), azure_provider=_RawProvider("nope"))
    _generate(orch)
    assert obs_provider.counter_total(MetricName.COS_PARSE_FAILURES) == 1
    assert obs_provider.counter_total(MetricName.COS_GENERATIONS) == 1


def test_no_raw_content_in_emitted_attributes(obs_provider):
    orch = ChiefOfStaffOrchestrator(
        settings=_settings_ai_on(), azure_provider=_FailingProvider(CosProviderTimeoutError("t"))
    )
    _generate(orch)
    # Every emitted attribute key must be on the bounded allowlist — no prompt,
    # evidence, citation id, provider output or exception text can appear.
    for (name, attrs), _value in obs_provider.counters.items():
        for key in dict(attrs):
            assert key in ALLOWED_ATTRIBUTES


def test_provider_failure_never_breaks_generation():
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

        def record_value(self, *a, **k):
            raise RuntimeError("boom")

    set_observability_provider(ExplodingProvider())
    try:
        orch = ChiefOfStaffOrchestrator(settings=Settings(AI_ENABLED=False))
        outcome = _generate(orch)
        assert outcome.brief is not None  # business result intact despite telemetry failure
    finally:
        reset_observability_provider()
