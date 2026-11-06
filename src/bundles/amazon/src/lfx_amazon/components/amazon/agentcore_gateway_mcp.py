from __future__ import annotations

import json
from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    DropdownInput,
    MessageTextInput,
    Output,
    SecretStrInput,
    StrInput,
)
from lfx.schema.data import Data
from lfx.schema.message import Message


class AgentCoreGatewayMCPComponent(Component):
    """Generic AWS Bedrock AgentCore Gateway component (Inbound OIDC / Outbound MCP Gateway)."""

    display_name = "AgentCore Gateway (Inbound / Outbound MCP)"
    description = (
        "Cấu hình và kết nối động tới bất kỳ AWS Bedrock AgentCore Gateway nào "
        "(Inbound OIDC Gateway hoặc Outbound MCP Gateway)."
    )
    icon = "Amazon"
    name = "AgentCoreGatewayMCP"

    inputs = [
        DropdownInput(
            name="gateway_role",
            display_name="Gateway Role & Identifier",
            options=[
                "Inbound Gateway: inbound-hr-gateway (Custom JWT Authorizer — Keycloak OIDC)",
                "Outbound Gateway (RAG & Targets): gateway-retrieval-hr-agent-xcjlmpsg83 (AWS IAM SigV4 + Token Vault API Key)",
                "Outbound Gateway (HR Ops): gateway-hr-operations (AgentCore MCP Gateway + Cedar Policy Engine -> Kong API GW)",
            ],
            value="Outbound Gateway (RAG & Targets): gateway-retrieval-hr-agent-xcjlmpsg83 (AWS IAM SigV4 + Token Vault API Key)",
            info="Chọn vai trò cổng AgentCore Gateway hoặc nhập Gateway ID bất kỳ bên dưới.",
        ),
        StrInput(
            name="gateway_id",
            display_name="Gateway ID",
            value="gateway-retrieval-hr-agent-xcjlmpsg83",
            info="Định danh Gateway (VD: inbound-hr-gateway, gateway-retrieval-hr-agent-xcjlmpsg83, gateway-hr-operations, hoặc ID Gateway bất kỳ).",
            required=True,
        ),
        DropdownInput(
            name="auth_mode",
            display_name="Security / Authorization Policy",
            options=[
                "AWS IAM SigV4 + Token Vault API Key",
                "Custom JWT Authorizer (Keycloak OIDC)",
                "Cedar Policy Engine -> Kong API GW",
            ],
            value="AWS IAM SigV4 + Token Vault API Key",
            info="Cơ chế xác thực và phân quyền trên AgentCore Gateway.",
        ),
        StrInput(
            name="gateway_url",
            display_name="AgentCore Gateway Endpoint (Optional)",
            value="",
            info="URL điểm cuối MCP của Gateway (để trống sẽ tự động phân giải từ Gateway ID và AWS Region).",
        ),
        MessageTextInput(
            name="tool_query",
            display_name="Gateway Request / Payload",
            info="Dữ liệu hoặc yêu cầu đi qua AgentCore Gateway.",
            required=False,
        ),
        StrInput(
            name="mcp_tool_name",
            display_name="MCP Tool Name (Optional)",
            value="",
            info="Tên MCP Tool cụ thể muốn gọi qua Gateway (để trống sẽ tự động khám phá danh sách tools/list).",
            advanced=True,
        ),
        StrInput(
            name="mcp_tool_arguments_json",
            display_name="MCP Tool Arguments JSON (Optional)",
            value="",
            info="Chuỗi JSON tham số truyền vào MCP Tool khi gọi tools/call.",
            advanced=True,
        ),
        DropdownInput(
            name="region_name",
            display_name="AWS Region",
            value="ap-southeast-1",
            options=AWS_REGIONS,
            advanced=True,
        ),
        SecretStrInput(
            name="oauth_bearer_token",
            display_name="Keycloak OIDC JWT / Token Vault Key (Optional)",
            advanced=True,
        ),
    ]

    outputs = [
        Output(
            display_name="Gateway Output Message",
            name="tool_context",
            method="build_gateway_message",
        ),
        Output(
            display_name="Gateway Spec Data",
            name="gateway_data",
            method="build_gateway_data",
        ),
    ]

    def _resolve_gateway_url(self, gw_id: str, region: str) -> str:
        custom_url = (self.gateway_url or "").strip()
        if custom_url and custom_url != "https://gateway.bedrock-agentcore.ap-southeast-1.amazonaws.com/mcp":
            return custom_url
        clean_id = gw_id.split()[0].strip()
        return f"https://{clean_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"

    def _gateway_spec(self) -> dict:
        if hasattr(self, "_cached_spec") and self._cached_spec:
            return self._cached_spec

        gw_id = str(self.gateway_id or "").strip()
        clean_id = gw_id.split()[0].strip() if gw_id else ""
        region = self.region_name or "ap-southeast-1"
        query = str(self.tool_query or "").strip()
        endpoint_url = self._resolve_gateway_url(clean_id, region)

        spec: dict = {
            "gateway_role": self.gateway_role,
            "gateway_id": clean_id,
            "auth_mode": self.auth_mode,
            "gateway_url": endpoint_url,
            "region": region,
            "query": query,
        }

        if clean_id and "inbound" not in clean_id.lower():
            try:
                import httpx

                headers = {"MCP-Protocol-Version": "2025-11-25", "Content-Type": "application/json"}
                if self.oauth_bearer_token:
                    headers["Authorization"] = f"Bearer {self.oauth_bearer_token}"

                with httpx.Client(timeout=15.0) as client:
                    list_resp = client.post(
                        endpoint_url,
                        headers=headers,
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    )
                    if list_resp.status_code == 200:
                        tools_meta = list_resp.json().get("result", {}).get("tools", [])
                        spec["mcp_tools_available"] = [t.get("name") for t in tools_meta if isinstance(t, dict)]

                        explicit_tool = (getattr(self, "mcp_tool_name", "") or "").strip()
                        raw_args = (getattr(self, "mcp_tool_arguments_json", "") or "").strip()
                        if explicit_tool:
                            args_dict = json.loads(raw_args) if raw_args else {"query": query}
                            call_resp = client.post(
                                endpoint_url,
                                headers=headers,
                                json={
                                    "jsonrpc": "2.0",
                                    "id": 2,
                                    "method": "tools/call",
                                    "params": {"name": explicit_tool, "arguments": args_dict},
                                },
                            )
                            spec["mcp_tool_called"] = explicit_tool
                            spec["mcp_tool_result"] = call_resp.json().get("result", {})
            except Exception as exc:  # noqa: BLE001
                spec["mcp_discovery_note"] = str(exc)

        self._cached_spec = spec
        return spec

    def build_gateway_message(self) -> Message:
        spec = self._gateway_spec()
        tools = spec.get("mcp_tools_available") or []
        self.status = (
            f"{spec['gateway_id']} ({len(tools)} MCP tools)"
            if tools
            else f"{spec['gateway_id']} ({spec['auth_mode']})"
        )
        return Message(text=spec["query"])

    def build_gateway_data(self) -> Data:
        spec = self._gateway_spec()
        self.status = f"Gateway {spec['gateway_id']}"
        return Data(data=spec)
