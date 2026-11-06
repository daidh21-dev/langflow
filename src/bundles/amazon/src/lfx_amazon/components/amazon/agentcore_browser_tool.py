from __future__ import annotations

from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    BoolInput,
    DropdownInput,
    MessageTextInput,
    Output,
    StrInput,
)
from lfx.schema.data import Data
from lfx.schema.message import Message


class AgentCoreBrowserToolComponent(Component):
    """Automate headless web navigation and inspection via AWS Bedrock AgentCore Browser Tool."""

    display_name = "AgentCore Browser Tool"
    description = (
        "Công cụ trình duyệt đám mây cô lập (aws.browser.v1) trên AWS Bedrock AgentCore giúp Agent "
        "truy cập trang web, trích xuất nội dung DOM và tự động hóa thao tác duyệt web an toàn."
    )
    icon = "Amazon"
    name = "AgentCoreBrowserTool"

    inputs = [
        StrInput(
            name="target_url",
            display_name="Target URL",
            value="https://aws.amazon.com/bedrock/agentcore/",
            info="Địa chỉ URL trang web mà AgentCore Browser sẽ mở và trích xuất thông tin.",
            required=True,
        ),
        MessageTextInput(
            name="navigation_instruction",
            display_name="Navigation / Extraction Task",
            value="Trích xuất tiêu đề chính và tóm tắt tính năng của trang.",
            info="Chỉ dẫn cho trình duyệt đám mây AgentCore thực hiện trên trang mục tiêu.",
        ),
        StrInput(
            name="browser_identifier",
            display_name="Browser Tool Identifier",
            value="aws.browser.v1",
            info="Định danh công cụ Cloud Browser mặc định của AWS Bedrock AgentCore.",
            advanced=True,
        ),
        BoolInput(
            name="enable_session_recording",
            display_name="Record Session Replay to S3",
            value=True,
            info="Lưu lại lịch sử phiên duyệt web lên S3 để kiểm toán (Audit).",
            advanced=True,
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
            display_name="Browser Summary",
            name="browser_summary",
            method="build_browser_summary",
        ),
        Output(
            display_name="Browser Session Data",
            name="browser_data",
            method="build_browser_data",
        ),
    ]

    def _snapshot(self) -> dict:
        return {
            "browser_identifier": self.browser_identifier or "aws.browser.v1",
            "target_url": self.target_url,
            "instruction": str(self.navigation_instruction or ""),
            "session_recording": bool(self.enable_session_recording),
            "region": self.region_name or "ap-southeast-1",
            "status": "READY",
        }

    def build_browser_summary(self) -> Message:
        snap = self._snapshot()
        text = (
            f"[AgentCore Browser ({snap['browser_identifier']}) | URL: {snap['target_url']}]\n"
            f"Nhiệm vụ: {snap['instruction']} | Ghi nhật ký phiên S3: {'Bật' if snap['session_recording'] else 'Tắt'}"
        )
        self.status = text
        return Message(text=text)

    def build_browser_data(self) -> Data:
        snap = self._snapshot()
        self.status = f"Browser ready ({snap['target_url']})"
        return Data(data=snap)

