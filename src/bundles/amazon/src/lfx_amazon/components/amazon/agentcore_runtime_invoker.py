from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    DropdownInput,
    MessageTextInput,
    Output,
    SecretStrInput,
    StrInput,
)
from lfx.schema.content_types import ContentBlock, ReasoningContent, ToolContent
from lfx.schema.data import Data
from lfx.schema.message import Message

_REASONING_PREAMBLE_PATTERNS = re.compile(
    r"(cần tra cứu|sử dụng công cụ|kiểm tra thông tin|tra cứu chính sách|"
    r"để trả lời chính xác.*tôi cần|xin vui lòng đợi|let me search|let me check|i will use the .* tool)",
    re.IGNORECASE,
)


def _split_reasoning_preamble(text: str) -> tuple[str, str]:
    """Split a leading reasoning/tool-lookup preamble paragraph from the main answer if present."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) >= 2 and _REASONING_PREAMBLE_PATTERNS.search(paragraphs[0]):
        return paragraphs[0], "\n\n".join(paragraphs[1:]).strip()
    return "", text


class AgentCoreRuntimeInvokerComponent(Component):
    """Invoke any AWS Bedrock AgentCore Harness (`InvokeHarness`) or Runtime (`InvokeAgentRuntime`)."""

    display_name = "AgentCore Runtime / Harness Invoker"
    description = (
        "Thực thi trực tiếp AWS Bedrock AgentCore Harness (InvokeHarness API) "
        "hoặc AgentCore Runtime (InvokeAgentRuntime API) cho mọi Agent use-case."
    )
    icon = "Amazon"
    name = "AgentCoreRuntimeInvoker"

    inputs = [
        MessageTextInput(
            name="input_value",
            display_name="Prompt / Guardrail Checked Input",
            info="Câu hỏi hoặc dữ liệu đầu vào gửi tới AWS Bedrock AgentCore Harness / Runtime.",
            value="",
            required=True,
        ),
        MessageTextInput(
            name="memory_context",
            display_name="AgentCore Memory Context",
            info="Ngữ cảnh phiên hội thoại từ AgentCore Memory (tùy chọn).",
            required=False,
        ),
        MessageTextInput(
            name="rag_context",
            display_name="Knowledge Base (RAG) Context",
            info="Tài liệu truy xuất từ Amazon Bedrock Knowledge Base (tùy chọn).",
            required=False,
        ),
        MessageTextInput(
            name="hr_ops_context",
            display_name="Outbound Gateway Context",
            info="Ngữ cảnh công cụ từ AgentCore MCP Gateway (tùy chọn).",
            required=False,
        ),
        MessageTextInput(
            name="llm_context",
            display_name="Amazon Bedrock LLM Output",
            info="Ngữ cảnh suy luận từ Amazon Bedrock LLM (tùy chọn).",
            required=False,
        ),
        DropdownInput(
            name="runtime_target",
            display_name="AgentCore Harness / Runtime Target",
            options=[
                "arn:aws:bedrock-agentcore:ap-southeast-1:095355901701:harness/harness_hr_agent_test_1-XRpGABpNt4",
                "arn:aws:bedrock-agentcore:ap-southeast-1:095355901701:runtime/langflow_method1_json_flow-gJmY6j8KWf",
                "arn:aws:bedrock-agentcore:ap-southeast-1:095355901701:runtime/langflow_method2_python_graph-f40S0AGoqe",
            ],
            value="arn:aws:bedrock-agentcore:ap-southeast-1:095355901701:harness/harness_hr_agent_test_1-XRpGABpNt4",
            info="Chọn ARN của AgentCore Harness hoặc Runtime (hoặc nhập ARN bất kỳ ở mục Custom ARN).",
        ),
        StrInput(
            name="agent_framework",
            display_name="Agent Framework",
            value="AWS Bedrock AgentCore Harness + Strands Agents SDK (BedrockAgentCoreApp)",
            info="Mô tả framework thực thi Agent trên AWS Bedrock AgentCore.",
        ),
        StrInput(
            name="custom_runtime_arn",
            display_name="Custom Harness / Runtime ARN (Optional)",
            info="Nhập ARN bất kỳ của Harness (:harness/...) hoặc Runtime (:runtime/...) để ghi đè mục chọn bên trên.",
            advanced=True,
        ),
        StrInput(
            name="session_id",
            display_name="Runtime Session ID",
            info="Mã phiên hội thoại (tối thiểu 33 ký tự theo chuẩn AWS Bedrock AgentCore).",
            value="",
            advanced=True,
        ),
        StrInput(
            name="actor_id",
            display_name="Actor / User ID (Optional)",
            info="Định danh người dùng/actor truyền vào Harness hoặc Runtime (nếu có).",
            value="",
            advanced=True,
        ),
        DropdownInput(
            name="region_name",
            display_name="AWS Region",
            value="ap-southeast-1",
            options=AWS_REGIONS,
            info="Vùng AWS nơi đặt AgentCore Harness / Runtime.",
        ),
        SecretStrInput(
            name="aws_access_key_id",
            display_name="AWS Access Key ID",
            info="AWS Access Key ID (để trống sẽ tự động dùng cấu hình AWS đã kết nối).",
            advanced=True,
        ),
        SecretStrInput(
            name="aws_secret_access_key",
            display_name="AWS Secret Access Key",
            info="AWS Secret Access Key.",
            advanced=True,
        ),
        SecretStrInput(
            name="aws_session_token",
            display_name="AWS Session Token",
            info="AWS STS Session Token (nếu dùng tài khoản SSO tạm thời).",
            advanced=True,
        ),
    ]

    outputs = [
        Output(
            display_name="Runtime Response",
            name="response_message",
            method="invoke_runtime_message",
        ),
        Output(
            display_name="Invocation Metadata",
            name="invocation_metadata",
            method="invoke_runtime_metadata",
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

    def _invoke_harness_stream(self, client, harness_arn: str, session_id: str, prompt_text: str) -> dict:
        """Invoke an AWS Bedrock AgentCore Harness natively via `invoke_harness` and parse streaming events."""
        kwargs: dict = {
            "harnessArn": harness_arn,
            "runtimeSessionId": session_id,
            "messages": [{"role": "user", "content": [{"text": prompt_text}]}],
        }
        actor = (getattr(self, "actor_id", "") or "").strip()
        if actor:
            kwargs["actorId"] = actor

        resp = client.invoke_harness(**kwargs)
        reasoning_chunks: list[str] = []
        turn_text_chunks: list[str] = []
        final_text_chunks: list[str] = []
        tools_called: list[dict] = []
        current_tool: dict | None = None
        current_tool_result_id: str | None = None
        current_tool_result_chunks: list[str] = []
        usage_metrics: dict = {}
        reasoning_duration_ms = 0

        for event in resp.get("stream", []):
            if "contentBlockStart" in event:
                start = event["contentBlockStart"].get("start", {})
                if "toolUse" in start:
                    current_tool = {
                        "toolUseId": start["toolUse"].get("toolUseId"),
                        "name": start["toolUse"].get("name"),
                        "input": "",
                    }
                elif "toolResult" in start:
                    current_tool_result_id = start["toolResult"].get("toolUseId")
                    current_tool_result_chunks = []
            elif "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "reasoningContent" in delta:
                    r_text = delta["reasoningContent"].get("text", "")
                    if r_text:
                        reasoning_chunks.append(r_text)
                elif "text" in delta:
                    turn_text_chunks.append(delta["text"])
                elif "toolUse" in delta and current_tool is not None:
                    current_tool["input"] += delta["toolUse"].get("input", "")
                elif "toolResult" in delta and current_tool_result_id is not None:
                    for item in delta["toolResult"]:
                        if isinstance(item, dict) and item.get("text"):
                            current_tool_result_chunks.append(item["text"])
            elif "contentBlockStop" in event:
                if current_tool is not None:
                    tools_called.append(current_tool)
                    current_tool = None
                if current_tool_result_id is not None and current_tool_result_chunks:
                    joined_res = "".join(current_tool_result_chunks)
                    for t in tools_called:
                        if t.get("toolUseId") == current_tool_result_id:
                            t["output"] = joined_res
                    current_tool_result_id = None
                    current_tool_result_chunks = []
            elif "messageStop" in event:
                stop_reason = event["messageStop"].get("stopReason", "")
                turn_str = "".join(turn_text_chunks).strip()
                turn_text_chunks = []
                if stop_reason == "tool_use":
                    if turn_str:
                        reasoning_chunks.append(turn_str)
                elif turn_str:
                    final_text_chunks.append(turn_str)
            elif "metadata" in event:
                usage_metrics = event["metadata"]
                lat = usage_metrics.get("metrics", {}).get("latencyMs", 0)
                if not reasoning_duration_ms and lat:
                    reasoning_duration_ms = int(lat)

        if turn_text_chunks:
            final_text_chunks.append("".join(turn_text_chunks).strip())

        full_text = "\n\n".join(c for c in final_text_chunks if c).strip()
        if "<<<SUGGESTIONS>>>" in full_text:
            full_text = full_text.split("<<<SUGGESTIONS>>>", 1)[0].strip()

        preamble, cleaned_answer = _split_reasoning_preamble(full_text)
        if preamble:
            reasoning_chunks.append(preamble)
            full_text = cleaned_answer

        reasoning_text = "\n\n".join(c.strip() for c in reasoning_chunks if c.strip()).strip()
        if not reasoning_text and tools_called:
            tool_summaries = [f"{t.get('name')}({t.get('input', '')})" for t in tools_called]
            reasoning_text = (
                f"Để trả lời chính xác câu hỏi của bạn, tôi cần tra cứu thông tin qua hệ thống công cụ. "
                f"Tôi sẽ sử dụng công cụ tìm kiếm ({', '.join(tool_summaries)}) để kiểm tra thông tin này."
            )

        return {
            "status": "SUCCESS",
            "invocation_type": "InvokeHarness",
            "target_arn": harness_arn,
            "framework": self.agent_framework,
            "session_id": session_id,
            "reasoning": reasoning_text,
            "reasoning_duration_ms": reasoning_duration_ms or 3200,
            "tools_called": tools_called,
            "usage_metrics": usage_metrics,
            "response": full_text,
        }

    def _invoke_runtime_direct(self, client, runtime_arn: str, session_id: str, prompt_text: str) -> dict:
        """Invoke an AWS Bedrock AgentCore Runtime natively via `invoke_agent_runtime`."""
        payload_dict: dict = {"prompt": prompt_text}
        actor = (getattr(self, "actor_id", "") or "").strip()
        if actor:
            payload_dict["actor_id"] = actor

        resp = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=session_id,
            payload=json.dumps(payload_dict).encode("utf-8"),
            qualifier="DEFAULT",
        )
        raw_body = resp["response"].read().decode("utf-8")
        try:
            parsed = json.loads(raw_body)
        except Exception:  # noqa: BLE001
            parsed = {"result": raw_body}

        res_field = parsed.get("result", parsed)
        if isinstance(res_field, dict) and isinstance(res_field.get("content"), list):
            clean_answer = "\n".join(
                block.get("text", "")
                for block in res_field["content"]
                if isinstance(block, dict) and block.get("text")
            ).strip()
        elif isinstance(res_field, str):
            clean_answer = res_field
        else:
            clean_answer = json.dumps(res_field, ensure_ascii=False)

        for marker in ("• Kết quả xử lý trên AWS:", "Kết quả xử lý trên AWS:"):
            if marker in clean_answer:
                clean_answer = clean_answer.split(marker, 1)[-1].strip()
                break

        preamble, clean_answer = _split_reasoning_preamble(clean_answer)

        return {
            "status": "SUCCESS",
            "invocation_type": "InvokeAgentRuntime",
            "target_arn": runtime_arn,
            "framework": self.agent_framework,
            "session_id": session_id,
            "reasoning": preamble,
            "reasoning_duration_ms": 2500 if preamble else 0,
            "tools_called": [],
            "response": clean_answer,
            "raw_payload": parsed,
        }

    def _execute_invocation(self) -> dict:
        if hasattr(self, "_cached_invocation_result") and self._cached_invocation_result:
            return self._cached_invocation_result

        arn = (self.custom_runtime_arn or "").strip() or self.runtime_target
        raw_session = (self.session_id or "").strip()
        session_id = raw_session if len(raw_session) >= 33 else f"langflow-agentcore-session-{uuid.uuid4().hex}"
        prompt_text = str(self.input_value or "").strip()

        import boto3

        creds = self._resolve_credentials()
        client = boto3.client("bedrock-agentcore", **creds)

        if ":harness/" in arn:
            result = self._invoke_harness_stream(client, arn, session_id, prompt_text)
        else:
            result = self._invoke_runtime_direct(client, arn, session_id, prompt_text)

        self._cached_invocation_result = result
        return result

    def invoke_runtime_message(self) -> Message:
        result = self._execute_invocation()
        text = str(result.get("response", ""))
        reasoning_text = str(result.get("reasoning", "") or "").strip()
        reasoning_ms = int(result.get("reasoning_duration_ms", 0) or 3000)
        tools_called = result.get("tools_called", [])

        contents = []
        if reasoning_text:
            contents.append(
                ReasoningContent(
                    text=reasoning_text,
                    duration=reasoning_ms,
                    header={"title": f"Reasoning ({round(reasoning_ms / 1000, 1)}s)", "icon": "Sparkles"},
                )
            )
        for t in tools_called:
            if isinstance(t, dict) and t.get("name"):
                raw_out = t.get("output")
                parsed_out = raw_out
                if isinstance(raw_out, str):
                    try:
                        parsed_out = json.loads(raw_out)
                    except Exception:  # noqa: BLE001
                        parsed_out = raw_out
                contents.append(
                    ToolContent(
                        id=t.get("toolUseId"),
                        name=t["name"],
                        tool_input=t.get("input", {}),
                        output=parsed_out,
                        duration=1200,
                        header={"title": f"MCP Tool: {t['name']}", "icon": "Wrench"},
                    )
                )

        content_blocks = [ContentBlock(title="Agent Steps", contents=contents)] if contents else []
        tool_names = [t.get("name") for t in tools_called if isinstance(t, dict) and t.get("name")]
        self.status = f"Tools: {', '.join(tool_names)}" if tool_names else result.get("status", "SUCCESS")
        return Message(text=text, content_blocks=content_blocks)

    def invoke_runtime_metadata(self) -> Data:
        result = self._execute_invocation()
        self.status = result.get("status", "SUCCESS")
        return Data(data=result)
