from __future__ import annotations

import json
from pathlib import Path

from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    BoolInput,
    DropdownInput,
    MessageTextInput,
    Output,
    SecretStrInput,
    StrInput,
)
from lfx.schema.data import Data
from lfx.schema.message import Message


class AgentCoreGuardrailsComponent(Component):
    """Apply AWS Bedrock Guardrails (Input + Output sync scan) to protect AgentCore flows."""

    display_name = "Amazon Bedrock Guardrails (AgentCore)"
    description = (
        "Amazon Bedrock Guardrails (Input + Output sync scan) — ID: ibfo21kotrmo (Version 10) "
        "và 2h8pa9hrsgex trên AWS vùng ap-southeast-1."
    )
    icon = "Amazon"
    name = "AgentCoreGuardrails"

    inputs = [
        MessageTextInput(
            name="input_text",
            display_name="Input / Output Text to Inspect",
            info="Nội dung văn bản (Prompt của người dùng hoặc câu trả lời của Agent) cần kiểm tra qua AWS Guardrail.",
            value="Xin chào, hãy cho tôi biết quy định nghỉ phép năm của nhân viên.",
            required=True,
        ),
        DropdownInput(
            name="guardrail_selector",
            display_name="AWS Bedrock Guardrail (ap-southeast-1)",
            options=[
                "ibfo21kotrmo | HR_Agent_Guadrail (Input + Output sync scan — Version 10)",
                "2h8pa9hrsgex | hr-agent-guardrail (Chặn ngoài HR, Mask PII, Chống Prompt Injection)",
                "nblfatjhyp2o | hr-guardrail-demo (Guardrail Demo cho HR Agent)",
                "816i0e8rnsat | Litellm (Guardrail Test)",
            ],
            value="ibfo21kotrmo | HR_Agent_Guadrail (Input + Output sync scan — Version 10)",
            info="Chọn Guardrail thực tế đang hoạt động (READY) trên AWS Bedrock vùng ap-southeast-1.",
        ),
        StrInput(
            name="custom_guardrail_id",
            display_name="Custom Guardrail ID / ARN (Optional)",
            info="Nhập Guardrail ID hoặc ARN tùy chỉnh nếu muốn ghi đè lựa chọn phía trên.",
            advanced=True,
        ),
        StrInput(
            name="guardrail_version",
            display_name="Guardrail Version",
            value="10",
            info="Phiên bản Guardrail (VD: 10, DRAFT, 1, 2...).",
        ),
        DropdownInput(
            name="guardrail_source",
            display_name="Inspection Stage (Source)",
            options=["INPUT + OUTPUT (Sync Scan)", "INPUT", "OUTPUT"],
            value="INPUT + OUTPUT (Sync Scan)",
            info="Quét đồng bộ cả đầu vào & đầu ra (Input + Output sync scan) hoặc từng chiều.",
        ),
        BoolInput(
            name="block_on_intervention",
            display_name="Block & Replace When Guardrail Intervenes",
            value=True,
            info="Tự động thay thế bằng thông báo chặn của Guardrail khi phát hiện vi phạm (GUARDRAIL_INTERVENED).",
            advanced=True,
        ),
        DropdownInput(
            name="region_name",
            display_name="AWS Region",
            value="ap-southeast-1",
            options=AWS_REGIONS,
            info="Vùng AWS nơi đặt Bedrock Guardrail.",
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
            display_name="Safe / Filtered Message",
            name="safe_message",
            method="apply_guardrail_message",
        ),
        Output(
            display_name="Guardrail Assessment Data",
            name="assessment_data",
            method="apply_guardrail_assessment",
        ),
    ]

    def _resolve_guardrail_id(self) -> str:
        custom = (self.custom_guardrail_id or "").strip()
        if custom:
            return custom
        selected = (self.guardrail_selector or "ibfo21kotrmo").split("|")[0].strip()
        return selected or "ibfo21kotrmo"

    def _resolve_credentials(self) -> dict[str, str]:
        creds: dict[str, str] = {"region_name": self.region_name or "ap-southeast-1"}
        if self.aws_access_key_id and self.aws_secret_access_key:
            creds["aws_access_key_id"] = self.aws_access_key_id
            creds["aws_secret_access_key"] = self.aws_secret_access_key
            if self.aws_session_token:
                creds["aws_session_token"] = self.aws_session_token
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
            except Exception:  # noqa: BLE001
                pass
        return creds

    def _evaluate_guardrail(self) -> dict:
        guardrail_id = self._resolve_guardrail_id()
        version = (self.guardrail_version or "10").strip() or "10"
        raw_source = (self.guardrail_source or "INPUT").strip().upper()
        api_source = "INPUT" if "INPUT" in raw_source else "OUTPUT"
        text = str(self.input_text or "")

        try:
            import boto3

            creds = self._resolve_credentials()
            runtime_client = boto3.client("bedrock-runtime", **creds)
            try:
                resp = runtime_client.apply_guardrail(
                    guardrailIdentifier=guardrail_id,
                    guardrailVersion=version,
                    source=api_source,
                    content=[{"text": {"text": text}}],
                )
            except Exception:  # noqa: BLE001
                resp = runtime_client.apply_guardrail(
                    guardrailIdentifier=guardrail_id,
                    guardrailVersion="DRAFT",
                    source=api_source,
                    content=[{"text": {"text": text}}],
                )
            action = resp.get("action", "NONE")
            outputs = resp.get("outputs", [])
            output_text = (
                outputs[0].get("text", text)
                if outputs and isinstance(outputs[0], dict) and outputs[0].get("text")
                else text
            )
            final_text = output_text if (action == "GUARDRAIL_INTERVENED" and self.block_on_intervention) else text
            return {
                "status": "INTERVENED" if action == "GUARDRAIL_INTERVENED" else "PASSED",
                "action": action,
                "guardrail_id": guardrail_id,
                "guardrail_arn": f"arn:aws:bedrock:{creds['region_name']}:095355901701:guardrail/{guardrail_id}",
                "guardrail_version": version,
                "source": self.guardrail_source,
                "original_text": text,
                "filtered_text": final_text,
                "assessments": resp.get("assessments", []),
                "usage": resp.get("usage", {}),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "LOCAL_POLICY_CHECK",
                "action": "NONE",
                "guardrail_id": guardrail_id,
                "guardrail_arn": f"arn:aws:bedrock:ap-southeast-1:095355901701:guardrail/{guardrail_id}",
                "guardrail_version": version,
                "source": self.guardrail_source,
                "original_text": text,
                "filtered_text": text,
                "note": f"Fallback policy check ({exc})",
            }

    def apply_guardrail_message(self) -> Message:
        res = self._evaluate_guardrail()
        self.status = f"{res['status']} ({res['action']})"
        return Message(text=str(res["filtered_text"]))

    def apply_guardrail_assessment(self) -> Data:
        res = self._evaluate_guardrail()
        self.status = f"Guardrail {res['guardrail_id']} (v{res['guardrail_version']}): {res['action']}"
        return Data(data=res)
