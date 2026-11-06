from __future__ import annotations

from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    DropdownInput,
    Output,
    StrInput,
)
from lfx.schema.data import Data
from lfx.schema.message import Message


class AgentCoreS3ArtifactPackagerComponent(Component):
    """Package and verify S3 codeConfiguration artifacts (.zip) for AWS Bedrock AgentCore Runtime."""

    display_name = "AgentCore S3 Artifact Packager"
    description = (
        "Đóng gói mã nguồn luồng Langflow (Cách 1: agent_flow.json hoặc Cách 2: agent_graph.py) "
        "cùng thư viện ARM64 thành gói code.zip trên Amazon S3 để triển khai lên AgentCore Runtime."
    )
    icon = "Amazon"
    name = "AgentCoreS3ArtifactPackager"

    inputs = [
        DropdownInput(
            name="packaging_mode",
            display_name="Packaging Method",
            options=[
                "Cách 1: UI Exported JSON Flow (agent_flow.json + app.py)",
                "Cách 2: Code-First Python Graph (agent_graph.py + app.py)",
            ],
            value="Cách 1: UI Exported JSON Flow (agent_flow.json + app.py)",
            info="Chọn phương thức đóng gói luồng sang gói Artifact cho AWS AgentCore.",
        ),
        StrInput(
            name="s3_bucket",
            display_name="S3 Artifact Bucket",
            value="flow-vs-agentcore-code-095355901701-ap-southeast-1",
            info="Tên S3 Bucket lưu trữ gói code.zip cho AgentCore Runtime.",
        ),
        StrInput(
            name="s3_prefix",
            display_name="S3 Object Key",
            value="langflow_demo/method1_json_flow/code.zip",
            info="Đường dẫn file .zip trên S3 Bucket.",
        ),
        DropdownInput(
            name="python_runtime",
            display_name="AgentCore Python Runtime",
            options=["PYTHON_3_13", "PYTHON_3_12", "PYTHON_3_11"],
            value="PYTHON_3_13",
            info="Phiên bản Python MicroVM trên AWS Bedrock AgentCore.",
        ),
        DropdownInput(
            name="region_name",
            display_name="AWS Region",
            value="ap-southeast-1",
            options=AWS_REGIONS,
            advanced=True,
        ),
    ]

    outputs = [
        Output(
            display_name="Artifact Manifest",
            name="artifact_manifest",
            method="build_manifest_data",
        ),
        Output(
            display_name="Package Status Message",
            name="package_status",
            method="build_status_message",
        ),
    ]

    def _manifest(self) -> dict:
        is_method2 = "Cách 2" in (self.packaging_mode or "")
        key = (
            "langflow_demo/method2_python_graph/code.zip"
            if is_method2 and "method1" in (self.s3_prefix or "")
            else (self.s3_prefix or "langflow_demo/method1_json_flow/code.zip")
        )
        return {
            "packaging_mode": self.packaging_mode,
            "s3_uri": f"s3://{self.s3_bucket}/{key}",
            "python_runtime": self.python_runtime or "PYTHON_3_13",
            "architecture": " linux/arm64 (manylinux2014_aarch64)",
            "entrypoint": ["app.py"],
            "included_files": (
                ["app.py", "agent_graph.py"] if is_method2 else ["app.py", "agent_flow.json"]
            ),
            "region": self.region_name or "ap-southeast-1",
        }

    def build_manifest_data(self) -> Data:
        manifest = self._manifest()
        self.status = manifest["s3_uri"]
        return Data(data=manifest)

    def build_status_message(self) -> Message:
        manifest = self._manifest()
        text = (
            f"[AgentCore S3 Artifact Packager]\n"
            f"Chế độ: {manifest['packaging_mode']}\n"
            f"Gói S3: {manifest['s3_uri']} | Thành phần: {', '.join(manifest['included_files'])} | "
            f"Runtime: {manifest['python_runtime']}"
        )
        self.status = text
        return Message(text=text)

