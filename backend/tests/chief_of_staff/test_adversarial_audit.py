"""Adversarial behavioral proofs for Phase 3 Prompt 6 audit gaps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.models import enterprise as ent_orm
from app.db.models.assessment import Assessment, AssessmentRiskFinding
from app.db.models.catalog import Project
from app.domain.chief_of_staff_constants import (
    MAX_CITATIONS_PER_CLAIM,
    MAX_DETERMINISTIC_RISKS,
    MAX_EVIDENCE_SIGNALS,
    MAX_GRAPH_FINDINGS,
    MAX_SCENARIO_IMPACTS,
    MAX_SCENARIO_RUNS,
)
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffClaimAuthorship,
    ChiefOfStaffClaimSupportStatus,
    ChiefOfStaffClaimType,
    ChiefOfStaffFailureCategory,
    ChiefOfStaffGenerationState,
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
    CitationResult,
    DecisionOptionType,
    EvidenceEntryType,
    GroundingResult,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffBrief,
    ChiefOfStaffCitation,
    ChiefOfStaffClaim,
    ChiefOfStaffEvidencePackage,
    ChiefOfStaffRequest,
    DecisionOptionCandidate,
    EvidenceEntry,
    FreshnessSummary,
    PredictionProvenanceSummary,
    TargetLifecycleInfo,
    TruncationMetadata,
)
from app.domain.prediction_enums import EstimateKind
from app.services.chief_of_staff.canonicalization import (
    attach_package_hash,
    compute_brief_output_hash,
)
from app.services.chief_of_staff.evidence_assembly import EvidenceAssemblyService
from app.services.chief_of_staff.fallback import build_fallback_brief
from app.services.chief_of_staff.grounding import (
    CitationValidationError,
    UnsupportedClaimError,
    validate_brief_grounding,
)
from app.services.chief_of_staff.novabank_seed import seed_novabank_briefs
from app.services.chief_of_staff.orchestration import ChiefOfStaffOrchestrator
from app.services.chief_of_staff.provider_interface import CosProviderGenerationResult
from app.services.chief_of_staff.responsible_language import (
    ResponsibleLanguageError,
    validate_responsible_language,
)
from app.services.chief_of_staff.service import ChiefOfStaffService
from app.services.enterprise.exceptions import (
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
PACKAGE_ID = "snap-audit"  # content-canonical package hash in unit fixtures


def _first_project_id(uow, ctx) -> str:
    projects = uow.initiatives_projects.list_projects(ctx, limit=5, offset=0)
    assert projects.items
    return projects.items[0].enterprise_project_id


def _entry(
    eid: str,
    etype: EvidenceEntryType,
    *,
    summary: str = "ok",
    tenant_id: str = "novabank",
    event_time: datetime | None = AS_OF,
) -> EvidenceEntry:
    return EvidenceEntry(
        evidence_id=eid,
        evidence_type=etype,
        source_type="test",
        source_record_id=eid,
        summary=summary,
        semantic_classification="test",
        provenance="test",
        payload_hash="a" * 16,
        tenant_id=tenant_id,
        source_event_time=event_time,
    )


def _package(entries: list[EvidenceEntry], **overrides) -> ChiefOfStaffEvidencePackage:
    data = dict(
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
                supporting_evidence_ids=[
                    next(
                        (
                            e.evidence_id
                            for e in entries
                            if e.evidence_type == EvidenceEntryType.PACKAGE_METADATA
                        ),
                        entries[0].evidence_id,
                    )
                ],
            )
        ],
        package_hash=PACKAGE_ID,
    )
    data.update(overrides)
    return ChiefOfStaffEvidencePackage(**data)


def _brief_from_claim(
    claim: ChiefOfStaffClaim,
    citations: list[ChiefOfStaffCitation],
    *,
    estimate_kind: EstimateKind | None = None,
    probability: float | None = None,
    options: list[DecisionOptionType] | None = None,
) -> ChiefOfStaffBrief:
    return ChiefOfStaffBrief(
        schema_version="chief-of-staff-brief-v1",
        intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
        target_type=ChiefOfStaffTargetType.PROJECT,
        target_id="proj-1",
        as_of_at=AS_OF,
        sections=[],
        claims=[claim],
        citations=citations,
        decision_option_types=options or [DecisionOptionType.CONTINUE_MONITORING],
        limitations=["synthetic"],
        provider_mode=ChiefOfStaffProviderMode.AZURE_OPENAI,
        generation_state=ChiefOfStaffGenerationState.GENERATED,
        fallback_visible=False,
        estimate_kind=estimate_kind,
        probability=probability,
        uncalibrated_score=None,
    )


def test_request_rejects_prior_for_incompatible_intent():
    with pytest.raises(ValidationError):
        ChiefOfStaffRequest(
            tenant_id="novabank",
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="proj-1",
            as_of_at=AS_OF,
            prior_brief_id="brief-x",
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        )


def test_maximum_bound_package_truncates_and_hashes(seeded_novabank, uow, novabank_tenant):
    """Behavioral max-bound harness: assemble at declared ceilings and +1 overflow."""
    target_id = _first_project_id(uow, novabank_tenant)
    assembly = EvidenceAssemblyService(uow)

    # Synthesize oversized evidence lists directly on a package to prove truncation
    # metadata and hash stability at the declared ceilings.
    risks = [
        _entry(f"risk-{i:03d}", EvidenceEntryType.ASSESSMENT_RISK, summary=f"risk {i}")
        for i in range(MAX_DETERMINISTIC_RISKS + 1)
    ]
    findings = [
        _entry(f"find-{i:03d}", EvidenceEntryType.GRAPH_FINDING, summary=f"finding {i}")
        for i in range(MAX_GRAPH_FINDINGS + 1)
    ]
    signals = [
        _entry(f"sig-{i:03d}", EvidenceEntryType.EVIDENCE_SIGNAL, summary=f"signal {i}")
        for i in range(MAX_EVIDENCE_SIGNALS + 1)
    ]
    runs = [
        _entry(f"run-{i:03d}", EvidenceEntryType.SCENARIO_RUN, summary=f"run {i}")
        for i in range(MAX_SCENARIO_RUNS + 1)
    ]
    impacts = [
        _entry(f"imp-{i:03d}", EvidenceEntryType.SCENARIO_IMPACT, summary=f"impact {i}")
        for i in range(MAX_SCENARIO_IMPACTS + 1)
    ]
    options = [
        DecisionOptionCandidate(
            option_type=DecisionOptionType.CONTINUE_MONITORING,
            eligible=True,
            rationale=f"opt {i}",
            supporting_evidence_ids=[],
        )
        for i in range(10)
    ]
    claims_entries = risks[:MAX_DETERMINISTIC_RISKS] + findings[:MAX_GRAPH_FINDINGS]
    package = _package(
        claims_entries
        + signals[:MAX_EVIDENCE_SIGNALS]
        + runs[:MAX_SCENARIO_RUNS]
        + impacts[:MAX_SCENARIO_IMPACTS]
        + [_entry("pkg", EvidenceEntryType.PACKAGE_METADATA, summary="meta")],
        deterministic_risks=risks[:MAX_DETERMINISTIC_RISKS],
        graph_findings=findings[:MAX_GRAPH_FINDINGS],
        evidence_signals=signals[:MAX_EVIDENCE_SIGNALS],
        scenario_runs=runs[:MAX_SCENARIO_RUNS],
        scenario_impacts=impacts[:MAX_SCENARIO_IMPACTS],
        decision_option_candidates=options,
        truncation=TruncationMetadata(
            risks_truncated=True,
            risks_total=MAX_DETERMINISTIC_RISKS + 1,
            risks_included=MAX_DETERMINISTIC_RISKS,
            graph_findings_truncated=True,
            graph_findings_total=MAX_GRAPH_FINDINGS + 1,
            graph_findings_included=MAX_GRAPH_FINDINGS,
            evidence_signals_truncated=True,
            evidence_signals_total=MAX_EVIDENCE_SIGNALS + 1,
            evidence_signals_included=MAX_EVIDENCE_SIGNALS,
            scenario_runs_truncated=True,
            scenario_runs_total=MAX_SCENARIO_RUNS + 1,
            scenario_runs_included=MAX_SCENARIO_RUNS,
            scenario_impacts_truncated=True,
            scenario_impacts_total=MAX_SCENARIO_IMPACTS + 1,
            scenario_impacts_included=MAX_SCENARIO_IMPACTS,
        ),
        target_id=target_id,
        target_stable_id=target_id,
    )
    hashed = attach_package_hash(package)
    assert hashed.truncation.any_truncated is True
    assert len(hashed.deterministic_risks) == MAX_DETERMINISTIC_RISKS
    assert len(hashed.graph_findings) == MAX_GRAPH_FINDINGS
    assert len(hashed.evidence_signals) == MAX_EVIDENCE_SIGNALS
    assert len(hashed.scenario_runs) == MAX_SCENARIO_RUNS
    assert len(hashed.scenario_impacts) == MAX_SCENARIO_IMPACTS
    brief = build_fallback_brief(hashed, evidence_package_hash=hashed.package_hash)
    assert len(brief.claims) <= 30
    assert all(len(c.evidence_ids) <= MAX_CITATIONS_PER_CLAIM for c in brief.claims)
    validate_brief_grounding(brief, hashed, evidence_package_hash=hashed.package_hash)

    # Overflow at model boundary must reject.
    with pytest.raises(ValidationError):
        _package(
            claims_entries + [_entry("pkg2", EvidenceEntryType.PACKAGE_METADATA, summary="meta")],
            deterministic_risks=risks,  # 21 > max 20
            target_id=target_id,
            target_stable_id=target_id,
        )

    # Live assembly still succeeds for NovaBank under bounds.
    live = assembly.assemble(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert live.package_hash
    assert len(live.deterministic_risks) <= MAX_DETERMINISTIC_RISKS
    assert len(live.graph_findings) <= MAX_GRAPH_FINDINGS


def test_assessment_included_when_legacy_link_present(
    seeded_novabank, uow, novabank_tenant, db_session
):
    target_id = _first_project_id(uow, novabank_tenant)
    legacy_id = "cos_audit_project"
    if db_session.get(Project, legacy_id) is None:
        db_session.add(Project(project_id=legacy_id, name="CoS Audit Project", schema_version="1"))
    row = db_session.get(ent_orm.EnterpriseProject, target_id)
    assert row is not None
    row.legacy_project_id = legacy_id
    assessment_id = uuid4()
    db_session.add(
        Assessment(
            assessment_record_id=assessment_id,
            assessment_id="a1",
            project_id=legacy_id,
            policy_version="policy_v1",
            schema_version="1",
            input_snapshot={},
            input_snapshot_hash="i" * 64,
            result_snapshot={},
            result_snapshot_hash="r" * 64,
            readiness_score=72,
            confidence_score=61,
            confidence_level="medium",
            created_at=AS_OF - timedelta(days=1),
            status="completed",
        )
    )
    db_session.add(
        AssessmentRiskFinding(
            assessment_record_id=assessment_id,
            finding_type="key_person_risk",
            severity="high",
            message="Key person concentration on critical path",
        )
    )
    db_session.commit()

    package = EvidenceAssemblyService(uow).assemble(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert package.readiness_score == 72.0
    assert package.assessment_confidence == 61.0
    assert package.assessment_evidence_id is not None
    assert any(
        e.evidence_type == EvidenceEntryType.READINESS_ASSESSMENT for e in package.evidence_entries
    )
    assert any(
        e.evidence_type == EvidenceEntryType.ASSESSMENT_RISK for e in package.deterministic_risks
    )


def test_missing_assessment_is_explicit(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    package = EvidenceAssemblyService(uow).assemble(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.EVIDENCE_GAP_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert package.readiness_score is None
    assert package.assessment_confidence is None
    assert any("readiness assessment" in w.lower() for w in package.missing_data_warnings)


def test_prior_brief_wrong_target_equivalent_to_missing(seeded_novabank, uow, novabank_tenant):
    projects = uow.initiatives_projects.list_projects(novabank_tenant, limit=5, offset=0)
    assert len(projects.items) >= 2
    service = ChiefOfStaffService(uow)
    prior = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=projects.items[0].enterprise_project_id,
            as_of_at=AS_OF - timedelta(days=3),
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    with pytest.raises(EnterpriseNotFoundError):
        service.generate(
            novabank_tenant,
            ChiefOfStaffRequest(
                tenant_id=novabank_tenant.tenant_id,
                intent=ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW,
                target_type=ChiefOfStaffTargetType.PROJECT,
                target_id=projects.items[1].enterprise_project_id,
                as_of_at=AS_OF,
                prior_brief_id=prior.brief.brief_id,
                requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
            ),
        )
    with pytest.raises(EnterpriseNotFoundError):
        service.generate(
            novabank_tenant,
            ChiefOfStaffRequest(
                tenant_id=novabank_tenant.tenant_id,
                intent=ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW,
                target_type=ChiefOfStaffTargetType.PROJECT,
                target_id=projects.items[1].enterprise_project_id,
                as_of_at=AS_OF,
                prior_brief_id="does-not-exist",
                requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
            ),
        )


def test_quality_summary_tenant_isolation(seeded_novabank, uow, novabank_tenant, tenant_b):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    summary_a = service.quality_summary(novabank_tenant)
    summary_b = service.quality_summary(tenant_b)
    assert summary_a.total_runs >= 1
    assert summary_b.total_runs == 0
    assert summary_b.fallback_count == 0
    assert summary_b.grounding_failures == 0


def test_grounding_failure_recorded_in_orchestration():
    entries = [
        _entry("pkg", EvidenceEntryType.PACKAGE_METADATA, summary="meta"),
        _entry("pred", EvidenceEntryType.DELIVERY_PREDICTION, summary="score only"),
    ]
    package = _package(entries)

    class _BadProvider:
        def generate(self, **_kwargs):
            bad = ChiefOfStaffBrief(
                schema_version="chief-of-staff-brief-v1",
                intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
                target_type=ChiefOfStaffTargetType.PROJECT,
                target_id="proj-1",
                as_of_at=AS_OF,
                sections=[],
                claims=[
                    ChiefOfStaffClaim(
                        claim_id="c1",
                        claim_type=ChiefOfStaffClaimType.DETERMINISTIC_FINDING,
                        text="Fabricated certainty",
                        support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                        authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                        temporal_cutoff=AS_OF,
                        evidence_ids=["missing-evidence"],
                        ordering_index=0,
                    )
                ],
                citations=[
                    ChiefOfStaffCitation(
                        citation_id="cit1",
                        claim_id="c1",
                        evidence_id="missing-evidence",
                        evidence_type=EvidenceEntryType.GRAPH_FINDING,
                        package_id=PACKAGE_ID,
                        ordering_index=0,
                    )
                ],
                decision_option_types=[DecisionOptionType.CONTINUE_MONITORING],
                limitations=[],
                provider_mode=ChiefOfStaffProviderMode.AZURE_OPENAI,
                generation_state=ChiefOfStaffGenerationState.GENERATED,
                fallback_visible=False,
            )
            return CosProviderGenerationResult(
                raw_content=bad.model_dump_json(),
                provider_mode=ChiefOfStaffProviderMode.AZURE_OPENAI,
                duration_ms=12,
                model_deployment_id="demo",
            )

    settings = Settings(
        AI_ENABLED=True,
        AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
        AZURE_OPENAI_API_KEY="test-key",
        AZURE_OPENAI_DEPLOYMENT="demo",
    )
    orch = ChiefOfStaffOrchestrator(settings=settings, azure_provider=_BadProvider())
    outcome = orch.generate(
        package,
        evidence_package_hash=PACKAGE_ID,
        requested_provider=ChiefOfStaffProviderMode.AZURE_OPENAI,
    )
    assert outcome.generation_state == ChiefOfStaffGenerationState.FALLBACK_GENERATED
    assert outcome.failure_category == ChiefOfStaffFailureCategory.CITATION_VALIDATION_FAILED
    assert outcome.grounding_result == GroundingResult.FAILED
    assert outcome.citation_result == CitationResult.FAILED
    assert outcome.brief.fallback_visible is True


@pytest.mark.parametrize(
    "text,exc_type",
    [
        ("Guaranteed delivery by Friday", ResponsibleLanguageError),
        ("This is causal proof of failure", ResponsibleLanguageError),
        ("Fire the engineer responsible", ResponsibleLanguageError),
        ("Rank engineers by blame", ResponsibleLanguageError),
        ("Microsoft endorses this estimate", ResponsibleLanguageError),
        ("Customer validated production calibrated model", ResponsibleLanguageError),
    ],
)
def test_responsible_language_rejects_overstatements(text, exc_type):
    entries = [_entry("pkg", EvidenceEntryType.PACKAGE_METADATA)]
    package = _package(entries)
    brief = build_fallback_brief(package, evidence_package_hash=PACKAGE_ID)
    poisoned = brief.model_copy(
        update={
            "claims": [brief.claims[0].model_copy(update={"text": text})]
            if brief.claims
            else [
                ChiefOfStaffClaim(
                    claim_id="c1",
                    claim_type=ChiefOfStaffClaimType.LIMITATION,
                    text=text,
                    support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                    authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                    temporal_cutoff=AS_OF,
                    evidence_ids=["pkg"],
                    ordering_index=0,
                )
            ]
        }
    )
    with pytest.raises(exc_type):
        validate_responsible_language(poisoned)


def test_adversarial_grounding_matrix():
    pred = _entry("pred", EvidenceEntryType.DELIVERY_PREDICTION)
    graph_ids = [f"graph-{i}" for i in range(MAX_CITATIONS_PER_CLAIM + 1)]
    graphs = [
        _entry(gid, EvidenceEntryType.GRAPH_FINDING, summary="medium dependency risk")
        for gid in graph_ids
    ]
    scen = _entry("scen", EvidenceEntryType.SCENARIO_IMPACT, summary="simulated impact")
    foreign = _entry("foreign", EvidenceEntryType.GRAPH_FINDING, tenant_id="other-tenant")
    stale = _entry(
        "stale",
        EvidenceEntryType.EVIDENCE_SIGNAL,
        event_time=AS_OF + timedelta(days=1),
    )
    pkg_meta = _entry("pkg", EvidenceEntryType.PACKAGE_METADATA)
    entries = [pred, *graphs, scen, foreign, stale, pkg_meta]
    package = _package(
        entries,
        prediction=PredictionProvenanceSummary(
            prediction_id="p1",
            estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
            probability=None,
            uncalibrated_score=0.33,
            model_id=None,
            model_state="candidate",
            model_was_promoted=False,
            horizon_days=90,
            as_of_at=AS_OF,
            notes=[],
        ),
        prediction_evidence_id="pred",
        decision_option_candidates=[
            DecisionOptionCandidate(
                option_type=DecisionOptionType.CONTINUE_MONITORING,
                eligible=True,
                rationale="monitor",
                supporting_evidence_ids=["pkg"],
            )
        ],
    )

    # 1. Uncalibrated score + probability rejected at domain boundary.
    with pytest.raises(ValidationError):
        _brief_from_claim(
            ChiefOfStaffClaim(
                claim_id="c1",
                claim_type=ChiefOfStaffClaimType.PREDICTION_ESTIMATE,
                text="Probability is 80%",
                support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                temporal_cutoff=AS_OF,
                evidence_ids=["pred"],
                ordering_index=0,
            ),
            [
                ChiefOfStaffCitation(
                    citation_id="cit1",
                    claim_id="c1",
                    evidence_id="pred",
                    evidence_type=EvidenceEntryType.DELIVERY_PREDICTION,
                    package_id=PACKAGE_ID,
                    ordering_index=0,
                )
            ],
            estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
            probability=0.8,
        )

    # Grounding also rejects uncalibrated+probability when constructed without domain check.
    bypass = ChiefOfStaffBrief.model_construct(
        schema_version="chief-of-staff-brief-v1",
        intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
        target_type=ChiefOfStaffTargetType.PROJECT,
        target_id="proj-1",
        as_of_at=AS_OF,
        sections=[],
        claims=[
            ChiefOfStaffClaim(
                claim_id="c1b",
                claim_type=ChiefOfStaffClaimType.PREDICTION_ESTIMATE,
                text="Probability is 80%",
                support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                temporal_cutoff=AS_OF,
                evidence_ids=["pred"],
                ordering_index=0,
            )
        ],
        citations=[
            ChiefOfStaffCitation(
                citation_id="cit1b",
                claim_id="c1b",
                evidence_id="pred",
                evidence_type=EvidenceEntryType.DELIVERY_PREDICTION,
                package_id=PACKAGE_ID,
                ordering_index=0,
            )
        ],
        decision_option_types=[DecisionOptionType.CONTINUE_MONITORING],
        limitations=["synthetic"],
        provider_mode=ChiefOfStaffProviderMode.AZURE_OPENAI,
        generation_state=ChiefOfStaffGenerationState.GENERATED,
        fallback_visible=False,
        estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
        probability=0.8,
        uncalibrated_score=0.33,
        horizon_days=None,
        synthetic_demo_scope=False,
    )
    with pytest.raises(UnsupportedClaimError):
        validate_brief_grounding(bypass, package, package_id=PACKAGE_ID)

    # 2. Fabricated evidence id.
    with pytest.raises(CitationValidationError):
        validate_brief_grounding(
            _brief_from_claim(
                ChiefOfStaffClaim(
                    claim_id="c2",
                    claim_type=ChiefOfStaffClaimType.DETERMINISTIC_FINDING,
                    text="Certain delivery failure",
                    support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                    authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                    temporal_cutoff=AS_OF,
                    evidence_ids=["does-not-exist"],
                    ordering_index=0,
                ),
                [
                    ChiefOfStaffCitation(
                        citation_id="cit2",
                        claim_id="c2",
                        evidence_id="does-not-exist",
                        evidence_type=EvidenceEntryType.GRAPH_FINDING,
                        package_id=PACKAGE_ID,
                        ordering_index=0,
                    )
                ],
            ),
            package,
            package_id=PACKAGE_ID,
        )

    # 3. Foreign-tenant evidence.
    with pytest.raises(CitationValidationError):
        validate_brief_grounding(
            _brief_from_claim(
                ChiefOfStaffClaim(
                    claim_id="c3",
                    claim_type=ChiefOfStaffClaimType.DETERMINISTIC_FINDING,
                    text="Foreign finding",
                    support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                    authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                    temporal_cutoff=AS_OF,
                    evidence_ids=["foreign"],
                    ordering_index=0,
                ),
                [
                    ChiefOfStaffCitation(
                        citation_id="cit3",
                        claim_id="c3",
                        evidence_id="foreign",
                        evidence_type=EvidenceEntryType.GRAPH_FINDING,
                        package_id=PACKAGE_ID,
                        ordering_index=0,
                    )
                ],
            ),
            package,
            package_id=PACKAGE_ID,
        )

    # 4. Temporal future evidence.
    with pytest.raises(CitationValidationError):
        validate_brief_grounding(
            _brief_from_claim(
                ChiefOfStaffClaim(
                    claim_id="c4",
                    claim_type=ChiefOfStaffClaimType.SOURCE_FACT,
                    text="Future signal",
                    support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                    authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                    temporal_cutoff=AS_OF,
                    evidence_ids=["stale"],
                    ordering_index=0,
                ),
                [
                    ChiefOfStaffCitation(
                        citation_id="cit4",
                        claim_id="c4",
                        evidence_id="stale",
                        evidence_type=EvidenceEntryType.EVIDENCE_SIGNAL,
                        package_id=PACKAGE_ID,
                        ordering_index=0,
                    )
                ],
            ),
            package,
            package_id=PACKAGE_ID,
        )

    # 5. Citation overflow rejected at claim model boundary (max 5 evidence_ids).
    with pytest.raises(ValidationError):
        ChiefOfStaffClaim(
            claim_id="c5",
            claim_type=ChiefOfStaffClaimType.DETERMINISTIC_FINDING,
            text="Too many cites",
            support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
            authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
            temporal_cutoff=AS_OF,
            evidence_ids=graph_ids,
            ordering_index=0,
        )

    # 6. Ineligible decision option.
    with pytest.raises(UnsupportedClaimError):
        validate_brief_grounding(
            _brief_from_claim(
                ChiefOfStaffClaim(
                    claim_id="c6",
                    claim_type=ChiefOfStaffClaimType.ADVISORY_OPTION,
                    text="Punitive option",
                    support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                    authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                    temporal_cutoff=AS_OF,
                    evidence_ids=["pkg"],
                    semantic_metadata={
                        "option_type": DecisionOptionType.REVIEW_CAPACITY_PLAN.value
                    },
                    ordering_index=0,
                ),
                [
                    ChiefOfStaffCitation(
                        citation_id="cit6",
                        claim_id="c6",
                        evidence_id="pkg",
                        evidence_type=EvidenceEntryType.PACKAGE_METADATA,
                        package_id=PACKAGE_ID,
                        ordering_index=0,
                    )
                ],
                options=[DecisionOptionType.REVIEW_CAPACITY_PLAN],
            ),
            package,
            package_id=PACKAGE_ID,
        )

    # 7. Wrong package_id.
    with pytest.raises(CitationValidationError):
        validate_brief_grounding(
            _brief_from_claim(
                ChiefOfStaffClaim(
                    claim_id="c7",
                    claim_type=ChiefOfStaffClaimType.DETERMINISTIC_FINDING,
                    text="Wrong package",
                    support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                    authorship=ChiefOfStaffClaimAuthorship.AI_AUTHORED,
                    temporal_cutoff=AS_OF,
                    evidence_ids=["graph-0"],
                    ordering_index=0,
                ),
                [
                    ChiefOfStaffCitation(
                        citation_id="cit7",
                        claim_id="c7",
                        evidence_id="graph-0",
                        evidence_type=EvidenceEntryType.GRAPH_FINDING,
                        package_id="other-package",
                        ordering_index=0,
                    )
                ],
            ),
            package,
            package_id=PACKAGE_ID,
        )


def test_fallback_determinism_across_two_assemblies(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    req = ChiefOfStaffRequest(
        tenant_id=novabank_tenant.tenant_id,
        intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
        target_type=ChiefOfStaffTargetType.PROJECT,
        target_id=target_id,
        as_of_at=AS_OF,
        requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
    )
    a = EvidenceAssemblyService(uow).assemble(novabank_tenant, req)
    b = EvidenceAssemblyService(uow).assemble(novabank_tenant, req)
    assert a.package_hash == b.package_hash
    brief_a = build_fallback_brief(a, evidence_package_hash=a.package_hash)
    brief_b = build_fallback_brief(b, evidence_package_hash=b.package_hash)
    assert [c.text for c in brief_a.claims] == [c.text for c in brief_b.claims]
    assert [c.claim_id for c in brief_a.claims] == [c.claim_id for c in brief_b.claims]
    assert compute_brief_output_hash(
        brief_a, evidence_package_hash=a.package_hash
    ) == compute_brief_output_hash(brief_b, evidence_package_hash=b.package_hash)
    # Distinct fake persistence IDs must not change semantic hash when citations
    # bind to the evidence package hash.
    assert all(c.package_id == a.package_hash for c in brief_a.citations)


def test_novabank_seed_generates_supported_intents(seeded_novabank, uow, novabank_tenant):
    result = seed_novabank_briefs(uow, novabank_tenant, as_of=AS_OF)
    briefs = result["briefs"]
    assert "delivery_status_brief" in briefs
    assert "change_since_last_review" in briefs
    assert "delivery_prediction_brief" in briefs
    assert "evidence_gap_brief" in briefs
    for key in (
        "delivery_status_brief",
        "change_since_last_review",
        "delivery_prediction_brief",
        "evidence_gap_brief",
    ):
        assert briefs[key]["brief_id"]
        assert briefs[key]["run_id"]
        assert briefs[key]["evidence_hash"]
        assert briefs[key]["output_hash"]
    assert briefs["delivery_prediction_brief"].get("probability") is None
    assert any("synthetic" in lim.lower() or "demo" in lim.lower() for lim in result["limitations"])


def test_compare_briefs_requires_same_target(seeded_novabank, uow, novabank_tenant):
    projects = uow.initiatives_projects.list_projects(novabank_tenant, limit=5, offset=0)
    assert len(projects.items) >= 2
    service = ChiefOfStaffService(uow)
    a = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=projects.items[0].enterprise_project_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    b = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=projects.items[1].enterprise_project_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    with pytest.raises(EnterpriseValidationError):
        service.compare_briefs(novabank_tenant, a.brief.brief_id, b.brief.brief_id)
