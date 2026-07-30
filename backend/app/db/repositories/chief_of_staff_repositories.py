"""Tenant-scoped repositories for AI Chief of Staff (Prompt 6)."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import chief_of_staff as orm
from app.db.types import new_uuid
from app.domain.chief_of_staff_constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffFailureCategory,
    ChiefOfStaffGenerationState,
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffReviewState,
    ChiefOfStaffTargetType,
    CitationResult,
    GroundingResult,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffBrief,
    ChiefOfStaffBriefRecord,
    ChiefOfStaffCitation,
    ChiefOfStaffClaim,
    ChiefOfStaffEvidenceSnapshotRecord,
    ChiefOfStaffReview,
    ChiefOfStaffRunRecord,
    QualitySummary,
)
from app.domain.enterprise_models import Page
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    EnterpriseConflictError,
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)

_NOT_FOUND = "Resource not found for this tenant"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_val(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _page_limit(limit: int) -> int:
    return max(1, min(limit, MAX_PAGE_SIZE))


class _CosTenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def _insert_guard(self, conflict_message: str):
        try:
            yield
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise EnterpriseConflictError(conflict_message) from exc

    def _tenant_get(self, model, pk_attr, pk: str, ctx: TenantContext):
        return self._session.scalar(
            select(model).where(pk_attr == pk, model.tenant_id == ctx.tenant_id)
        )


class CosEvidenceSnapshotRepository(_CosTenantRepository):
    def get(
        self, ctx: TenantContext, snapshot_id: str
    ) -> ChiefOfStaffEvidenceSnapshotRecord | None:
        row = self._tenant_get(
            orm.CosEvidenceSnapshot,
            orm.CosEvidenceSnapshot.snapshot_id,
            snapshot_id,
            ctx,
        )
        return (
            ChiefOfStaffEvidenceSnapshotRecord.model_validate(row, from_attributes=True)
            if row
            else None
        )

    def require(self, ctx: TenantContext, snapshot_id: str) -> ChiefOfStaffEvidenceSnapshotRecord:
        item = self.get(ctx, snapshot_id)
        if item is None:
            raise EnterpriseNotFoundError(_NOT_FOUND)
        return item

    def get_by_hash(
        self, ctx: TenantContext, package_hash: str
    ) -> ChiefOfStaffEvidenceSnapshotRecord | None:
        row = self._session.scalar(
            select(orm.CosEvidenceSnapshot).where(
                orm.CosEvidenceSnapshot.tenant_id == ctx.tenant_id,
                orm.CosEvidenceSnapshot.package_hash == package_hash,
            )
        )
        return (
            ChiefOfStaffEvidenceSnapshotRecord.model_validate(row, from_attributes=True)
            if row
            else None
        )

    def create(
        self,
        ctx: TenantContext,
        *,
        target_type: ChiefOfStaffTargetType | str,
        target_id: str,
        intent: ChiefOfStaffIntent | str,
        as_of_at: datetime,
        horizon_days: int | None,
        evidence_schema_version: str,
        package_hash: str,
        package_json: dict[str, Any],
        truncation_flags: dict[str, Any],
        snapshot_id: str | None = None,
    ) -> ChiefOfStaffEvidenceSnapshotRecord:
        existing = self.get_by_hash(ctx, package_hash)
        if existing is not None:
            # Immutable reuse of identical package — do not overwrite JSON.
            return existing
        sid = snapshot_id or str(new_uuid())
        row = orm.CosEvidenceSnapshot(
            snapshot_id=sid,
            tenant_id=ctx.tenant_id,
            target_type=_enum_val(target_type),
            target_id=target_id,
            intent=_enum_val(intent),
            as_of_at=as_of_at,
            horizon_days=horizon_days,
            evidence_schema_version=evidence_schema_version,
            package_hash=package_hash,
            package_json=package_json,
            truncation_flags=truncation_flags,
            created_at=_utcnow(),
        )
        with self._insert_guard("Evidence snapshot conflict for this tenant"):
            self._session.add(row)
        return ChiefOfStaffEvidenceSnapshotRecord.model_validate(row, from_attributes=True)


class CosRunRepository(_CosTenantRepository):
    def get(self, ctx: TenantContext, run_id: str) -> ChiefOfStaffRunRecord | None:
        row = self._tenant_get(orm.CosRun, orm.CosRun.run_id, run_id, ctx)
        return ChiefOfStaffRunRecord.model_validate(row, from_attributes=True) if row else None

    def require(self, ctx: TenantContext, run_id: str) -> ChiefOfStaffRunRecord:
        item = self.get(ctx, run_id)
        if item is None:
            raise EnterpriseNotFoundError(_NOT_FOUND)
        return item

    def create(self, ctx: TenantContext, **fields: Any) -> ChiefOfStaffRunRecord:
        run_id = fields.pop("run_id", None) or str(new_uuid())
        row = orm.CosRun(
            run_id=run_id,
            tenant_id=ctx.tenant_id,
            target_type=_enum_val(fields["target_type"]),
            target_id=fields["target_id"],
            intent=_enum_val(fields["intent"]),
            as_of_at=fields["as_of_at"],
            horizon_days=fields.get("horizon_days"),
            evidence_snapshot_id=fields["evidence_snapshot_id"],
            prior_brief_id=fields.get("prior_brief_id"),
            requested_provider=_enum_val(fields["requested_provider"]),
            final_provider=_enum_val(fields["final_provider"]),
            model_deployment_id=fields.get("model_deployment_id"),
            prompt_version=fields["prompt_version"],
            evidence_schema_version=fields["evidence_schema_version"],
            output_schema_version=fields["output_schema_version"],
            fallback_template_version=fields["fallback_template_version"],
            evidence_package_hash=fields["evidence_package_hash"],
            output_hash=fields.get("output_hash"),
            generation_state=_enum_val(fields["generation_state"]),
            failure_category=_enum_val(fields["failure_category"])
            if fields.get("failure_category")
            else None,
            grounding_result=_enum_val(fields["grounding_result"])
            if fields.get("grounding_result")
            else None,
            citation_result=_enum_val(fields["citation_result"])
            if fields.get("citation_result")
            else None,
            input_tokens=fields.get("input_tokens"),
            output_tokens=fields.get("output_tokens"),
            total_tokens=fields.get("total_tokens"),
            provider_latency_ms=fields.get("provider_latency_ms"),
            duration_ms=fields.get("duration_ms"),
            correlation_id=fields.get("correlation_id") or run_id,
            created_at=_utcnow(),
        )
        with self._insert_guard("Chief of Staff run conflict for this tenant"):
            self._session.add(row)
        return ChiefOfStaffRunRecord.model_validate(row, from_attributes=True)

    def list(
        self,
        ctx: TenantContext,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        target_type: str | None = None,
        target_id: str | None = None,
        intent: str | None = None,
        generation_state: str | None = None,
    ) -> Page[ChiefOfStaffRunRecord]:
        normalized_limit = _page_limit(limit)
        normalized_offset = max(0, offset)
        filters = [orm.CosRun.tenant_id == ctx.tenant_id]
        if target_type:
            filters.append(orm.CosRun.target_type == target_type)
        if target_id:
            filters.append(orm.CosRun.target_id == target_id)
        if intent:
            filters.append(orm.CosRun.intent == intent)
        if generation_state:
            filters.append(orm.CosRun.generation_state == generation_state)
        count_q = select(func.count()).select_from(orm.CosRun).where(*filters)
        total = int(self._session.scalar(count_q) or 0)
        query: Select = (
            select(orm.CosRun)
            .where(*filters)
            .order_by(orm.CosRun.created_at.desc(), orm.CosRun.run_id.asc())
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        rows = self._session.scalars(query).all()
        return Page[ChiefOfStaffRunRecord](
            items=[ChiefOfStaffRunRecord.model_validate(r, from_attributes=True) for r in rows],
            total=total,
            limit=normalized_limit,
            offset=normalized_offset,
        )

    def quality_summary(self, ctx: TenantContext) -> QualitySummary:
        rows = self._session.scalars(
            select(orm.CosRun).where(orm.CosRun.tenant_id == ctx.tenant_id)
        ).all()
        total = len(rows)
        generated = sum(
            1 for r in rows if r.generation_state == ChiefOfStaffGenerationState.GENERATED.value
        )
        fallback = sum(
            1
            for r in rows
            if r.generation_state == ChiefOfStaffGenerationState.FALLBACK_GENERATED.value
        )
        failed = sum(
            1 for r in rows if r.generation_state == ChiefOfStaffGenerationState.FAILED.value
        )
        rejected = sum(
            1 for r in rows if r.generation_state == ChiefOfStaffGenerationState.REJECTED.value
        )
        categories: dict[str, int] = {}
        grounding_failures = 0
        citation_failures = 0
        unsupported = 0
        injection = 0
        latencies: list[int] = []
        token_sum = 0
        has_tokens = False
        for r in rows:
            if r.failure_category:
                categories[r.failure_category] = categories.get(r.failure_category, 0) + 1
            if r.grounding_result == GroundingResult.FAILED.value:
                grounding_failures += 1
            if r.citation_result == CitationResult.FAILED.value:
                citation_failures += 1
            if r.failure_category == ChiefOfStaffFailureCategory.UNSUPPORTED_CLAIM_DETECTED.value:
                unsupported += 1
            if r.failure_category == ChiefOfStaffFailureCategory.PROMPT_INJECTION_DETECTED.value:
                injection += 1
            if r.provider_latency_ms is not None:
                latencies.append(int(r.provider_latency_ms))
            if r.total_tokens is not None:
                token_sum += int(r.total_tokens)
                has_tokens = True
        return QualitySummary(
            tenant_id=ctx.tenant_id,
            total_runs=total,
            generated_count=generated,
            fallback_count=fallback,
            fallback_rate=(fallback / total) if total else 0.0,
            failed_count=failed,
            rejected_count=rejected,
            failure_categories=dict(sorted(categories.items())),
            grounding_failures=grounding_failures,
            citation_failures=citation_failures,
            unsupported_claim_detections=unsupported,
            prompt_injection_detections=injection,
            provider_latency_ms_avg=(sum(latencies) / len(latencies)) if latencies else None,
            provider_latency_ms_max=max(latencies) if latencies else None,
            total_tokens_sum=token_sum if has_tokens else None,
        )


class CosBriefRepository(_CosTenantRepository):
    def get(self, ctx: TenantContext, brief_id: str) -> ChiefOfStaffBriefRecord | None:
        row = self._tenant_get(orm.CosBrief, orm.CosBrief.brief_id, brief_id, ctx)
        return ChiefOfStaffBriefRecord.model_validate(row, from_attributes=True) if row else None

    def require(self, ctx: TenantContext, brief_id: str) -> ChiefOfStaffBriefRecord:
        item = self.get(ctx, brief_id)
        if item is None:
            raise EnterpriseNotFoundError(_NOT_FOUND)
        return item

    def list(
        self,
        ctx: TenantContext,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        target_type: str | None = None,
        target_id: str | None = None,
        intent: str | None = None,
    ) -> Page[ChiefOfStaffBriefRecord]:
        normalized_limit = _page_limit(limit)
        normalized_offset = max(0, offset)
        filters = [orm.CosBrief.tenant_id == ctx.tenant_id]
        if target_type:
            filters.append(orm.CosBrief.target_type == target_type)
        if target_id:
            filters.append(orm.CosBrief.target_id == target_id)
        if intent:
            filters.append(orm.CosBrief.intent == intent)
        total = int(
            self._session.scalar(select(func.count()).select_from(orm.CosBrief).where(*filters))
            or 0
        )
        rows = self._session.scalars(
            select(orm.CosBrief)
            .where(*filters)
            .order_by(orm.CosBrief.created_at.desc(), orm.CosBrief.brief_id.asc())
            .limit(normalized_limit)
            .offset(normalized_offset)
        ).all()
        return Page[ChiefOfStaffBriefRecord](
            items=[ChiefOfStaffBriefRecord.model_validate(r, from_attributes=True) for r in rows],
            total=total,
            limit=normalized_limit,
            offset=normalized_offset,
        )

    def persist_brief_bundle(
        self,
        ctx: TenantContext,
        *,
        run_id: str,
        evidence_snapshot_id: str,
        evidence_package_hash: str,
        target_type: ChiefOfStaffTargetType | str,
        target_id: str,
        intent: ChiefOfStaffIntent | str,
        as_of_at: datetime,
        horizon_days: int | None,
        structured_brief: ChiefOfStaffBrief,
        output_hash: str,
        output_schema_version: str,
        generation_state: ChiefOfStaffGenerationState | str,
        final_provider: ChiefOfStaffProviderMode | str,
        brief_id: str | None = None,
    ) -> ChiefOfStaffBriefRecord:
        bid = brief_id or str(new_uuid())
        brief_json = structured_brief.model_dump(mode="json")
        estimate_kind = (
            _enum_val(structured_brief.estimate_kind) if structured_brief.estimate_kind else None
        )
        row = orm.CosBrief(
            brief_id=bid,
            tenant_id=ctx.tenant_id,
            run_id=run_id,
            evidence_snapshot_id=evidence_snapshot_id,
            target_type=_enum_val(target_type),
            target_id=target_id,
            intent=_enum_val(intent),
            as_of_at=as_of_at,
            horizon_days=horizon_days,
            brief_json=brief_json,
            output_hash=output_hash,
            output_schema_version=output_schema_version,
            generation_state=_enum_val(generation_state),
            final_provider=_enum_val(final_provider),
            estimate_kind=estimate_kind,
            probability=structured_brief.probability,
            created_at=_utcnow(),
        )
        with self._insert_guard("Chief of Staff brief conflict for this tenant"):
            self._session.add(row)

        for claim in sorted(structured_brief.claims, key=lambda c: c.ordering_index):
            persisted_claim_id = f"{bid}:{claim.claim_id}"
            claim_row = orm.CosClaim(
                claim_id=persisted_claim_id,
                tenant_id=ctx.tenant_id,
                brief_id=bid,
                claim_type=_enum_val(claim.claim_type),
                text=claim.text,
                support_status=_enum_val(claim.support_status),
                authorship=_enum_val(claim.authorship),
                temporal_cutoff=claim.temporal_cutoff,
                evidence_ids=list(claim.evidence_ids),
                semantic_metadata={
                    **dict(claim.semantic_metadata or {}),
                    "logical_claim_id": claim.claim_id,
                },
                ordering_index=claim.ordering_index,
                created_at=_utcnow(),
            )
            self._session.add(claim_row)

        self._session.flush()

        for citation in sorted(
            structured_brief.citations, key=lambda c: (c.claim_id, c.ordering_index)
        ):
            # Semantic citation.package_id is the content-canonical evidence hash.
            if citation.package_id != evidence_package_hash:
                raise EnterpriseValidationError(
                    "Citation package_id must match evidence package hash"
                )
            persisted_claim_id = f"{bid}:{citation.claim_id}"
            persisted_citation_id = f"{bid}:{citation.citation_id}"
            cit_row = orm.CosCitation(
                citation_id=persisted_citation_id,
                tenant_id=ctx.tenant_id,
                brief_id=bid,
                claim_id=persisted_claim_id,
                evidence_id=citation.evidence_id,
                evidence_type=_enum_val(citation.evidence_type),
                # Persistence FK to snapshot; semantic hash remains in brief_json.
                package_id=evidence_snapshot_id,
                ordering_index=citation.ordering_index,
                created_at=_utcnow(),
            )
            self._session.add(cit_row)

        with self._insert_guard("Chief of Staff citation/claim conflict for this tenant"):
            self._session.flush()

        return ChiefOfStaffBriefRecord.model_validate(row, from_attributes=True)

    def list_claims(self, ctx: TenantContext, brief_id: str) -> list[ChiefOfStaffClaim]:
        self.require(ctx, brief_id)
        rows = self._session.scalars(
            select(orm.CosClaim)
            .where(
                orm.CosClaim.tenant_id == ctx.tenant_id,
                orm.CosClaim.brief_id == brief_id,
            )
            .order_by(orm.CosClaim.ordering_index.asc(), orm.CosClaim.claim_id.asc())
        ).all()
        return [
            ChiefOfStaffClaim(
                claim_id=(r.semantic_metadata or {}).get("logical_claim_id")
                or r.claim_id.split(":", 1)[-1],
                claim_type=r.claim_type,
                text=r.text,
                support_status=r.support_status,
                authorship=r.authorship,
                temporal_cutoff=r.temporal_cutoff,
                evidence_ids=list(r.evidence_ids or []),
                semantic_metadata={
                    k: v
                    for k, v in dict(r.semantic_metadata or {}).items()
                    if k != "logical_claim_id"
                },
                ordering_index=r.ordering_index,
            )
            for r in rows
        ]

    def list_citations(self, ctx: TenantContext, brief_id: str) -> list[ChiefOfStaffCitation]:
        brief = self.require(ctx, brief_id)
        snapshot = self._session.scalar(
            select(orm.CosEvidenceSnapshot).where(
                orm.CosEvidenceSnapshot.tenant_id == ctx.tenant_id,
                orm.CosEvidenceSnapshot.snapshot_id == brief.evidence_snapshot_id,
            )
        )
        semantic_package_id = (
            snapshot.package_hash if snapshot is not None else brief.evidence_snapshot_id
        )
        rows = self._session.scalars(
            select(orm.CosCitation)
            .where(
                orm.CosCitation.tenant_id == ctx.tenant_id,
                orm.CosCitation.brief_id == brief_id,
            )
            .order_by(
                orm.CosCitation.claim_id.asc(),
                orm.CosCitation.ordering_index.asc(),
                orm.CosCitation.citation_id.asc(),
            )
        ).all()
        return [
            ChiefOfStaffCitation(
                citation_id=r.citation_id.split(":", 1)[-1]
                if ":" in r.citation_id
                else r.citation_id,
                claim_id=(r.claim_id.split(":", 1)[-1] if ":" in r.claim_id else r.claim_id),
                evidence_id=r.evidence_id,
                evidence_type=r.evidence_type,
                # API returns content-canonical hash, not the snapshot FK.
                package_id=semantic_package_id,
                ordering_index=r.ordering_index,
            )
            for r in rows
        ]

    def get_claim(self, ctx: TenantContext, claim_id: str) -> ChiefOfStaffClaim | None:
        row = self._tenant_get(orm.CosClaim, orm.CosClaim.claim_id, claim_id, ctx)
        if row is None:
            return None
        return ChiefOfStaffClaim(
            claim_id=row.claim_id,
            claim_type=row.claim_type,
            text=row.text,
            support_status=row.support_status,
            authorship=row.authorship,
            temporal_cutoff=row.temporal_cutoff,
            evidence_ids=list(row.evidence_ids or []),
            semantic_metadata=dict(row.semantic_metadata or {}),
            ordering_index=row.ordering_index,
        )

    def get_citation(self, ctx: TenantContext, citation_id: str) -> ChiefOfStaffCitation | None:
        row = self._tenant_get(orm.CosCitation, orm.CosCitation.citation_id, citation_id, ctx)
        if row is None:
            return None
        return ChiefOfStaffCitation(
            citation_id=row.citation_id,
            claim_id=row.claim_id,
            evidence_id=row.evidence_id,
            evidence_type=row.evidence_type,
            package_id=row.package_id,
            ordering_index=row.ordering_index,
        )


class CosReviewRepository(_CosTenantRepository):
    def append(
        self,
        ctx: TenantContext,
        *,
        brief_id: str,
        review_state: ChiefOfStaffReviewState | str,
        reviewer_context: str,
        notes: str = "",
        review_id: str | None = None,
    ) -> ChiefOfStaffReview:
        brief = self._session.scalar(
            select(orm.CosBrief).where(
                orm.CosBrief.brief_id == brief_id,
                orm.CosBrief.tenant_id == ctx.tenant_id,
            )
        )
        if brief is None:
            raise EnterpriseNotFoundError(_NOT_FOUND)
        rid = review_id or str(new_uuid())
        row = orm.CosReview(
            review_id=rid,
            tenant_id=ctx.tenant_id,
            brief_id=brief_id,
            review_state=_enum_val(review_state),
            reviewer_context=(reviewer_context or "cli")[:64],
            notes=(notes or "")[:2000],
            created_at=_utcnow(),
        )
        with self._insert_guard("Chief of Staff review conflict for this tenant"):
            self._session.add(row)
        return ChiefOfStaffReview(
            review_id=row.review_id,
            tenant_id=row.tenant_id,
            brief_id=row.brief_id,
            review_state=row.review_state,
            reviewer_context=row.reviewer_context,
            notes=row.notes,
            created_at=row.created_at,
        )

    def list_for_brief(self, ctx: TenantContext, brief_id: str) -> Sequence[ChiefOfStaffReview]:
        rows = self._session.scalars(
            select(orm.CosReview)
            .where(
                orm.CosReview.tenant_id == ctx.tenant_id,
                orm.CosReview.brief_id == brief_id,
            )
            .order_by(orm.CosReview.created_at.asc(), orm.CosReview.review_id.asc())
        ).all()
        return [
            ChiefOfStaffReview(
                review_id=r.review_id,
                tenant_id=r.tenant_id,
                brief_id=r.brief_id,
                review_state=r.review_state,
                reviewer_context=r.reviewer_context,
                notes=r.notes,
                created_at=r.created_at,
            )
            for r in rows
        ]

    def get(self, ctx: TenantContext, review_id: str) -> ChiefOfStaffReview | None:
        row = self._tenant_get(orm.CosReview, orm.CosReview.review_id, review_id, ctx)
        if row is None:
            return None
        return ChiefOfStaffReview(
            review_id=row.review_id,
            tenant_id=row.tenant_id,
            brief_id=row.brief_id,
            review_state=row.review_state,
            reviewer_context=row.reviewer_context,
            notes=row.notes,
            created_at=row.created_at,
        )
