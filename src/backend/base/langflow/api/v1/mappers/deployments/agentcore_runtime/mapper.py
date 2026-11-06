"""AgentCore Runtime deployment mapper implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from lfx.services.adapters.deployment.schema import BaseFlowArtifact
from lfx.services.adapters.schema import AdapterType

from langflow.api.v1.mappers.deployments.registry import register_mapper
from langflow.api.v1.mappers.deployments.watsonx_orchestrate.mapper import (
    WatsonxOrchestrateDeploymentMapper,
)
from langflow.api.v1.mappers.deployments.watsonx_orchestrate.payloads import (
    WatsonxApiProviderAccountCreate,
)
from langflow.services.adapters.deployment.agentcore_runtime.constants import (
    AGENTCORE_RUNTIME_DEPLOYMENT_ADAPTER_KEY,
)
from langflow.services.database.models.deployment_provider_account.utils import (
    check_provider_url_allowed,
    extract_tenant_from_url,
)

if TYPE_CHECKING:
    from langflow.services.database.models.deployment.model import Deployment
    from langflow.services.database.models.flow.model import Flow
    from langflow.services.database.models.flow_version.model import FlowVersion


@register_mapper(AdapterType.DEPLOYMENT, AGENTCORE_RUNTIME_DEPLOYMENT_ADAPTER_KEY)
class AgentCoreRuntimeDeploymentMapper(WatsonxOrchestrateDeploymentMapper):
    """Deployment mapper for AgentCore Runtime provider."""

    PROVIDER_LABEL = "AgentCore Runtime"

    def _validate_flow_artifacts(self, flow_artifacts: list[tuple[UUID, BaseFlowArtifact]]) -> None:
        """AgentCore Runtime accepts any Langflow flow version without wxO eligibility restrictions."""
        _ = flow_artifacts

    def _validate_create_provider_data(
        self,
        provider_data: dict[str, Any],
    ) -> tuple[WatsonxApiProviderAccountCreate, str]:
        parsed = self._parse_and_check_url(provider_data)
        tenant_id = parsed.tenant_id
        if not tenant_id:
            tenant_id = (
                extract_tenant_from_url(
                    parsed.url,
                    AGENTCORE_RUNTIME_DEPLOYMENT_ADAPTER_KEY,
                )
                or "agentcore-runtime"
            )
        return parsed, tenant_id

    def _parse_and_check_url(
        self,
        provider_data: dict[str, Any],
    ) -> WatsonxApiProviderAccountCreate:
        parsed: WatsonxApiProviderAccountCreate = self.parse_api_request_slot(
            slot=self.api_payloads.provider_account_create,
            slot_name="provider_account_create",
            raw=provider_data,
        )
        check_provider_url_allowed(parsed.url, AGENTCORE_RUNTIME_DEPLOYMENT_ADAPTER_KEY)
        return parsed

    def resolve_snapshot_update_artifact(
        self,
        *,
        flow_version: FlowVersion,
        flow_row: Flow | None,
        deployment: Deployment,
    ) -> BaseFlowArtifact:
        flow_name = (flow_row.name if flow_row else None) or f"flow-{flow_version.flow_id}"
        flow_description = (flow_row.description if flow_row else None) or ""
        provider_data = self._build_flow_tool_payload(
            project_id=deployment.project_id,
            flow_version_id=flow_version.id,
            tool_display_name=flow_name,
        )["provider_data"]
        return BaseFlowArtifact(
            id=flow_version.flow_id,
            name=flow_name,
            description=flow_description,
            data=flow_version.data or {},
            provider_data=provider_data,
        )

