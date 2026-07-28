"""Azure DevOps package — staged readiness only."""

from app.connectors.azure_devops.descriptor import (
    AzureDevOpsStubConnector,
    azure_devops_descriptor,
)

__all__ = ["AzureDevOpsStubConnector", "azure_devops_descriptor"]
