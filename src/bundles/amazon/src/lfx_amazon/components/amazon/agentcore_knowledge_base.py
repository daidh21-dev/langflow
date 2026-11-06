from __future__ import annotations

import json
import os
from pathlib import Path

from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    DropdownInput,
    IntInput,
    MessageTextInput,
    Output,
    SecretStrInput,
    StrInput,
)
from lfx.schema.data import Data
from lfx.schema.message import Message


class AgentCoreKnowledgeBaseComponent(Component):
    """Amazon Bedrock Knowledge Base (S3 + Vector Search) component with dynamic MCP Gateway & SDK support."""

    display_name = "Amazon Bedrock Knowledge Base (RAG)"
    description = (
        "Truy vấn tri thức RAG trên Amazon Bedrock Knowledge Base (S3 + Vector Search) "
        "trực tiếp qua AWS SDK hoặc thông qua AgentCore Outbound MCP Gateway bất kỳ."
    )
    icon = "Amazon"
    name = "AgentCoreKnowledgeBase"

    inputs = [
        MessageTextInput(
            name="search_query",
            display_name="Search Query",
            info="Câu hỏi hoặc từ khóa cần tra cứu trên Amazon Bedrock Knowledge Base.",
            value="",
            required=False,
        ),
        StrInput(
            name="knowledge_base_id",
            display_name="Knowledge Base ID",
            value="RVAHZPCHQN",
            info="Định danh Amazon Bedrock Knowledge Base (10 ký tự).",
            required=True,
        ),
        StrInput(
            name="outbound_gateway_id",
            display_name="Outbound MCP Gateway ID (Optional)",
            value="gateway-retrieval-hr-agent-xcjlmpsg83",
            info="Định danh AgentCore MCP Gateway kết nối tới Knowledge Base (nếu truy xuất qua Gateway).",
        ),
        DropdownInput(
            name="retrieval_storage",
            display_name="Storage & Search Engine",
            options=[
                "Amazon Bedrock Knowledge Base (S3 + Vector Search)",
                "Amazon OpenSearch Serverless Vector Store",
                "Amazon Aurora PostgreSQL (pgvector)",
            ],
            value="Amazon Bedrock Knowledge Base (S3 + Vector Search)",
            info="Cơ chế lưu trữ tài liệu nguồn và tìm kiếm vector.",
        ),
        IntInput(
            name="top_k",
            display_name="Top K Results",
            value=5,
            info="Số lượng đoạn tài liệu (chunks) liên quan nhất cần trích xuất.",
            advanced=True,
        ),
        DropdownInput(
            name="region_name",
            display_name="AWS Region",
            value="ap-southeast-1",
            options=AWS_REGIONS,
            info="Vùng AWS nơi đặt Amazon Bedrock Knowledge Base.",
        ),
        SecretStrInput(
            name="aws_access_key_id",
            display_name="AWS Access Key ID",
            advanced=True,
        ),
        SecretStrInput(
            name="aws_secret_access_key",
            display_name="AWS Secret Access Key",
            advanced=True,
        ),
        SecretStrInput(
            name="aws_session_token",
            display_name="AWS Session Token",
            advanced=True,
        ),
    ]

    outputs = [
        Output(
            display_name="RAG Context Message",
            name="rag_context",
            method="retrieve_rag_message",
        ),
        Output(
            display_name="KB Citations Data",
            name="kb_citations",
            method="retrieve_kb_data",
        ),
    ]

    def _resolve_credentials(self) -> dict[str, str]:
        creds: dict[str, str] = {"region_name": self.region_name or "ap-southeast-1"}
        ak = (self.aws_access_key_id or "").strip()
        sk = (self.aws_secret_access_key or "").strip()
        st = (self.aws_session_token or "").strip()
        if ak in {"AWS_ACCESS_KEY_ID", ""}:
            ak = ""
        if sk in {"AWS_SECRET_ACCESS_KEY", ""}:
            sk = ""
        if st in {"AWS_SESSION_TOKEN", ""}:
            st = ""

        if ak and sk:
            creds["aws_access_key_id"] = ak
            creds["aws_secret_access_key"] = sk
            if st:
                creds["aws_session_token"] = st
            return creds

        meta_file = Path("/app/deploy/agentcore/aws_deployed_runtimes.json")
        if meta_file.exists():
            try:
                saved = json.loads(meta_file.read_text(encoding="utf-8"))
                if saved.get("aws_access_key_id") and saved.get("aws_secret_access_key"):
                    creds["aws_access_key_id"] = saved["aws_access_key_id"]
                    creds["aws_secret_access_key"] = saved["aws_secret_access_key"]
                    if saved.get("aws_session_token"):
                        creds["aws_session_token"] = saved["aws_session_token"]
                    return creds
            except Exception:  # noqa: BLE001
                pass

        if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
            creds["aws_access_key_id"] = os.environ["AWS_ACCESS_KEY_ID"]
            creds["aws_secret_access_key"] = os.environ["AWS_SECRET_ACCESS_KEY"]
            if os.environ.get("AWS_SESSION_TOKEN"):
                creds["aws_session_token"] = os.environ["AWS_SESSION_TOKEN"]
        return creds

    def _retrieve_kb(self) -> dict:
        if hasattr(self, "_cached_kb_result") and self._cached_kb_result:
            return self._cached_kb_result

        kb_id = (self.knowledge_base_id or "").strip()
        query = str(self.search_query or "").strip()
        gw_id = (self.outbound_gateway_id or "").strip().split()[0] if self.outbound_gateway_id else ""
        region = self.region_name or "ap-southeast-1"
        top_k = int(self.top_k or 5)

        # 1. Try direct AWS Bedrock Agent Runtime Retrieve API first
        try:
            import boto3

            creds = self._resolve_credentials()
            agent_runtime = boto3.client("bedrock-agent-runtime", **creds)
            resp = agent_runtime.retrieve(
                knowledgeBaseId=kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
            )
            results = resp.get("retrievalResults", [])
            snippets = [
                r.get("content", {}).get("text", "")
                for r in results
                if isinstance(r, dict) and r.get("content", {}).get("text")
            ]
            if snippets:
                out = {
                    "status": "RETRIEVED_DIRECT_SDK",
                    "knowledge_base_id": kb_id,
                    "outbound_gateway_id": gw_id,
                    "query": query,
                    "num_chunks": len(snippets),
                    "snippets": snippets[:top_k],
                }
                self._cached_kb_result = out
                return out
        except Exception:  # noqa: BLE001
            pass

        # 2. Dynamically discover & call any KB retrieval tool on the configured Outbound MCP Gateway
        if gw_id and query:
            try:
                import httpx

                mcp_url = f"https://{gw_id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"
                headers = {"MCP-Protocol-Version": "2025-11-25", "Content-Type": "application/json"}
                with httpx.Client(timeout=20.0) as client:
                    list_resp = client.post(
                        mcp_url,
                        headers=headers,
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    )
                    tools = list_resp.json().get("result", {}).get("tools", [])
                    kb_tool_name = None
                    for t in tools:
                        props = t.get("inputSchema", {}).get("properties", {})
                        if "kb_id" in props and "query" in props:
                            kb_tool_name = t.get("name")
                            break
                    if kb_tool_name:
                        mcp_resp = client.post(
                            mcp_url,
                            headers=headers,
                            json={
                                "jsonrpc": "2.0",
                                "id": 2,
                                "method": "tools/call",
                                "params": {
                                    "name": kb_tool_name,
                                    "arguments": {"kb_id": kb_id, "query": query, "top_k": top_k},
                                },
                            },
                        )
                        content_blocks = mcp_resp.json().get("result", {}).get("content", [])
                        if content_blocks and content_blocks[0].get("text"):
                            parsed_kb = json.loads(content_blocks[0]["text"])
                            results = parsed_kb.get("results", [])
                            snippets = [
                                f"[{r.get('document_title', 'Document')} - #{r.get('citation_id')}]: {r.get('content', '')}"
                                for r in results
                                if isinstance(r, dict) and r.get("content")
                            ]
                            out = {
                                "status": "RETRIEVED_VIA_MCP_GATEWAY",
                                "knowledge_base_id": kb_id,
                                "outbound_gateway_id": gw_id,
                                "mcp_tool": kb_tool_name,
                                "query": query,
                                "num_chunks": len(snippets),
                                "snippets": snippets[:top_k],
                                "citations": results,
                            }
                            self._cached_kb_result = out
                            return out
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "ERROR",
                    "knowledge_base_id": kb_id,
                    "outbound_gateway_id": gw_id,
                    "query": query,
                    "num_chunks": 0,
                    "snippets": [],
                    "error": str(exc),
                }

        return {
            "status": "NO_RESULTS",
            "knowledge_base_id": kb_id,
            "outbound_gateway_id": gw_id,
            "query": query,
            "num_chunks": 0,
            "snippets": [],
        }

    def retrieve_rag_message(self) -> Message:
        res = self._retrieve_kb()
        text = "\n\n".join(res.get("snippets", []))
        self.status = f"KB {res['knowledge_base_id']} ({res['num_chunks']} chunks)"
        return Message(text=text)

    def retrieve_kb_data(self) -> Data:
        res = self._retrieve_kb()
        self.status = res.get("status", "RETRIEVED")
        return Data(data=res)
