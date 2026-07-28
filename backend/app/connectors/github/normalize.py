"""GitHub record normalization — deterministic IDs, no emails, snapshot semantics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.connectors.errors import ConnectorError
from app.connectors.protocol import NormalizedConnectorEvent
from app.domain.enterprise_enums import (
    ConnectorErrorCategory,
    DataSourceType,
    PermissionClassification,
)
from app.domain.enterprise_identifiers import build_entity_id
from app.services.persistence.snapshot_service import snapshot_hash

_MAX_PAYLOAD_CHARS = 16_384
_EMAIL_KEYS = frozenset({"email", "user_email", "author_email", "committer_email"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ConnectorError(
            ConnectorErrorCategory.NORMALIZATION_FAILED,
            f"Invalid GitHub timestamp: {value}",
            retryable=False,
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _strip_emails(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _EMAIL_KEYS:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_emails(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _strip_emails(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def _actor_login(user: Any) -> str | None:
    if isinstance(user, dict):
        login = user.get("login")
        if isinstance(login, str) and login:
            return login[:128]
        node_id = user.get("node_id") or user.get("id")
        if node_id is not None:
            return str(node_id)[:128]
    return None


def _bounded_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.persistence.snapshot_service import canonical_json

    encoded = canonical_json(payload)
    if len(encoded) > _MAX_PAYLOAD_CHARS:
        raise ConnectorError(
            ConnectorErrorCategory.PAYLOAD_TOO_LARGE,
            "Normalized payload exceeds size bound",
            retryable=False,
        )
    return payload


def _map_pr_state(raw: dict[str, Any]) -> str:
    if raw.get("merged_at") or raw.get("merged"):
        return "merged"
    state = str(raw.get("state") or "open").lower()
    if state == "closed":
        return "closed"
    return "open"


def _map_issue_state(raw: dict[str, Any]) -> str:
    state = str(raw.get("state") or "open").lower()
    return "done" if state == "closed" else "todo"


def _map_visibility(raw: dict[str, Any]) -> str:
    if raw.get("private") is True:
        return "private"
    visibility = str(raw.get("visibility") or "public").lower()
    if visibility in {"private", "internal", "public"}:
        return visibility
    return "public"


def normalize_repository(
    *,
    tenant_id: str,
    data_source_id: str,
    raw: dict[str, Any],
    observed_at: datetime | None = None,
) -> NormalizedConnectorEvent:
    try:
        repo_id = str(raw["id"])
        full_name = str(
            raw.get("full_name") or f"{raw.get('owner', {}).get('login')}/{raw.get('name')}"
        )
        name = str(raw.get("name") or full_name.split("/")[-1])[:128]
        updated = (
            parse_github_datetime(raw.get("updated_at"))
            or parse_github_datetime(raw.get("pushed_at"))
            or _utcnow()
        )
        created = parse_github_datetime(raw.get("created_at"))
        payload = _bounded_payload(
            _strip_emails(
                {
                    "provider": "github",
                    "external_id": repo_id,
                    "full_name": full_name[:256],
                    "name": name,
                    "default_branch": (
                        str(raw["default_branch"])[:128] if raw.get("default_branch") else None
                    ),
                    "visibility": _map_visibility(raw),
                    "state": "archived" if raw.get("archived") else "active",
                    "source_created_at": created.isoformat() if created else None,
                    "source_updated_at": updated.isoformat(),
                    "html_url": str(raw.get("html_url") or "")[:512] or None,
                    "source_visibility": raw.get("visibility"),
                    "source_private": raw.get("private"),
                }
            )
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ConnectorError(
            ConnectorErrorCategory.NORMALIZATION_FAILED,
            f"Repository normalization failed: {exc}",
            retryable=False,
        ) from exc

    payload_hash = snapshot_hash(payload)
    observed = observed_at or _utcnow()
    event_type = "github.repository.snapshot"
    return NormalizedConnectorEvent(
        normalized_event_id=build_entity_id(
            "nev", tenant_id, data_source_id, event_type, repo_id, payload_hash
        ),
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        connector_type=DataSourceType.GITHUB,
        stream_name="repository",
        source_record_id=f"github:repo:{repo_id}",
        source_record_version=updated.isoformat(),
        event_type=event_type,
        subject_type="repository",
        subject_external_id=full_name[:256],
        event_time=updated,
        observed_at=observed,
        normalized_at=_utcnow(),
        permission_classification=(
            PermissionClassification.PUBLIC
            if payload["visibility"] == "public"
            else PermissionClassification.INTERNAL
        ),
        payload=payload,
        payload_hash=payload_hash,
        checkpoint_position=f"{updated.isoformat()}|{repo_id}",
        provider_metadata={"github_node_id": raw.get("node_id")},
    )


def normalize_pull_request(
    *,
    tenant_id: str,
    data_source_id: str,
    raw: dict[str, Any],
    observed_at: datetime | None = None,
) -> NormalizedConnectorEvent:
    try:
        pr_id = str(raw["id"])
        number = int(raw["number"])
        updated = parse_github_datetime(raw.get("updated_at")) or _utcnow()
        created = parse_github_datetime(raw.get("created_at"))
        closed = parse_github_datetime(raw.get("closed_at"))
        merged = parse_github_datetime(raw.get("merged_at"))
        title = str(raw.get("title") or f"PR #{number}")[:512]
        payload = _bounded_payload(
            _strip_emails(
                {
                    "provider": "github",
                    "external_id": pr_id,
                    "number": number,
                    "title": title,
                    "state": _map_pr_state(raw),
                    "draft": bool(raw.get("draft", False)),
                    "author_external_id": _actor_login(raw.get("user")),
                    "created_at_source": created.isoformat() if created else None,
                    "updated_at_source": updated.isoformat(),
                    "closed_at_source": closed.isoformat() if closed else None,
                    "merged_at_source": merged.isoformat() if merged else None,
                    "additions": raw.get("additions"),
                    "deletions": raw.get("deletions"),
                    "changed_files": raw.get("changed_files"),
                    "source_state": raw.get("state"),
                    "html_url": str(raw.get("html_url") or "")[:512] or None,
                    "base_ref": (raw.get("base") or {}).get("ref")
                    if isinstance(raw.get("base"), dict)
                    else None,
                    "head_ref": (raw.get("head") or {}).get("ref")
                    if isinstance(raw.get("head"), dict)
                    else None,
                }
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorError(
            ConnectorErrorCategory.NORMALIZATION_FAILED,
            f"Pull request normalization failed: {exc}",
            retryable=False,
        ) from exc

    payload_hash = snapshot_hash(payload)
    observed = observed_at or _utcnow()
    event_type = "github.pull_request.snapshot"
    return NormalizedConnectorEvent(
        normalized_event_id=build_entity_id(
            "nev", tenant_id, data_source_id, event_type, pr_id, payload_hash
        ),
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        connector_type=DataSourceType.GITHUB,
        stream_name="pull_requests",
        source_record_id=f"github:pr:{pr_id}",
        source_record_version=updated.isoformat(),
        event_type=event_type,
        subject_type="pull_request",
        subject_external_id=pr_id,
        event_time=updated,
        observed_at=observed,
        normalized_at=_utcnow(),
        permission_classification=PermissionClassification.INTERNAL,
        payload=payload,
        payload_hash=payload_hash,
        checkpoint_position=f"{updated.isoformat()}|{pr_id}",
        provider_metadata={"github_node_id": raw.get("node_id"), "number": number},
    )


def normalize_pull_request_review(
    *,
    tenant_id: str,
    data_source_id: str,
    raw: dict[str, Any],
    pull_request_id: str | None = None,
    observed_at: datetime | None = None,
) -> NormalizedConnectorEvent:
    try:
        review_id = str(raw["id"])
        submitted = (
            parse_github_datetime(raw.get("submitted_at"))
            or parse_github_datetime(raw.get("submitted_at"))
            or _utcnow()
        )
        pr_id = pull_request_id or str(
            (raw.get("pull_request_url") or "").rstrip("/").split("/")[-1]
            if raw.get("pull_request_url")
            else raw.get("pull_request_id") or "unknown"
        )
        state = str(raw.get("state") or "commented").lower()
        payload = _bounded_payload(
            _strip_emails(
                {
                    "provider": "github",
                    "external_id": review_id,
                    "pull_request_external_id": str(pr_id)[:128],
                    "state": state,
                    "author_external_id": _actor_login(raw.get("user")),
                    "submitted_at_source": submitted.isoformat(),
                    # Intentionally omit review body text (may contain sensitive content).
                    "has_body": bool(raw.get("body")),
                }
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorError(
            ConnectorErrorCategory.NORMALIZATION_FAILED,
            f"Review normalization failed: {exc}",
            retryable=False,
        ) from exc

    payload_hash = snapshot_hash(payload)
    observed = observed_at or _utcnow()
    event_type = "github.pull_request_review.snapshot"
    return NormalizedConnectorEvent(
        normalized_event_id=build_entity_id(
            "nev", tenant_id, data_source_id, event_type, review_id, payload_hash
        ),
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        connector_type=DataSourceType.GITHUB,
        stream_name="pull_request_reviews",
        source_record_id=f"github:pr_review:{review_id}",
        source_record_version=submitted.isoformat(),
        event_type=event_type,
        subject_type="pull_request",
        subject_external_id=str(pr_id)[:256],
        event_time=submitted,
        observed_at=observed,
        normalized_at=_utcnow(),
        permission_classification=PermissionClassification.INTERNAL,
        payload=payload,
        payload_hash=payload_hash,
        checkpoint_position=f"{submitted.isoformat()}|{review_id}",
        provider_metadata={"github_node_id": raw.get("node_id")},
    )


def normalize_issue(
    *,
    tenant_id: str,
    data_source_id: str,
    raw: dict[str, Any],
    observed_at: datetime | None = None,
) -> NormalizedConnectorEvent:
    # GitHub issue endpoints can return PRs; reject those here.
    if raw.get("pull_request") is not None:
        raise ConnectorError(
            ConnectorErrorCategory.NORMALIZATION_FAILED,
            "Pull request records must not be normalized as issues",
            retryable=False,
        )
    try:
        issue_id = str(raw["id"])
        number = int(raw["number"])
        updated = parse_github_datetime(raw.get("updated_at")) or _utcnow()
        created = parse_github_datetime(raw.get("created_at"))
        closed = parse_github_datetime(raw.get("closed_at"))
        labels = []
        for label in raw.get("labels") or []:
            if isinstance(label, dict) and label.get("name"):
                labels.append(str(label["name"])[:64])
            elif isinstance(label, str):
                labels.append(label[:64])
        payload = _bounded_payload(
            _strip_emails(
                {
                    "provider": "github",
                    "external_id": issue_id,
                    "number": number,
                    "title": str(raw.get("title") or f"Issue #{number}")[:256],
                    "state": _map_issue_state(raw),
                    "source_state": raw.get("state"),
                    "labels": labels[:50],
                    "author_external_id": _actor_login(raw.get("user")),
                    "created_at_source": created.isoformat() if created else None,
                    "updated_at_source": updated.isoformat(),
                    "closed_at_source": closed.isoformat() if closed else None,
                    "html_url": str(raw.get("html_url") or "")[:512] or None,
                }
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorError(
            ConnectorErrorCategory.NORMALIZATION_FAILED,
            f"Issue normalization failed: {exc}",
            retryable=False,
        ) from exc

    payload_hash = snapshot_hash(payload)
    observed = observed_at or _utcnow()
    event_type = "github.issue.snapshot"
    return NormalizedConnectorEvent(
        normalized_event_id=build_entity_id(
            "nev", tenant_id, data_source_id, event_type, issue_id, payload_hash
        ),
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        connector_type=DataSourceType.GITHUB,
        stream_name="issues",
        source_record_id=f"github:issue:{issue_id}",
        source_record_version=updated.isoformat(),
        event_type=event_type,
        subject_type="work_item",
        subject_external_id=issue_id,
        event_time=updated,
        observed_at=observed,
        normalized_at=_utcnow(),
        permission_classification=PermissionClassification.INTERNAL,
        payload=payload,
        payload_hash=payload_hash,
        checkpoint_position=f"{updated.isoformat()}|{issue_id}",
        provider_metadata={"github_node_id": raw.get("node_id"), "number": number},
    )


def normalize_release(
    *,
    tenant_id: str,
    data_source_id: str,
    raw: dict[str, Any],
    observed_at: datetime | None = None,
) -> NormalizedConnectorEvent:
    try:
        release_id = str(raw["id"])
        published = (
            parse_github_datetime(raw.get("published_at"))
            or parse_github_datetime(raw.get("created_at"))
            or _utcnow()
        )
        created = parse_github_datetime(raw.get("created_at"))
        payload = _bounded_payload(
            _strip_emails(
                {
                    "provider": "github",
                    "external_id": release_id,
                    "tag_name": str(raw.get("tag_name") or "")[:128],
                    "name": str(raw.get("name") or raw.get("tag_name") or release_id)[:256],
                    "draft": bool(raw.get("draft", False)),
                    "prerelease": bool(raw.get("prerelease", False)),
                    "author_external_id": _actor_login(raw.get("author")),
                    "created_at_source": created.isoformat() if created else None,
                    "published_at_source": published.isoformat(),
                    "html_url": str(raw.get("html_url") or "")[:512] or None,
                    # Releases are evidence-first; do NOT map to Deployment without deploy proof.
                    "not_a_deployment": True,
                }
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorError(
            ConnectorErrorCategory.NORMALIZATION_FAILED,
            f"Release normalization failed: {exc}",
            retryable=False,
        ) from exc

    payload_hash = snapshot_hash(payload)
    observed = observed_at or _utcnow()
    event_type = "github.release.snapshot"
    return NormalizedConnectorEvent(
        normalized_event_id=build_entity_id(
            "nev", tenant_id, data_source_id, event_type, release_id, payload_hash
        ),
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        connector_type=DataSourceType.GITHUB,
        stream_name="releases",
        source_record_id=f"github:release:{release_id}",
        source_record_version=published.isoformat(),
        event_type=event_type,
        subject_type="repository",
        subject_external_id=release_id,
        event_time=published,
        observed_at=observed,
        normalized_at=_utcnow(),
        permission_classification=PermissionClassification.PUBLIC,
        payload=payload,
        payload_hash=payload_hash,
        checkpoint_position=f"{published.isoformat()}|{release_id}",
        provider_metadata={"github_node_id": raw.get("node_id")},
    )


NORMALIZERS = {
    "repository": normalize_repository,
    "pull_requests": normalize_pull_request,
    "pull_request_reviews": normalize_pull_request_review,
    "issues": normalize_issue,
    "releases": normalize_release,
}
