"""Chief of Staff persistence orchestration service."""

from __future__ import annotations

import logging
import time

from app.db.types import new_uuid
from app.db.unit_of_work import UnitOfWork
from app.domain.chief_of_staff_constants import (
    EVIDENCE_SCHEMA_VERSION,
    FALLBACK_TEMPLATE_VERSION,
    OUTPUT_SCHEMA_VERSION,
    PROMPT_VERSION,
)
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffProviderMode,
    ChiefOfStaffReviewState,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffBriefRecord,
    ChiefOfStaffEvidencePackage,
    ChiefOfStaffRequest,
    ChiefOfStaffReview,
    GenerationOutcome,
    QualitySummary,
)
from app.domain.tenant_context import TenantContext
from app.services.chief_of_staff.canonicalization import compute_brief_output_hash
from app.services.chief_of_staff.evidence_assembly import EvidenceAssemblyService
from app.services.chief_of_staff.orchestration import ChiefOfStaffOrchestrator
from app.services.enterprise.exceptions import (
    EnterpriseValidationError,
)

logger = logging.getLogger(__name__)


class ChiefOfStaffService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        orchestrator: ChiefOfStaffOrchestrator | None = None,
    ) -> None:
        self._uow = uow
        self._assembly = EvidenceAssemblyService(uow)
        self._orchestrator = orchestrator or ChiefOfStaffOrchestrator()

    def generate(self, ctx: TenantContext, request: ChiefOfStaffRequest) -> GenerationOutcome:
        if request.tenant_id != ctx.tenant_id:
            raise EnterpriseValidationError("Request tenant does not match context")

        started = time.perf_counter()
        correlation_id = str(new_uuid())

        def _run(uow: UnitOfWork) -> GenerationOutcome:
            assembly = EvidenceAssemblyService(uow)
            package = assembly.assemble(ctx, request)
            snapshot = uow.cos_evidence_snapshots.create(
                ctx,
                target_type=package.target_type,
                target_id=package.target_id,
                intent=package.intent,
                as_of_at=package.as_of_at,
                horizon_days=package.horizon_days,
                evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
                package_hash=package.package_hash,
                package_json=package.model_dump(mode="json"),
                truncation_flags=package.truncation.model_dump(mode="json"),
            )
            outcome = self._orchestrator.generate(
                package,
                evidence_package_hash=package.package_hash,
                requested_provider=request.requested_provider,
            )
            # Semantic citations already bind to evidence_package_hash (not snapshot PK).
            brief = outcome.brief
            output_hash = compute_brief_output_hash(
                brief,
                evidence_package_hash=package.package_hash,
                fallback_template_version=outcome.fallback_template_version
                or FALLBACK_TEMPLATE_VERSION,
                output_schema_version=OUTPUT_SCHEMA_VERSION,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            run = uow.cos_runs.create(
                ctx,
                target_type=package.target_type,
                target_id=package.target_id,
                intent=package.intent,
                as_of_at=package.as_of_at,
                horizon_days=package.horizon_days,
                evidence_snapshot_id=snapshot.snapshot_id,
                prior_brief_id=request.prior_brief_id,
                requested_provider=outcome.requested_provider,
                final_provider=outcome.final_provider,
                model_deployment_id=outcome.model_deployment_id,
                prompt_version=outcome.prompt_version or PROMPT_VERSION,
                evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
                output_schema_version=OUTPUT_SCHEMA_VERSION,
                fallback_template_version=outcome.fallback_template_version
                or FALLBACK_TEMPLATE_VERSION,
                evidence_package_hash=package.package_hash,
                output_hash=output_hash,
                generation_state=outcome.generation_state,
                failure_category=outcome.failure_category,
                grounding_result=outcome.grounding_result,
                citation_result=outcome.citation_result,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                total_tokens=outcome.total_tokens,
                provider_latency_ms=outcome.provider_latency_ms,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
            )
            brief_record = uow.cos_briefs.persist_brief_bundle(
                ctx,
                run_id=run.run_id,
                evidence_snapshot_id=snapshot.snapshot_id,
                evidence_package_hash=package.package_hash,
                target_type=package.target_type,
                target_id=package.target_id,
                intent=package.intent,
                as_of_at=package.as_of_at,
                horizon_days=package.horizon_days,
                structured_brief=brief,
                output_hash=output_hash,
                output_schema_version=OUTPUT_SCHEMA_VERSION,
                generation_state=outcome.generation_state,
                final_provider=outcome.final_provider,
            )
            logger.info(
                "chief_of_staff_generated",
                extra={
                    "correlation_id": correlation_id,
                    "tenant_id": ctx.tenant_id,
                    "intent": package.intent.value,
                    "target_type": package.target_type.value,
                    "evidence_count": len(package.evidence_entries),
                    "truncated": package.truncation.any_truncated,
                    "package_hash_prefix": package.package_hash[:12],
                    "provider_requested": outcome.requested_provider.value,
                    "provider_final": outcome.final_provider.value,
                    "provider_latency_ms": outcome.provider_latency_ms,
                    "generation_state": outcome.generation_state.value,
                    "failure_category": (
                        outcome.failure_category.value if outcome.failure_category else None
                    ),
                    "grounding_result": outcome.grounding_result.value,
                    "citation_result": outcome.citation_result.value,
                    "fallback_used": outcome.final_provider
                    == ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
                    "duration_ms": duration_ms,
                    "total_tokens": outcome.total_tokens,
                },
            )
            return GenerationOutcome(
                run=run,
                brief=brief_record,
                evidence_snapshot=snapshot,
                package=package,
                structured_brief=brief,
            )

        return self._uow.execute(_run)

    def validate_brief(self, ctx: TenantContext, brief_id: str) -> dict:
        brief = self._uow.cos_briefs.require(ctx, brief_id)
        snapshot = self._uow.cos_evidence_snapshots.require(ctx, brief.evidence_snapshot_id)
        package = ChiefOfStaffEvidencePackage.model_validate(snapshot.package_json)
        from app.domain.chief_of_staff_models import ChiefOfStaffBrief
        from app.services.chief_of_staff.grounding import validate_brief_grounding
        from app.services.chief_of_staff.responsible_language import validate_responsible_language

        structured = ChiefOfStaffBrief.model_validate(brief.brief_json)
        validate_brief_grounding(structured, package, evidence_package_hash=snapshot.package_hash)
        validate_responsible_language(structured)
        return {
            "brief_id": brief.brief_id,
            "valid": True,
            "evidence_package_hash": snapshot.package_hash,
            "output_hash": brief.output_hash,
            "generation_state": brief.generation_state,
            "estimate_kind": brief.estimate_kind,
            "probability": brief.probability,
        }

    def compare_briefs(
        self, ctx: TenantContext, current_brief_id: str, prior_brief_id: str
    ) -> dict:
        current = self._uow.cos_briefs.require(ctx, current_brief_id)
        prior = self._uow.cos_briefs.require(ctx, prior_brief_id)
        if current.target_type != prior.target_type or current.target_id != prior.target_id:
            raise EnterpriseValidationError("Compared briefs must share the same tenant target")
        current_snap = self._uow.cos_evidence_snapshots.require(ctx, current.evidence_snapshot_id)
        prior_snap = self._uow.cos_evidence_snapshots.require(ctx, prior.evidence_snapshot_id)
        current_pkg = ChiefOfStaffEvidencePackage.model_validate(current_snap.package_json)
        prior_pkg = ChiefOfStaffEvidencePackage.model_validate(prior_snap.package_json)
        current_ids = {e.evidence_id for e in current_pkg.evidence_entries}
        prior_ids = {e.evidence_id for e in prior_pkg.evidence_entries}
        return {
            "current_brief_id": current.brief_id,
            "prior_brief_id": prior.brief_id,
            "additions": sorted(current_ids - prior_ids),
            "removals": sorted(prior_ids - current_ids),
            "shared": sorted(current_ids & prior_ids),
            "current_package_hash": current_snap.package_hash,
            "prior_package_hash": prior_snap.package_hash,
            "current_output_hash": current.output_hash,
            "prior_output_hash": prior.output_hash,
        }

    def append_review(
        self,
        ctx: TenantContext,
        *,
        brief_id: str,
        review_state: ChiefOfStaffReviewState | str,
        reviewer_context: str = "cli",
        notes: str = "",
    ) -> ChiefOfStaffReview:
        def _run(uow: UnitOfWork) -> ChiefOfStaffReview:
            return uow.cos_reviews.append(
                ctx,
                brief_id=brief_id,
                review_state=review_state,
                reviewer_context=reviewer_context,
                notes=notes,
            )

        return self._uow.execute(_run)

    def quality_summary(self, ctx: TenantContext) -> QualitySummary:
        return self._uow.cos_runs.quality_summary(ctx)

    def get_brief(self, ctx: TenantContext, brief_id: str) -> ChiefOfStaffBriefRecord:
        return self._uow.cos_briefs.require(ctx, brief_id)

    def evidence_summary(self, ctx: TenantContext, brief_id: str) -> dict:
        brief = self._uow.cos_briefs.require(ctx, brief_id)
        snapshot = self._uow.cos_evidence_snapshots.require(ctx, brief.evidence_snapshot_id)
        package = ChiefOfStaffEvidencePackage.model_validate(snapshot.package_json)
        return {
            "brief_id": brief.brief_id,
            "snapshot_id": snapshot.snapshot_id,
            "package_hash": snapshot.package_hash,
            "as_of_at": package.as_of_at.isoformat(),
            "intent": package.intent.value,
            "target_type": package.target_type.value,
            "target_id": package.target_id,
            "evidence_counts": {
                "total_entries": len(package.evidence_entries),
                "risks": len(package.deterministic_risks),
                "graph_findings": len(package.graph_findings),
                "signals": len(package.evidence_signals),
                "scenario_runs": len(package.scenario_runs),
                "scenario_impacts": len(package.scenario_impacts),
            },
            "truncation": package.truncation.model_dump(mode="json"),
            "freshness": package.freshness_summary.model_dump(mode="json"),
            "missing_data_warnings": package.missing_data_warnings,
            "estimate_kind": (
                package.prediction.estimate_kind.value if package.prediction else None
            ),
            "probability": package.prediction.probability if package.prediction else None,
            # No raw package JSON / secrets.
        }
