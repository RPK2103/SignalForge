"""Jira staged descriptor — configuration contract only; no HTTP."""

from __future__ import annotations

from typing import Any

from app.connectors.config import validate_connector_config
from app.connectors.errors import ConnectorError
from app.connectors.protocol import (
    ConnectorCapabilities,
    ConnectorContext,
    ConnectorDescriptor,
    ConnectorPage,
    ConnectorRequest,
    ConnectorStream,
)
from app.domain.enterprise_enums import ConnectorErrorCategory, DataSourceType


def jira_descriptor() -> ConnectorDescriptor:
    return ConnectorDescriptor(
        connector_key="jira",
        display_name="Jira",
        source_type=DataSourceType.JIRA,
        streams=[
            ConnectorStream(name="issues", display_name="Issues"),
            ConnectorStream(name="sprints", display_name="Sprints", supports_incremental=False),
        ],
        capabilities=ConnectorCapabilities(
            supports_initial_sync=False,
            supports_incremental_sync=False,
            supports_unauthenticated=False,
            requires_credential_reference=True,
            supports_webhooks=False,
            operational=False,
        ),
        documentation_notes="Staged configuration contract only. HTTP connector not implemented.",
    )


class JiraStubConnector:
    def descriptor(self) -> ConnectorDescriptor:
        return jira_descriptor()

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return validate_connector_config("jira", config)

    def list_streams(self, config: dict[str, Any]) -> list[ConnectorStream]:
        self.validate_config(config)
        return list(self.descriptor().streams)

    def fetch_page(
        self,
        context: ConnectorContext,
        config: dict[str, Any],
        request: ConnectorRequest,
    ) -> ConnectorPage:
        raise ConnectorError(
            ConnectorErrorCategory.CONNECTOR_NOT_IMPLEMENTED,
            "Jira connector is not implemented",
            retryable=False,
        )
