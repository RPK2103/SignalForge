"""Domain projections from normalized connector events."""

from __future__ import annotations

import logging
from datetime import datetime

from app.connectors.errors import ConnectorError
from app.connectors.protocol import NormalizedConnectorEvent
from app.db.unit_of_work import UnitOfWork
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    ConnectorErrorCategory,
    DataSourceType,
    PullRequestState,
    RepositoryState,
    RepositoryVisibility,
    WorkItemStatus,
    WorkItemType,
)
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.tenant_context import TenantContext

_logger = logging.getLogger("signalforge.connectors.projections")

# Source precedence: manual > connector. Connector must not silently overwrite manual.
PRECEDENCE_RANK = {"manual": 2, "connector": 1, "imported": 1}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


class ProjectionService:
    """Apply idempotent, tenant-qualified domain projections."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def apply(
        self,
        ctx: TenantContext,
        event: NormalizedConnectorEvent,
        *,
        evidence_signal_id: str,
    ) -> bool:
        """Return True when a projection was created or updated."""
        try:
            if event.event_type == "github.repository.snapshot":
                return self._project_repository(ctx, event, evidence_signal_id)
            if event.event_type == "github.issue.snapshot":
                return self._project_issue(ctx, event, evidence_signal_id)
            if event.event_type == "github.pull_request.snapshot":
                return self._project_pull_request(ctx, event, evidence_signal_id)
            # Reviews and releases remain evidence-first in Prompt 2.
            return False
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(
                ConnectorErrorCategory.PROJECTION_ERROR,
                f"Projection failed: {exc}",
                retryable=False,
            ) from exc

    def _project_repository(
        self, ctx: TenantContext, event: NormalizedConnectorEvent, evidence_signal_id: str
    ) -> bool:
        payload = event.payload
        external = str(payload.get("full_name") or event.subject_external_id)
        provider = DataSourceType.GITHUB
        existing = self._uow.delivery.get_repository_by_external(
            ctx, provider=provider.value, external_reference=external
        )
        visibility = RepositoryVisibility(payload.get("visibility") or "public")
        state = RepositoryState(payload.get("state") or "active")
        name = str(payload.get("name") or external.split("/")[-1])[:128]
        if existing is None:
            repo = dm.Repository(
                repository_id=build_entity_id("repo", ctx.tenant_id, provider.value, external),
                tenant_id=ctx.tenant_id,
                provider=provider,
                external_reference=external[:256],
                name=name,
                default_branch=payload.get("default_branch"),
                visibility=visibility,
                state=state,
                last_evidence_signal_id=evidence_signal_id,
                source_precedence="connector",
            )
            self._uow.delivery.add_repository(ctx, repo)
            _logger.info(
                "connector.projection.applied kind=repository tenant_id=%s repository_id=%s",
                ctx.tenant_id,
                repo.repository_id,
            )
            return True

        if PRECEDENCE_RANK.get(existing.source_precedence, 0) > PRECEDENCE_RANK.get("connector", 0):
            # Preserve manual ownership; only attach evidence pointer.
            updated = existing.model_copy(update={"last_evidence_signal_id": evidence_signal_id})
            self._uow.delivery.update_repository(ctx, updated)
            return True

        updated = existing.model_copy(
            update={
                "name": name,
                "default_branch": payload.get("default_branch") or existing.default_branch,
                "visibility": visibility,
                "state": state,
                "last_evidence_signal_id": evidence_signal_id,
                "source_precedence": "connector",
            }
        )
        self._uow.delivery.update_repository(ctx, updated)
        return True

    def _project_issue(
        self, ctx: TenantContext, event: NormalizedConnectorEvent, evidence_signal_id: str
    ) -> bool:
        payload = event.payload
        external = str(payload.get("external_id") or event.subject_external_id)
        provider = DataSourceType.GITHUB
        existing = self._uow.delivery.get_work_item_by_external(
            ctx, provider=provider.value, external_reference=external
        )
        status_raw = payload.get("state") or "todo"
        try:
            status = WorkItemStatus(status_raw)
        except ValueError:
            status = WorkItemStatus.TODO
        title = str(payload.get("title") or f"Issue {external}")[:256]
        if existing is None:
            wi = dm.WorkItem(
                work_item_id=build_entity_id("wi", ctx.tenant_id, provider.value, external),
                tenant_id=ctx.tenant_id,
                provider=provider,
                external_reference=external[:256],
                title=title,
                work_item_type=WorkItemType.STORY,
                status=status,
                source_created_at=_parse_dt(payload.get("created_at_source")),
                source_updated_at=_parse_dt(payload.get("updated_at_source")),
                completed_at=_parse_dt(payload.get("closed_at_source")),
                last_evidence_signal_id=evidence_signal_id,
                source_precedence="connector",
            )
            self._uow.delivery.add_work_item(ctx, wi)
            return True
        if PRECEDENCE_RANK.get(existing.source_precedence, 0) > PRECEDENCE_RANK.get("connector", 0):
            updated = existing.model_copy(update={"last_evidence_signal_id": evidence_signal_id})
            self._uow.delivery.update_work_item(ctx, updated)
            return True
        updated = existing.model_copy(
            update={
                "title": title,
                "status": status,
                "source_created_at": _parse_dt(payload.get("created_at_source"))
                or existing.source_created_at,
                "source_updated_at": _parse_dt(payload.get("updated_at_source"))
                or existing.source_updated_at,
                "completed_at": _parse_dt(payload.get("closed_at_source")),
                "last_evidence_signal_id": evidence_signal_id,
                "source_precedence": "connector",
            }
        )
        self._uow.delivery.update_work_item(ctx, updated)
        return True

    def _project_pull_request(
        self, ctx: TenantContext, event: NormalizedConnectorEvent, evidence_signal_id: str
    ) -> bool:
        payload = event.payload
        external = str(payload.get("external_id") or event.subject_external_id)
        provider = DataSourceType.GITHUB
        try:
            state = PullRequestState(payload.get("state") or "open")
        except ValueError:
            state = PullRequestState.OPEN
        pr = dm.PullRequest(
            pull_request_id=build_entity_id("pr", ctx.tenant_id, provider.value, external),
            tenant_id=ctx.tenant_id,
            provider=provider,
            external_id=external[:128],
            number=int(payload.get("number") or 0) or 1,
            title=str(payload.get("title") or f"PR {external}")[:512],
            state=state,
            draft=bool(payload.get("draft", False)),
            author_external_id=payload.get("author_external_id"),
            created_at_source=_parse_dt(payload.get("created_at_source")),
            updated_at_source=_parse_dt(payload.get("updated_at_source")),
            closed_at_source=_parse_dt(payload.get("closed_at_source")),
            merged_at_source=_parse_dt(payload.get("merged_at_source")),
            additions=payload.get("additions"),
            deletions=payload.get("deletions"),
            changed_files=payload.get("changed_files"),
            last_evidence_signal_id=evidence_signal_id,
            source_precedence="connector",
        )
        self._uow.pull_requests.upsert(ctx, pr)
        return True
