"""Non-secret connector configuration validation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.connectors.errors import ConnectorError
from app.domain.enterprise_enums import ConnectorErrorCategory
from app.services.persistence.snapshot_service import snapshot_hash

_SECRET_KEY_PATTERN = re.compile(
    r"(token|password|secret|api[_-]?key|authorization|private[_-]?key|connection[_-]?string)",
    re.IGNORECASE,
)

_MAX_CONFIG_CHARS = 8_192
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

GITHUB_STREAMS = frozenset(
    {"repository", "pull_requests", "pull_request_reviews", "issues", "releases"}
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GitHubConnectorConfig(_Strict):
    owner: str = Field(min_length=1, max_length=39)
    repository: str = Field(min_length=1, max_length=100)
    enabled_streams: list[str] = Field(
        default_factory=lambda: [
            "repository",
            "pull_requests",
            "pull_request_reviews",
            "issues",
            "releases",
        ]
    )
    page_size: int = Field(default=30, ge=1, le=100)
    overlap_seconds: int = Field(default=60, ge=0, le=86_400)
    maximum_pages: int | None = Field(default=None, ge=1, le=100)

    @field_validator("owner")
    @classmethod
    def _owner(cls, value: str) -> str:
        if not _OWNER_RE.match(value):
            raise ValueError("invalid GitHub owner")
        return value

    @field_validator("repository")
    @classmethod
    def _repo(cls, value: str) -> str:
        if value in {".", ".."} or not _REPO_RE.match(value):
            raise ValueError("invalid GitHub repository name")
        return value

    @field_validator("enabled_streams")
    @classmethod
    def _streams(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("enabled_streams must not be empty")
        unknown = set(value) - GITHUB_STREAMS
        if unknown:
            raise ValueError(f"unknown streams: {sorted(unknown)}")
        # Preserve order, dedupe
        seen: list[str] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return seen


class JiraConnectorConfig(_Strict):
    """Staged non-secret Jira config — HTTP connector not implemented."""

    base_site: str = Field(min_length=1, max_length=128)
    project_key: str = Field(min_length=1, max_length=32)
    enabled_streams: list[str] = Field(default_factory=lambda: ["issues"])
    page_size: int = Field(default=50, ge=1, le=100)


class AzureDevOpsConnectorConfig(_Strict):
    """Staged non-secret Azure DevOps config — HTTP connector not implemented."""

    organization: str = Field(min_length=1, max_length=128)
    project: str = Field(min_length=1, max_length=128)
    enabled_streams: list[str] = Field(default_factory=lambda: ["work_items", "pull_requests"])
    page_size: int = Field(default=50, ge=1, le=100)


def reject_secret_keys(config: dict[str, Any]) -> None:
    """Reject keys that resemble secrets — recursive; do not rely on docs alone."""

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if _SECRET_KEY_PATTERN.search(str(key)):
                    raise ConnectorError(
                        ConnectorErrorCategory.INVALID_CONFIGURATION,
                        f"Configuration key '{key}' resembles a secret and is forbidden",
                        retryable=False,
                    )
                _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(config)


def validate_connector_config(source_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize non-secret connector configuration."""
    if not isinstance(config, dict):
        raise ConnectorError(
            ConnectorErrorCategory.INVALID_CONFIGURATION,
            "connector_config must be an object",
            retryable=False,
        )
    reject_secret_keys(config)
    # Size bound on canonical representation
    from app.services.persistence.snapshot_service import canonical_json

    encoded = canonical_json(config)
    if len(encoded) > _MAX_CONFIG_CHARS:
        raise ConnectorError(
            ConnectorErrorCategory.PAYLOAD_TOO_LARGE,
            "connector_config exceeds size bound",
            retryable=False,
        )
    try:
        if source_type == "github":
            model = GitHubConnectorConfig.model_validate(config)
        elif source_type == "jira":
            model = JiraConnectorConfig.model_validate(config)
        elif source_type == "azure_devops":
            model = AzureDevOpsConnectorConfig.model_validate(config)
        else:
            raise ConnectorError(
                ConnectorErrorCategory.INVALID_CONFIGURATION,
                f"Unsupported source_type for connector_config: {source_type}",
                retryable=False,
            )
    except ConnectorError:
        raise
    except Exception as exc:
        raise ConnectorError(
            ConnectorErrorCategory.INVALID_CONFIGURATION,
            f"Invalid connector configuration: {exc}",
            retryable=False,
        ) from exc
    return model.model_dump(mode="json")


def hash_connector_config(config: dict[str, Any]) -> str:
    return snapshot_hash(config)
