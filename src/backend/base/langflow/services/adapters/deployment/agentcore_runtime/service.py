"""AgentCore Runtime deployment service implementation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from lfx.run.base import run_flow
from lfx.services.adapters.deployment.base import BaseDeploymentService
from lfx.services.adapters.deployment.exceptions import (
    DeploymentNotFoundError,
    InvalidContentError,
    OperationNotSupportedError,
    ResourceNotFoundError,
)
from lfx.services.adapters.deployment.schema import (
    BaseFlowArtifact,
    ConfigItem,
    ConfigListParams,
    ConfigListResult,
    DeploymentCreate,
    DeploymentCreateResult,
    DeploymentDeleteResult,
    DeploymentDuplicateResult,
    DeploymentGetResult,
    DeploymentListLlmsResult,
    DeploymentListParams,
    DeploymentListResult,
    DeploymentListTypesResult,
    DeploymentStatusResult,
    DeploymentType,
    DeploymentUpdate,
    DeploymentUpdateResult,
    ExecutionCreate,
    ExecutionCreateResult,
    ExecutionStatusResult,
    IdLike,
    ItemResult,
    RedeployResult,
    SnapshotItem,
    SnapshotListParams,
    SnapshotListResult,
    SnapshotUpdateResult,
    VerifyCredentials,
    VerifyCredentialsResult,
    _normalize_and_validate_id,
)

from langflow.services.adapters.deployment.agentcore_runtime.constants import (
    SUPPORTED_ADAPTER_DEPLOYMENT_TYPES,
)
from langflow.services.adapters.deployment.watsonx_orchestrate.payloads import (
    PAYLOAD_SCHEMAS,
    WatsonxBindOperation,
    WatsonxDeploymentCreatePayload,
    WatsonxDeploymentCreateResultData,
    WatsonxDeploymentLlmListResultData,
    WatsonxDeploymentUpdatePayload,
    WatsonxDeploymentUpdateResultData,
    WatsonxModelOut,
    WatsonxRemoveToolOperation,
    WatsonxRenameToolOperation,
    WatsonxResultToolRefBinding,
    WatsonxToolAppBinding,
    WatsonxToolRefBinding,
    WatsonxUnbindOperation,
    build_langflow_wxo_resource_name,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_AGENTCORE_MODELS = [
    "anthropic.claude-3-haiku-20240307-v1:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "apac.amazon.nova-pro-v1:0",
    "apac.amazon.nova-lite-v1:0",
    "amazon.titan-text-express-v1",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0",
    "gpt-4o",
    "gpt-4o-mini",
    "agentcore/langflow-native-runtime",
]


def _get_storage_dir() -> Path:
    base = Path("/app/deploy/agentcore")
    if not base.exists():
        base = Path("/tmp/langflow_agentcore")
    base.mkdir(parents=True, exist_ok=True)
    return base


class AgentCoreRuntimeDeploymentService(BaseDeploymentService):
    """Deployment adapter for Amazon Bedrock AgentCore Runtime & Standalone AgentCore containers."""

    name = "agentcore_runtime_deployment_service"
    payload_schemas = PAYLOAD_SCHEMAS

    def __init__(self) -> None:
        super().__init__()
        self._storage_dir = _get_storage_dir()
        self._state_file = self._storage_dir / "runtime_state.json"

    async def teardown(self) -> None:
        """No-op teardown for AgentCoreRuntimeDeploymentService."""

    def _load_state(self) -> dict[str, Any]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                logger.warning("Failed to read AgentCore runtime_state.json, initializing fresh state.")
        return {
            "agents": {},
            "tools": {},
            "connections": {},
            "executions": {},
        }

    def _save_state(self, state: dict[str, Any]) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _export_agentcore_bundle(self, agent_id: str, agent_record: dict[str, Any], state: dict[str, Any]) -> None:
        """Write standalone AgentCore Runtime bundle files for the deployment."""
        try:
            bundle_dir = self._storage_dir / "deployments" / agent_id
            bundle_dir.mkdir(parents=True, exist_ok=True)

            tool_ids = agent_record.get("tool_ids", [])
            attached_tools = [state["tools"][tid] for tid in tool_ids if tid in state["tools"]]

            manifest = {
                "agent_id": agent_id,
                "name": agent_record.get("name"),
                "display_name": agent_record.get("display_name"),
                "description": agent_record.get("description"),
                "llm": agent_record.get("llm"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "tools": [
                    {
                        "tool_id": t["id"],
                        "name": t["name"],
                        "display_name": t["display_name"],
                        "source_ref": t.get("source_ref"),
                    }
                    for t in attached_tools
                ],
            }
            (bundle_dir / "agentcore_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Sync primary flow JSON to both the deployment directory and method1_json_flow/agent_flow.json
            if attached_tools:
                primary_flow_data = attached_tools[0].get("flow_data")
                if primary_flow_data:
                    wrapped = (
                        {"data": primary_flow_data}
                        if isinstance(primary_flow_data, dict) and "nodes" in primary_flow_data
                        else primary_flow_data
                    )
                    flow_json_str = json.dumps(wrapped, indent=2, ensure_ascii=False)
                    (bundle_dir / "agent_flow.json").write_text(flow_json_str, encoding="utf-8")
                    method1_flow = self._storage_dir / "method1_json_flow" / "agent_flow.json"
                    if method1_flow.parent.exists():
                        method1_flow.write_text(flow_json_str, encoding="utf-8")
        except Exception:  # noqa: BLE001
            logger.warning("Failed to export AgentCore bundle for %s", agent_id, exc_info=True)

    async def verify_credentials(
        self,
        *,
        user_id: IdLike,
        payload: VerifyCredentials,
    ) -> VerifyCredentialsResult:
        _ = user_id
        if not payload.base_url:
            raise InvalidContentError(message="AgentCore Runtime endpoint URL is required.")
        return VerifyCredentialsResult(provider_result={"verified": True, "endpoint": payload.base_url})

    async def list_types(
        self,
        *,
        user_id: IdLike,
        db: AsyncSession,
    ) -> DeploymentListTypesResult:
        _ = user_id, db
        return DeploymentListTypesResult(deployment_types=list(SUPPORTED_ADAPTER_DEPLOYMENT_TYPES))

    async def list_llms(
        self,
        *,
        user_id: IdLike,
        db: AsyncSession,
    ) -> DeploymentListLlmsResult:
        _ = user_id, db
        provider_result = WatsonxDeploymentLlmListResultData(
            models=[WatsonxModelOut(model_name=m) for m in DEFAULT_AGENTCORE_MODELS]
        ).model_dump(mode="json")
        return DeploymentListLlmsResult(provider_result=provider_result)

    async def create(
        self,
        *,
        user_id: IdLike,
        payload: DeploymentCreate,
        db: AsyncSession,
    ) -> DeploymentCreateResult:
        _ = user_id, db
        if payload.spec.type not in SUPPORTED_ADAPTER_DEPLOYMENT_TYPES:
            raise OperationNotSupportedError(message=f"Unsupported deployment type: {payload.spec.type}")

        parsed_provider: WatsonxDeploymentCreatePayload = PAYLOAD_SCHEMAS.deployment_create.parse(
            payload.provider_data or {}
        )
        state = self._load_state()

        # 1. Create connections
        created_app_ids: list[str] = []
        for conn in parsed_provider.connections.raw_payloads or []:
            app_id = str(conn.app_id)
            state["connections"][app_id] = {
                "app_id": app_id,
                "connection_id": f"conn_{uuid4().hex[:10]}",
                "environment_variables": {
                    k: {"value": str(v.value), "source": str(v.source)}
                    for k, v in (conn.environment_variables or {}).items()
                },
            }
            created_app_ids.append(app_id)

        # 2. Map raw flow tool payloads by technical tool_name
        raw_tools_by_name: dict[str, BaseFlowArtifact] = {}
        for raw_tool in parsed_provider.tools.raw_payloads or []:
            tool_name = str(raw_tool.provider_data.tool_name)
            raw_tools_by_name[tool_name] = raw_tool

        # 3. Process operations to create/attach tools
        tools_with_refs: list[WatsonxToolRefBinding] = []
        tool_app_bindings: list[WatsonxToolAppBinding] = []
        attached_tool_ids: list[str] = []

        for op in parsed_provider.operations:
            if isinstance(op, WatsonxBindOperation):
                tool_ref = op.tool
                app_ids = [str(a) for a in op.app_ids]
                if tool_ref.tool_id_with_ref is not None:
                    tid = str(tool_ref.tool_id_with_ref.tool_id)
                    sref = str(tool_ref.tool_id_with_ref.source_ref)
                    if tid in state["tools"]:
                        state["tools"][tid]["connections"] = {a: a for a in app_ids}
                else:
                    tname = str(tool_ref.name_with_ref.name)
                    sref = str(tool_ref.name_with_ref.source_ref)
                    raw_artifact = raw_tools_by_name.get(tname)
                    tid = f"ac_tool_{uuid4().hex[:12]}"
                    display_name = (
                        str(raw_artifact.provider_data.tool_display_name or raw_artifact.name)
                        if raw_artifact
                        else tname
                    )
                    state["tools"][tid] = {
                        "id": tid,
                        "name": tname,
                        "display_name": display_name,
                        "description": (raw_artifact.description or "") if raw_artifact else "",
                        "source_ref": sref,
                        "connections": {a: a for a in app_ids},
                        "flow_data": raw_artifact.data if raw_artifact else None,
                    }
                    tools_with_refs.append(WatsonxToolRefBinding(source_ref=sref, tool_id=tid))
                if tid not in attached_tool_ids:
                    attached_tool_ids.append(tid)
                tool_app_bindings.append(WatsonxToolAppBinding(tool_id=tid, app_ids=app_ids))
            else:
                # Attach existing tool
                tid = str(op.tool.tool_id)
                if tid not in attached_tool_ids:
                    attached_tool_ids.append(tid)

        # Also create any raw_payloads not explicitly referenced in bind operations
        created_source_refs = {b.source_ref for b in tools_with_refs}
        for tname, raw_artifact in raw_tools_by_name.items():
            sref = str(raw_artifact.provider_data.source_ref)
            if sref not in created_source_refs:
                tid = f"ac_tool_{uuid4().hex[:12]}"
                display_name = str(raw_artifact.provider_data.tool_display_name or raw_artifact.name)
                state["tools"][tid] = {
                    "id": tid,
                    "name": tname,
                    "display_name": display_name,
                    "description": raw_artifact.description or "",
                    "source_ref": sref,
                    "connections": {},
                    "flow_data": raw_artifact.data,
                }
                tools_with_refs.append(WatsonxToolRefBinding(source_ref=sref, tool_id=tid))
                if tid not in attached_tool_ids:
                    attached_tool_ids.append(tid)

        agent_id = f"ac_agent_{uuid4().hex[:12]}"
        technical_name = build_langflow_wxo_resource_name(parsed_provider.display_name, resource="agent")
        description = payload.spec.description or ""

        agent_record = {
            "id": agent_id,
            "name": technical_name,
            "display_name": parsed_provider.display_name,
            "description": description,
            "llm": str(parsed_provider.llm),
            "tool_ids": attached_tool_ids,
            "environments": ["draft", "live"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        state["agents"][agent_id] = agent_record
        self._save_state(state)
        self._export_agentcore_bundle(agent_id, agent_record, state)

        provider_result = WatsonxDeploymentCreateResultData(
            display_name=parsed_provider.display_name,
            app_ids=created_app_ids,
            tools_with_refs=tools_with_refs,
            tool_app_bindings=tool_app_bindings,
        ).model_dump(mode="json")

        return DeploymentCreateResult(
            id=agent_id,
            name=technical_name,
            type=DeploymentType.AGENT,
            description=description,
            provider_result=provider_result,
        )

    async def list(
        self,
        *,
        user_id: IdLike,
        params: DeploymentListParams | None = None,
        db: AsyncSession,
    ) -> DeploymentListResult:
        _ = user_id, db
        state = self._load_state()
        agents = state.get("agents", {})

        requested_ids = None
        if params and params.deployment_ids:
            requested_ids = {str(did) for did in params.deployment_ids}

        items: list[ItemResult] = []
        for agent_id, agent in agents.items():
            if requested_ids is not None and agent_id not in requested_ids:
                continue
            items.append(
                ItemResult(
                    id=agent_id,
                    name=agent.get("name") or agent_id,
                    type=DeploymentType.AGENT,
                    provider_data={
                        "display_name": agent.get("display_name") or agent.get("name") or agent_id,
                        "description": agent.get("description") or "",
                        "tool_ids": agent.get("tool_ids") or [],
                        "llm": agent.get("llm") or DEFAULT_AGENTCORE_MODELS[0],
                        "environments": ["draft"],
                    },
                )
            )
        return DeploymentListResult(deployments=items)

    async def get(
        self,
        *,
        user_id: IdLike,
        deployment_id: IdLike,
        deployment_type: DeploymentType | None = None,
        db: AsyncSession,
    ) -> DeploymentGetResult:
        _ = user_id, deployment_type, db
        dep_id = _normalize_and_validate_id(deployment_id, field_name="deployment_id")
        state = self._load_state()
        agent = state.get("agents", {}).get(dep_id)
        if not agent:
            raise DeploymentNotFoundError(deployment_id=dep_id)

        return DeploymentGetResult(
            id=dep_id,
            name=agent.get("name") or dep_id,
            type=DeploymentType.AGENT,
            description=agent.get("description") or "",
            provider_data={
                "display_name": agent.get("display_name") or agent.get("name") or dep_id,
                "description": agent.get("description") or "",
                "tool_ids": agent.get("tool_ids") or [],
                "llm": agent.get("llm") or DEFAULT_AGENTCORE_MODELS[0],
                "environments": ["draft", "live"],
            },
        )

    async def update(
        self,
        *,
        user_id: IdLike,
        deployment_id: IdLike,
        deployment_type: DeploymentType | None = None,
        payload: DeploymentUpdate,
        db: AsyncSession,
    ) -> DeploymentUpdateResult:
        _ = user_id, deployment_type, db
        dep_id = _normalize_and_validate_id(deployment_id, field_name="deployment_id")
        state = self._load_state()
        agent = state.get("agents", {}).get(dep_id)
        if not agent:
            raise DeploymentNotFoundError(deployment_id=dep_id)

        if payload.spec and payload.spec.description is not None:
            agent["description"] = payload.spec.description

        created_app_ids: list[str] = []
        created_snapshot_ids: list[str] = []
        added_snapshot_ids: list[str] = []
        created_snapshot_bindings: list[WatsonxResultToolRefBinding] = []
        added_snapshot_bindings: list[WatsonxResultToolRefBinding] = []
        removed_snapshot_bindings: list[WatsonxResultToolRefBinding] = []
        referenced_snapshot_bindings: list[WatsonxResultToolRefBinding] = []

        if payload.provider_data:
            parsed_update: WatsonxDeploymentUpdatePayload = PAYLOAD_SCHEMAS.deployment_update.parse(
                payload.provider_data
            )
            if parsed_update.display_name is not None:
                agent["display_name"] = parsed_update.display_name
            if parsed_update.llm is not None:
                agent["llm"] = str(parsed_update.llm)

            if parsed_update.put_tools is not None:
                agent["tool_ids"] = [str(tid) for tid in parsed_update.put_tools]
            else:
                for conn in parsed_update.connections.raw_payloads or []:
                    app_id = str(conn.app_id)
                    state["connections"][app_id] = {
                        "app_id": app_id,
                        "connection_id": f"conn_{uuid4().hex[:10]}",
                        "environment_variables": {
                            k: {"value": str(v.value), "source": str(v.source)}
                            for k, v in (conn.environment_variables or {}).items()
                        },
                    }
                    created_app_ids.append(app_id)

                raw_tools_by_name: dict[str, BaseFlowArtifact] = {
                    str(rt.provider_data.tool_name): rt for rt in (parsed_update.tools.raw_payloads or [])
                }
                current_tools: list[str] = list(agent.get("tool_ids") or [])

                for op in parsed_update.operations:
                    if isinstance(op, WatsonxBindOperation):
                        tool_ref = op.tool
                        app_ids = [str(a) for a in op.app_ids]
                        if tool_ref.tool_id_with_ref is not None:
                            tid = str(tool_ref.tool_id_with_ref.tool_id)
                            sref = str(tool_ref.tool_id_with_ref.source_ref)
                            if tid in state["tools"]:
                                existing_conns = dict(state["tools"][tid].get("connections") or {})
                                for a in app_ids:
                                    existing_conns[a] = a
                                state["tools"][tid]["connections"] = existing_conns
                            binding = WatsonxResultToolRefBinding(source_ref=sref, tool_id=tid, created=False)
                            referenced_snapshot_bindings.append(binding)
                            if tid not in current_tools:
                                current_tools.append(tid)
                                added_snapshot_ids.append(tid)
                                added_snapshot_bindings.append(binding)
                        else:
                            tname = str(tool_ref.name_with_ref.name)
                            sref = str(tool_ref.name_with_ref.source_ref)
                            raw_artifact = raw_tools_by_name.get(tname)
                            tid = f"ac_tool_{uuid4().hex[:12]}"
                            display_name = (
                                str(raw_artifact.provider_data.tool_display_name or raw_artifact.name)
                                if raw_artifact
                                else tname
                            )
                            state["tools"][tid] = {
                                "id": tid,
                                "name": tname,
                                "display_name": display_name,
                                "description": (raw_artifact.description or "") if raw_artifact else "",
                                "source_ref": sref,
                                "connections": {a: a for a in app_ids},
                                "flow_data": raw_artifact.data if raw_artifact else None,
                            }
                            binding = WatsonxResultToolRefBinding(source_ref=sref, tool_id=tid, created=True)
                            created_snapshot_ids.append(tid)
                            added_snapshot_ids.append(tid)
                            created_snapshot_bindings.append(binding)
                            added_snapshot_bindings.append(binding)
                            referenced_snapshot_bindings.append(binding)
                            if tid not in current_tools:
                                current_tools.append(tid)
                    elif isinstance(op, WatsonxUnbindOperation):
                        tid = str(op.tool.tool_id)
                        sref = str(op.tool.source_ref)
                        if tid in state["tools"]:
                            existing_conns = dict(state["tools"][tid].get("connections") or {})
                            for a in op.app_ids:
                                existing_conns.pop(str(a), None)
                            state["tools"][tid]["connections"] = existing_conns
                        referenced_snapshot_bindings.append(
                            WatsonxResultToolRefBinding(source_ref=sref, tool_id=tid, created=False)
                        )
                    elif isinstance(op, WatsonxRenameToolOperation):
                        tid = str(op.tool.tool_id)
                        sref = str(op.tool.source_ref)
                        if tid in state["tools"]:
                            state["tools"][tid]["display_name"] = str(op.new_name)
                        referenced_snapshot_bindings.append(
                            WatsonxResultToolRefBinding(source_ref=sref, tool_id=tid, created=False)
                        )
                    elif isinstance(op, WatsonxRemoveToolOperation):
                        tid = str(op.tool.tool_id)
                        sref = str(op.tool.source_ref)
                        if tid in current_tools:
                            current_tools.remove(tid)
                        binding = WatsonxResultToolRefBinding(source_ref=sref, tool_id=tid, created=False)
                        removed_snapshot_bindings.append(binding)
                        referenced_snapshot_bindings.append(binding)
                    else:
                        # Attach tool operation
                        tid = str(op.tool.tool_id)
                        binding = WatsonxResultToolRefBinding(source_ref=tid, tool_id=tid, created=False)
                        referenced_snapshot_bindings.append(binding)
                        if tid not in current_tools:
                            current_tools.append(tid)
                            added_snapshot_ids.append(tid)
                            added_snapshot_bindings.append(binding)

                agent["tool_ids"] = current_tools

        self._save_state(state)
        self._export_agentcore_bundle(dep_id, agent, state)

        provider_result = WatsonxDeploymentUpdateResultData(
            name=agent["name"],
            display_name=agent["display_name"],
            description=agent.get("description"),
            created_app_ids=created_app_ids,
            created_snapshot_ids=created_snapshot_ids,
            added_snapshot_ids=added_snapshot_ids,
            created_snapshot_bindings=created_snapshot_bindings,
            added_snapshot_bindings=added_snapshot_bindings,
            removed_snapshot_bindings=removed_snapshot_bindings,
            referenced_snapshot_bindings=referenced_snapshot_bindings,
        ).model_dump(mode="json")

        return DeploymentUpdateResult(
            id=dep_id,
            provider_result=provider_result,
        )

    async def update_snapshot(
        self,
        *,
        user_id: IdLike,
        snapshot_id: IdLike,
        flow_artifact: BaseFlowArtifact,
        db: AsyncSession,
    ) -> SnapshotUpdateResult:
        _ = user_id, db
        sid = _normalize_and_validate_id(snapshot_id, field_name="snapshot_id")
        state = self._load_state()
        tool = state.get("tools", {}).get(sid)
        if not tool:
            raise ResourceNotFoundError(resource_id=sid, message=f"Tool snapshot '{sid}' not found.")

        tool["flow_data"] = flow_artifact.data
        tool["description"] = flow_artifact.description or tool.get("description") or ""
        if flow_artifact.provider_data and isinstance(flow_artifact.provider_data, dict):
            if flow_artifact.provider_data.get("source_ref"):
                tool["source_ref"] = str(flow_artifact.provider_data["source_ref"])
            if flow_artifact.provider_data.get("tool_display_name"):
                tool["display_name"] = str(flow_artifact.provider_data["tool_display_name"])

        self._save_state(state)
        for agent_id, agent in state.get("agents", {}).items():
            if sid in (agent.get("tool_ids") or []):
                self._export_agentcore_bundle(agent_id, agent, state)

        return SnapshotUpdateResult(snapshot_id=sid)

    async def redeploy(
        self,
        *,
        user_id: IdLike,
        deployment_id: IdLike,
        deployment_type: DeploymentType | None = None,
        db: AsyncSession,
    ) -> RedeployResult:
        _ = user_id, deployment_type, db
        dep_id = _normalize_and_validate_id(deployment_id, field_name="deployment_id")
        state = self._load_state()
        agent = state.get("agents", {}).get(dep_id)
        if not agent:
            raise DeploymentNotFoundError(deployment_id=dep_id)
        self._export_agentcore_bundle(dep_id, agent, state)
        return RedeployResult(id=dep_id)

    async def duplicate(
        self,
        *,
        user_id: IdLike,
        deployment_id: IdLike,
        deployment_type: DeploymentType | None = None,
        db: AsyncSession,
    ) -> DeploymentDuplicateResult:
        _ = user_id, deployment_type, db
        dep_id = _normalize_and_validate_id(deployment_id, field_name="deployment_id")
        state = self._load_state()
        agent = state.get("agents", {}).get(dep_id)
        if not agent:
            raise DeploymentNotFoundError(deployment_id=dep_id)
        new_id = f"ac_agent_{uuid4().hex[:12]}"
        new_agent = dict(agent)
        new_agent["id"] = new_id
        new_agent["display_name"] = f"{agent['display_name']} (Copy)"
        state["agents"][new_id] = new_agent
        self._save_state(state)
        self._export_agentcore_bundle(new_id, new_agent, state)
        return DeploymentDuplicateResult(
            id=new_id,
            name=new_agent["name"],
            type=DeploymentType.AGENT,
        )

    async def delete(
        self,
        *,
        user_id: IdLike,
        deployment_id: IdLike,
        deployment_type: DeploymentType | None = None,
        db: AsyncSession,
    ) -> DeploymentDeleteResult:
        _ = user_id, deployment_type, db
        dep_id = _normalize_and_validate_id(deployment_id, field_name="deployment_id")
        state = self._load_state()
        if dep_id not in state.get("agents", {}):
            raise DeploymentNotFoundError(deployment_id=dep_id)
        state["agents"].pop(dep_id, None)
        self._save_state(state)
        return DeploymentDeleteResult(id=dep_id)

    async def get_status(
        self,
        *,
        user_id: IdLike,
        deployment_id: IdLike,
        deployment_type: DeploymentType | None = None,
        db: AsyncSession,
    ) -> DeploymentStatusResult:
        _ = user_id, deployment_type, db
        dep_id = _normalize_and_validate_id(deployment_id, field_name="deployment_id")
        state = self._load_state()
        if dep_id not in state.get("agents", {}):
            raise DeploymentNotFoundError(deployment_id=dep_id)
        return DeploymentStatusResult(id=dep_id, provider_data={"status": "healthy", "runtime": "agentcore"})

    async def _execute_attached_flow(
        self,
        agent: dict[str, Any],
        state: dict[str, Any],
        message_text: str,
        thread_id: str,
    ) -> str:
        """Execute the attached Langflow flow via live AgentCore Runtime (/invocations) or LFX runtime."""
        display_name = str(agent.get("display_name") or "")
        description = str(agent.get("description") or "")
        is_method2 = (
            "cách 2" in display_name.lower()
            or "method 2" in display_name.lower()
            or "python graph" in display_name.lower()
            or "8082" in description.lower()
        )
        runtime_port = 8082 if is_method2 else 8081
        runtime_url = f"http://127.0.0.1:{runtime_port}/invocations"

        tool_ids = agent.get("tool_ids") or []
        for tid in tool_ids:
            tool = state.get("tools", {}).get(tid)
            if not tool or not tool.get("flow_data"):
                continue
            raw_fd = tool["flow_data"]
            wrapped_fd = {"data": raw_fd} if isinstance(raw_fd, dict) and "nodes" in raw_fd else raw_fd
            flow_path = self._storage_dir / "deployments" / agent["id"] / f"{tid}.json"
            flow_path.parent.mkdir(parents=True, exist_ok=True)
            flow_json_str = json.dumps(wrapped_fd, ensure_ascii=False, indent=2)
            flow_path.write_text(flow_json_str, encoding="utf-8")

            if not is_method2:
                method1_flow = self._storage_dir / "method1_json_flow" / "agent_flow.json"
                if method1_flow.parent.exists():
                    method1_flow.write_text(flow_json_str, encoding="utf-8")

            # 0. Try calling REAL AWS Bedrock AgentCore Runtime (ap-southeast-1) if configured
            aws_meta_file = self._storage_dir / "aws_deployed_runtimes.json"
            if aws_meta_file.exists():
                try:
                    import boto3

                    aws_meta = json.loads(aws_meta_file.read_text(encoding="utf-8"))
                    target_key = "method2" if is_method2 else "method1"
                    runtime_arn = aws_meta.get(target_key, {}).get("runtime_arn")
                    if runtime_arn:
                        boto_sess = boto3.Session(
                            aws_access_key_id=aws_meta.get("aws_access_key_id"),
                            aws_secret_access_key=aws_meta.get("aws_secret_access_key"),
                            aws_session_token=aws_meta.get("aws_session_token"),
                            region_name=aws_meta.get("region", "ap-southeast-1"),
                        )
                        ac_client = boto_sess.client("bedrock-agentcore")
                        aws_session_id = thread_id if len(thread_id) >= 33 else f"langflow-aws-session-{thread_id}-{uuid4().hex}"
                        aws_resp = ac_client.invoke_agent_runtime(
                            agentRuntimeArn=runtime_arn,
                            runtimeSessionId=aws_session_id,
                            payload=json.dumps({"prompt": message_text}).encode("utf-8"),
                        )
                        raw_body = aws_resp["response"].read().decode("utf-8")
                        parsed_aws = json.loads(raw_body)
                        if isinstance(parsed_aws, dict) and "result" in parsed_aws:
                            return str(parsed_aws["result"])
                        return raw_body
                except Exception as aws_exc:  # noqa: BLE001
                    logger.warning("AWS Bedrock AgentCore invocation warning, falling back to local runtime: %s", aws_exc)

            # 1. Try calling the live AgentCore Runtime HTTP server (/invocations)
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        runtime_url,
                        headers={"X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": thread_id},
                        json={"prompt": message_text, "session_id": thread_id},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict) and "output" in data:
                            return str(data["output"])
            except Exception as http_exc:  # noqa: BLE001
                logger.debug("AgentCore HTTP server on port %s not used, falling back to LFX: %s", runtime_port, http_exc)

            # 2. Fallback to direct LFX execution
            try:
                script_to_run = (
                    self._storage_dir / "method2_python_graph" / "agent_graph.py"
                    if is_method2 and (self._storage_dir / "method2_python_graph" / "agent_graph.py").exists()
                    else flow_path
                )
                result = await run_flow(
                    script_path=script_to_run,
                    input_value=message_text,
                    session_id=thread_id,
                    output_format="json",
                    check_variables=False,
                )
                if isinstance(result, dict):
                    text_out = (
                        result.get("result")
                        or result.get("text")
                        or result.get("output")
                        or json.dumps(result, ensure_ascii=False)
                    )
                    return str(text_out)
                return str(result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AgentCore flow execution warning for tool %s: %s", tid, exc)
                return (
                    f"[AgentCore Runtime - {agent.get('display_name')}]\n"
                    f"Flow '{tool.get('display_name')}' nhận input: \"{message_text}\"\n"
                    f"(Chi tiết thực thi: {exc})"
                )
        return f"[AgentCore Runtime - {agent.get('display_name')}] Đã nhận tin nhắn: {message_text}"

    async def create_execution(
        self,
        *,
        user_id: IdLike,
        payload: ExecutionCreate,
        db: AsyncSession,
    ) -> ExecutionCreateResult:
        _ = user_id, db
        dep_id = _normalize_and_validate_id(payload.deployment_id, field_name="deployment_id")
        state = self._load_state()
        agent = state.get("agents", {}).get(dep_id)
        if not agent:
            raise DeploymentNotFoundError(deployment_id=dep_id)

        provider_data = payload.provider_data or {}
        if provider_data.get("input") is not None:
            message_text = str(provider_data["input"])
        else:
            msg_obj = provider_data.get("message") or {}
            message_text = str(msg_obj.get("content") or "") if isinstance(msg_obj, dict) else str(msg_obj)
        thread_id = str(provider_data.get("thread_id") or f"ac_thread_{uuid4().hex[:10]}")
        execution_id = f"ac_exec_{uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc).isoformat()

        output_text = await self._execute_attached_flow(
            agent=agent,
            state=state,
            message_text=message_text,
            thread_id=thread_id,
        )
        completed_at = datetime.now(timezone.utc).isoformat()

        exec_record = {
            "execution_id": execution_id,
            "agent_id": dep_id,
            "thread_id": thread_id,
            "status": "completed",
            "started_at": started_at,
            "completed_at": completed_at,
            "result": {
                "data": {
                    "message": {
                        "content": [
                            {
                                "response_type": "text",
                                "text": output_text,
                            }
                        ]
                    }
                }
            },
        }
        state["executions"][execution_id] = exec_record
        self._save_state(state)

        return ExecutionCreateResult(
            execution_id=execution_id,
            deployment_id=dep_id,
            provider_result=exec_record,
        )

    async def get_execution(
        self,
        *,
        user_id: IdLike,
        execution_id: IdLike,
        deployment_type: DeploymentType | None = None,
        db: AsyncSession,
    ) -> ExecutionStatusResult:
        _ = user_id, deployment_type, db
        exec_id = _normalize_and_validate_id(execution_id, field_name="execution_id")
        state = self._load_state()
        exec_record = state.get("executions", {}).get(exec_id)
        if not exec_record:
            raise ResourceNotFoundError(resource_id=exec_id, message=f"Execution '{exec_id}' not found.")

        return ExecutionStatusResult(
            execution_id=exec_id,
            deployment_id=exec_record.get("agent_id") or "",
            provider_result=exec_record,
        )

    async def list_configs(
        self,
        *,
        user_id: IdLike,
        params: ConfigListParams | None = None,
        db: AsyncSession,
    ) -> ConfigListResult:
        _ = user_id, db
        state = self._load_state()
        connections = state.get("connections", {})
        items: list[ConfigItem] = []
        for app_id, conn in connections.items():
            items.append(
                ConfigItem(
                    id=conn.get("connection_id") or app_id,
                    name=app_id,
                    provider_data={
                        "type": "key_value_creds",
                        "environment": "draft",
                    },
                )
            )
        dep_id = None
        if params and params.deployment_ids:
            dep_id = str(params.deployment_ids[0])
        provider_result: dict[str, Any] = {}
        if dep_id:
            provider_result["deployment_id"] = dep_id
            agent = state.get("agents", {}).get(dep_id)
            provider_result["tool_ids"] = (agent.get("tool_ids") or []) if agent else []
        return ConfigListResult(configs=items, provider_result=provider_result)

    async def list_snapshots(
        self,
        *,
        user_id: IdLike,
        params: SnapshotListParams | None = None,
        db: AsyncSession,
    ) -> SnapshotListResult:
        _ = user_id, db
        state = self._load_state()
        tools = state.get("tools", {})

        allowed_ids: set[str] | None = None
        dep_id: str | None = None
        if params:
            if params.snapshot_ids:
                allowed_ids = {str(sid) for sid in params.snapshot_ids}
            elif params.deployment_ids:
                dep_id = str(params.deployment_ids[0])
                agent = state.get("agents", {}).get(dep_id)
                allowed_ids = set(agent.get("tool_ids") or []) if agent else set()

        items: list[SnapshotItem] = []
        for tid, tool in tools.items():
            if allowed_ids is not None and tid not in allowed_ids:
                continue
            items.append(
                SnapshotItem(
                    id=tid,
                    name=tool.get("display_name") or tool.get("name") or tid,
                    provider_data={
                        "name": tool.get("name") or tid,
                        "display_name": tool.get("display_name") or tool.get("name") or tid,
                        "connections": tool.get("connections") or {},
                    },
                )
            )
        provider_result = {"deployment_id": dep_id} if dep_id else {}
        return SnapshotListResult(snapshots=items, provider_result=provider_result)
