"""Constants for the AgentCore Runtime deployment adapter."""

from __future__ import annotations

from lfx.services.adapters.deployment.schema import DeploymentType

from langflow.services.database.models.deployment_provider_account.schemas import DeploymentProviderKey

SUPPORTED_ADAPTER_DEPLOYMENT_TYPES: frozenset[DeploymentType] = frozenset({DeploymentType.AGENT})

AGENTCORE_RUNTIME_DEPLOYMENT_ADAPTER_KEY = DeploymentProviderKey.AGENTCORE_RUNTIME.value

