"""Tenant-scoped repositories for connector checkpoints, receipts, dead letters, PRs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update

from app.db.models import enterprise as orm
from app.db.repositories.enterprise_repositories import _dump, _page, _TenantRepository, _to_dto
from app.domain import enterprise_models as dm
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    EnterpriseConflictError,
    EnterpriseNotFoundError,
)
from app.services.persistence.snapshot_service import snapshot_hash


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorCheckpointRepository(_TenantRepository):
    def get(
        self, ctx: TenantContext, *, data_source_id: str, stream_name: str
    ) -> dm.ConnectorCheckpoint | None:
        row = self._session.scalar(
            select(orm.ConnectorCheckpoint).where(
                orm.ConnectorCheckpoint.tenant_id == ctx.tenant_id,
                orm.ConnectorCheckpoint.data_source_id == data_source_id,
                orm.ConnectorCheckpoint.stream_name == stream_name,
            )
        )
        return _to_dto(dm.ConnectorCheckpoint, row) if row else None

    def list_for_source(
        self,
        ctx: TenantContext,
        *,
        data_source_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.ConnectorCheckpoint]:
        base = select(orm.ConnectorCheckpoint).where(
            orm.ConnectorCheckpoint.tenant_id == ctx.tenant_id,
            orm.ConnectorCheckpoint.data_source_id == data_source_id,
        )
        count = (
            select(func.count())
            .select_from(orm.ConnectorCheckpoint)
            .where(
                orm.ConnectorCheckpoint.tenant_id == ctx.tenant_id,
                orm.ConnectorCheckpoint.data_source_id == data_source_id,
            )
        )
        rows, total = self._paginate(
            base.order_by(orm.ConnectorCheckpoint.stream_name.asc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.ConnectorCheckpoint, rows, total, limit, offset)

    def upsert(
        self,
        ctx: TenantContext,
        checkpoint: dm.ConnectorCheckpoint,
        *,
        expected_version: int | None = None,
    ) -> dm.ConnectorCheckpoint:
        """Insert or update with atomic optimistic concurrency on version.

        Updates use ``UPDATE ... WHERE version = expected`` so a stale writer
        cannot overwrite a newer checkpoint under concurrent sessions.
        """
        self._require_ref(
            orm.DataSource,
            orm.DataSource.data_source_id,
            checkpoint.data_source_id,
            ctx,
            "data_source",
        )
        existing = self._session.scalar(
            select(orm.ConnectorCheckpoint).where(
                orm.ConnectorCheckpoint.tenant_id == ctx.tenant_id,
                orm.ConnectorCheckpoint.data_source_id == checkpoint.data_source_id,
                orm.ConnectorCheckpoint.stream_name == checkpoint.stream_name,
            )
        )
        payload = checkpoint.cursor_payload
        cursor_hash = checkpoint.cursor_hash or snapshot_hash(payload)
        if existing is None:
            to_insert = checkpoint.model_copy(
                update={"cursor_hash": cursor_hash, "version": 1, "tenant_id": ctx.tenant_id}
            )
            with self._insert_guard("Connector checkpoint already exists"):
                self._session.add(orm.ConnectorCheckpoint(**_dump(to_insert, ctx)))
            return to_insert

        if expected_version is None:
            expected_version = int(existing.version)
        elif int(existing.version) != int(expected_version):
            raise EnterpriseConflictError(
                "Connector checkpoint version conflict (stale update rejected)"
            )

        now = _utcnow()
        result = self._session.execute(
            update(orm.ConnectorCheckpoint)
            .where(
                orm.ConnectorCheckpoint.tenant_id == ctx.tenant_id,
                orm.ConnectorCheckpoint.data_source_id == checkpoint.data_source_id,
                orm.ConnectorCheckpoint.stream_name == checkpoint.stream_name,
                orm.ConnectorCheckpoint.version == expected_version,
            )
            .values(
                cursor_schema_version=checkpoint.cursor_schema_version,
                cursor_payload=payload,
                cursor_hash=cursor_hash,
                high_watermark_time=checkpoint.high_watermark_time,
                high_watermark_source_id=checkpoint.high_watermark_source_id,
                etag=checkpoint.etag,
                last_successful_run_id=checkpoint.last_successful_run_id,
                version=int(expected_version) + 1,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise EnterpriseConflictError(
                "Connector checkpoint version conflict (stale update rejected)"
            )
        self._session.expire(existing)
        refreshed = self._session.scalar(
            select(orm.ConnectorCheckpoint).where(
                orm.ConnectorCheckpoint.tenant_id == ctx.tenant_id,
                orm.ConnectorCheckpoint.data_source_id == checkpoint.data_source_id,
                orm.ConnectorCheckpoint.stream_name == checkpoint.stream_name,
            )
        )
        if refreshed is None:
            raise EnterpriseNotFoundError("Connector checkpoint not found for this tenant")
        return _to_dto(dm.ConnectorCheckpoint, refreshed)


class IngestionReceiptRepository(_TenantRepository):
    def append(
        self, ctx: TenantContext, receipt: dm.IngestionReceipt
    ) -> tuple[dm.IngestionReceipt, bool]:
        """Append observation receipt. Same-run duplicate returns existing."""
        self._require_ref(
            orm.DataSource,
            orm.DataSource.data_source_id,
            receipt.data_source_id,
            ctx,
            "data_source",
        )
        existing = self._session.scalar(
            select(orm.IngestionReceipt).where(
                orm.IngestionReceipt.tenant_id == ctx.tenant_id,
                orm.IngestionReceipt.ingestion_run_id == receipt.ingestion_run_id,
                orm.IngestionReceipt.stream_name == receipt.stream_name,
                orm.IngestionReceipt.source_record_id == receipt.source_record_id,
                orm.IngestionReceipt.payload_hash == receipt.payload_hash,
            )
        )
        if existing is not None:
            return _to_dto(dm.IngestionReceipt, existing), False
        try:
            with self._insert_guard("Ingestion receipt conflict"):
                self._session.add(orm.IngestionReceipt(**_dump(receipt, ctx)))
            return receipt, True
        except EnterpriseConflictError:
            # Race: re-read
            existing = self._session.scalar(
                select(orm.IngestionReceipt).where(
                    orm.IngestionReceipt.tenant_id == ctx.tenant_id,
                    orm.IngestionReceipt.ingestion_run_id == receipt.ingestion_run_id,
                    orm.IngestionReceipt.stream_name == receipt.stream_name,
                    orm.IngestionReceipt.source_record_id == receipt.source_record_id,
                    orm.IngestionReceipt.payload_hash == receipt.payload_hash,
                )
            )
            if existing is None:
                raise
            return _to_dto(dm.IngestionReceipt, existing), False

    def list_for_run(
        self,
        ctx: TenantContext,
        *,
        ingestion_run_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.IngestionReceipt]:
        base = select(orm.IngestionReceipt).where(
            orm.IngestionReceipt.tenant_id == ctx.tenant_id,
            orm.IngestionReceipt.ingestion_run_id == ingestion_run_id,
        )
        count = (
            select(func.count())
            .select_from(orm.IngestionReceipt)
            .where(
                orm.IngestionReceipt.tenant_id == ctx.tenant_id,
                orm.IngestionReceipt.ingestion_run_id == ingestion_run_id,
            )
        )
        rows, total = self._paginate(
            base.order_by(orm.IngestionReceipt.ingestion_receipt_id.asc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.IngestionReceipt, rows, total, limit, offset)


class IngestionDeadLetterRepository(_TenantRepository):
    def append(
        self, ctx: TenantContext, dead_letter: dm.IngestionDeadLetter
    ) -> dm.IngestionDeadLetter:
        self._require_ref(
            orm.DataSource,
            orm.DataSource.data_source_id,
            dead_letter.data_source_id,
            ctx,
            "data_source",
        )
        with self._insert_guard("Dead letter already exists"):
            self._session.add(orm.IngestionDeadLetter(**_dump(dead_letter, ctx)))
        return dead_letter

    def get(self, ctx: TenantContext, dead_letter_id: str) -> dm.IngestionDeadLetter | None:
        row = self._tenant_get(
            orm.IngestionDeadLetter, orm.IngestionDeadLetter.dead_letter_id, dead_letter_id, ctx
        )
        return _to_dto(dm.IngestionDeadLetter, row) if row else None

    def update(
        self, ctx: TenantContext, dead_letter: dm.IngestionDeadLetter
    ) -> dm.IngestionDeadLetter:
        row = self._tenant_get(
            orm.IngestionDeadLetter,
            orm.IngestionDeadLetter.dead_letter_id,
            dead_letter.dead_letter_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Dead letter not found for this tenant")
        payload = _dump(dead_letter, ctx)
        for key, value in payload.items():
            if key in {"dead_letter_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.IngestionDeadLetter, row)

    def list_for_run(
        self,
        ctx: TenantContext,
        *,
        ingestion_run_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.IngestionDeadLetter]:
        base = select(orm.IngestionDeadLetter).where(
            orm.IngestionDeadLetter.tenant_id == ctx.tenant_id,
            orm.IngestionDeadLetter.ingestion_run_id == ingestion_run_id,
        )
        count = (
            select(func.count())
            .select_from(orm.IngestionDeadLetter)
            .where(
                orm.IngestionDeadLetter.tenant_id == ctx.tenant_id,
                orm.IngestionDeadLetter.ingestion_run_id == ingestion_run_id,
            )
        )
        rows, total = self._paginate(
            base.order_by(orm.IngestionDeadLetter.dead_letter_id.asc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.IngestionDeadLetter, rows, total, limit, offset)

    def list_for_source(
        self,
        ctx: TenantContext,
        *,
        data_source_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dm.Page[dm.IngestionDeadLetter]:
        base = select(orm.IngestionDeadLetter).where(
            orm.IngestionDeadLetter.tenant_id == ctx.tenant_id,
            orm.IngestionDeadLetter.data_source_id == data_source_id,
        )
        count = (
            select(func.count())
            .select_from(orm.IngestionDeadLetter)
            .where(
                orm.IngestionDeadLetter.tenant_id == ctx.tenant_id,
                orm.IngestionDeadLetter.data_source_id == data_source_id,
            )
        )
        rows, total = self._paginate(
            base.order_by(orm.IngestionDeadLetter.dead_letter_id.asc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.IngestionDeadLetter, rows, total, limit, offset)


class PullRequestRepository(_TenantRepository):
    def add(self, ctx: TenantContext, pull_request: dm.PullRequest) -> dm.PullRequest:
        if pull_request.repository_id:
            self._require_ref(
                orm.Repository,
                orm.Repository.repository_id,
                pull_request.repository_id,
                ctx,
                "repository",
            )
        with self._insert_guard("Pull request external id already exists"):
            self._session.add(orm.PullRequest(**_dump(pull_request, ctx)))
        return pull_request

    def get(self, ctx: TenantContext, pull_request_id: str) -> dm.PullRequest | None:
        row = self._tenant_get(
            orm.PullRequest, orm.PullRequest.pull_request_id, pull_request_id, ctx
        )
        return _to_dto(dm.PullRequest, row) if row else None

    def get_by_external(
        self, ctx: TenantContext, *, provider: str, external_id: str
    ) -> dm.PullRequest | None:
        row = self._session.scalar(
            select(orm.PullRequest).where(
                orm.PullRequest.tenant_id == ctx.tenant_id,
                orm.PullRequest.provider == provider,
                orm.PullRequest.external_id == external_id,
            )
        )
        return _to_dto(dm.PullRequest, row) if row else None

    def update(self, ctx: TenantContext, pull_request: dm.PullRequest) -> dm.PullRequest:
        row = self._tenant_get(
            orm.PullRequest, orm.PullRequest.pull_request_id, pull_request.pull_request_id, ctx
        )
        if row is None:
            raise EnterpriseNotFoundError("Pull request not found for this tenant")
        payload = _dump(pull_request, ctx)
        for key, value in payload.items():
            if key in {"pull_request_id", "tenant_id", "created_at"}:
                continue
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.PullRequest, row)

    def upsert(self, ctx: TenantContext, pull_request: dm.PullRequest) -> dm.PullRequest:
        existing = self.get_by_external(
            ctx, provider=pull_request.provider.value, external_id=pull_request.external_id
        )
        if existing is None:
            try:
                return self.add(ctx, pull_request)
            except EnterpriseConflictError:
                existing = self.get_by_external(
                    ctx, provider=pull_request.provider.value, external_id=pull_request.external_id
                )
                if existing is None:
                    raise
        updated = pull_request.model_copy(update={"pull_request_id": existing.pull_request_id})
        # Precedence: never overwrite manual with connector without explicit rule.
        if existing.source_precedence == "manual" and pull_request.source_precedence == "connector":
            # Preserve manual ownership-like fields; only update evidence pointer.
            updated = existing.model_copy(
                update={"last_evidence_signal_id": pull_request.last_evidence_signal_id}
            )
        return self.update(ctx, updated)
