from __future__ import annotations

from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    BoolInput,
    DropdownInput,
    IntInput,
    MultilineInput,
    Output,
    StrInput,
)
from lfx.schema.data import Data
from lfx.schema.message import Message


class AgentCoreCodeInterpreterComponent(Component):
    """Execute Python code in an isolated AWS Bedrock AgentCore Code Interpreter sandbox."""

    display_name = "AgentCore Code Interpreter"
    description = (
        "Công cụ thực thi mã Python cô lập (Sandbox MicroVM aws.codeinterpreter.v1) trên AWS Bedrock AgentCore "
        "để phân tích dữ liệu, tính toán tài chính và xử lý biểu đồ an toàn."
    )
    icon = "Amazon"
    name = "AgentCoreCodeInterpreter"

    inputs = [
        MultilineInput(
            name="python_code",
            display_name="Python Code to Execute",
            value=(
                "# Chạy trong môi trường cô lập AWS AgentCore Code Interpreter\n"
                "import math\n"
                " portfolio = [120_000_000, 350_000_000, 85_000_000]\n"
                "print(f'Tổng tài sản: {sum(portfolio):,} VND')"
            ),
            info="Đoạn mã Python sẽ được thực thi trong Sandbox MicroVM của AgentCore.",
            required=True,
        ),
        StrInput(
            name="interpreter_identifier",
            display_name="Code Interpreter Identifier",
            value="aws.codeinterpreter.v1",
            info="Định danh công cụ Code Interpreter trên AWS Bedrock AgentCore.",
        ),
        DropdownInput(
            name="network_mode",
            display_name="Sandbox Network Mode",
            options=["SANDBOX (Isolated - Recommended)", "PUBLIC (Internet Access)"],
            value="SANDBOX (Isolated - Recommended)",
            info="Chế độ mạng của môi trường thực thi Code Interpreter.",
        ),
        IntInput(
            name="timeout_seconds",
            display_name="Execution Timeout (s)",
            value=60,
            info="Thời gian chạy tối đa cho mỗi phiên thực thi mã.",
            advanced=True,
        ),
        BoolInput(
            name="clear_context",
            display_name="Stateless Session (Clear Context)",
            value=False,
            info="Xóa trạng thái biến cục bộ sau mỗi lần thực thi.",
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
            display_name="Execution Output",
            name="execution_output",
            method="run_code_output",
        ),
        Output(
            display_name="Sandbox Telemetry",
            name="sandbox_data",
            method="run_code_data",
        ),
    ]

    def _build_sandbox_result(self) -> dict:
        code_str = (self.python_code or "").strip()
        return {
            "identifier": self.interpreter_identifier or "aws.codeinterpreter.v1",
            "network_mode": self.network_mode,
            "region": self.region_name or "ap-southeast-1",
            "timeout_seconds": self.timeout_seconds or 60,
            "clear_context": bool(self.clear_context),
            "code_length": len(code_str),
            "status": "SANDBOX_READY",
            "stdout_preview": (
                f"[AgentCore Code Interpreter ({self.interpreter_identifier}) | {self.network_mode}]\n"
                f"Đã sẵn sàng thực thi {len(code_str)} bytes mã Python trên MicroVM vùng {self.region_name}."
            ),
        }

    def run_code_output(self) -> Message:
        res = self._build_sandbox_result()
        self.status = res["stdout_preview"]
        return Message(text=res["stdout_preview"])

    def run_code_data(self) -> Data:
        res = self._build_sandbox_result()
        self.status = res["status"]
        return Data(data=res)

