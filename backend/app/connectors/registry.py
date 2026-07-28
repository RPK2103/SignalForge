"""Connector registry — static registration, no dynamic plugin loading."""

from __future__ import annotations

from typing import Callable

from app.connectors.errors import ConnectorError
from app.connectors.protocol import Connector, ConnectorDescriptor
from app.domain.enterprise_enums import ConnectorErrorCategory


class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Connector]] = {}
        self._descriptors: dict[str, ConnectorDescriptor] = {}
        self._operational: dict[str, bool] = {}

    def register(
        self,
        key: str,
        factory: Callable[[], Connector],
        *,
        operational: bool = True,
        descriptor: ConnectorDescriptor | None = None,
    ) -> None:
        self._factories[key] = factory
        self._operational[key] = operational
        if descriptor is not None:
            self._descriptors[key] = descriptor
        else:
            self._descriptors[key] = factory().descriptor()

    def get(self, key: str) -> Connector:
        if key not in self._factories:
            raise ConnectorError(
                ConnectorErrorCategory.INVALID_CONFIGURATION,
                f"Unknown connector: {key}",
                retryable=False,
            )
        if not self._operational.get(key, False):
            raise ConnectorError(
                ConnectorErrorCategory.CONNECTOR_NOT_IMPLEMENTED,
                f"Connector '{key}' is staged but not implemented",
                retryable=False,
            )
        return self._factories[key]()

    def is_operational(self, key: str) -> bool:
        return bool(self._operational.get(key))

    def list_descriptors(self) -> list[ConnectorDescriptor]:
        return [self._descriptors[k] for k in sorted(self._descriptors)]

    def get_descriptor(self, key: str) -> ConnectorDescriptor | None:
        return self._descriptors.get(key)


_DEFAULT: ConnectorRegistry | None = None


def get_default_registry() -> ConnectorRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = build_default_registry()
    return _DEFAULT


def reset_default_registry() -> None:
    global _DEFAULT
    _DEFAULT = None


def build_default_registry() -> ConnectorRegistry:
    from app.connectors.azure_devops.descriptor import (
        AzureDevOpsStubConnector,
        azure_devops_descriptor,
    )
    from app.connectors.github.connector import GitHubConnector
    from app.connectors.jira.descriptor import JiraStubConnector, jira_descriptor

    registry = ConnectorRegistry()
    registry.register("github", GitHubConnector, operational=True)
    registry.register(
        "jira",
        JiraStubConnector,
        operational=False,
        descriptor=jira_descriptor(),
    )
    registry.register(
        "azure_devops",
        AzureDevOpsStubConnector,
        operational=False,
        descriptor=azure_devops_descriptor(),
    )
    return registry
