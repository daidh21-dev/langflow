"""Register the AgentCore Runtime deployment adapter."""

from lfx.services.adapters.registry import register_adapter
from lfx.services.adapters.schema import AdapterType

from langflow.services.adapters.deployment.agentcore_runtime.constants import (
    AGENTCORE_RUNTIME_DEPLOYMENT_ADAPTER_KEY,
)
from langflow.services.adapters.deployment.agentcore_runtime.service import (
    AgentCoreRuntimeDeploymentService,
)

register_adapter(
    AdapterType.DEPLOYMENT,
    AGENTCORE_RUNTIME_DEPLOYMENT_ADAPTER_KEY,
)(AgentCoreRuntimeDeploymentService)

