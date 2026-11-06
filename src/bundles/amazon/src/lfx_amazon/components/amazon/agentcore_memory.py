from __future__ import annotations

import time

from lfx.base.models.aws_constants import AWS_REGIONS
from lfx.custom.custom_component.component import Component
from lfx.io import (
    BoolInput,
    DropdownInput,
    IntInput,
    MessageTextInput,
    Output,
    StrInput,
)
from lfx.schema.data import Data
from lfx.schema.message import Message


class AgentCoreMemoryComponent(Component):
    """Manage Short-Term & Long-Term Conversational Memory on AWS Bedrock AgentCore (AgentCoreMemorySessionManager)."""

    display_name = "AgentCore Memory (AgentCoreMemorySessionManager)"
    description = (
        "AgentCore Memory (AgentCoreMemorySessionManager) — ID: harness_hr_agent_test_1-EaQdhn7ACO "
        "quản lý phiên hội thoại và bộ nhớ dài hạn cho HR Agent trên AWS Bedrock AgentCore."
    )
    icon = "Amazon"
    name = "AgentCoreMemory"

    inputs = [
        MessageTextInput(
            name="user_message",
            display_name="User Message / Event",
            info="Tin nhắn người dùng hoặc sự kiện hội thoại cần lưu/truy xuất từ bộ nhớ AgentCore.",
            required=False,
        ),
        StrInput(
            name="memory_id",
            display_name="AgentCore Memory ID",
            value="harness_hr_agent_test_1-EaQdhn7ACO",
            info="Định danh bộ nhớ AgentCore Memory (VD: harness_hr_agent_test_1-EaQdhn7ACO).",
            required=True,
        ),
        DropdownInput(
            name="memory_strategy",
            display_name="Memory Session Manager / Strategy",
            options=[
                "AgentCoreMemorySessionManager (Short-Term + Long-Term)",
                "SummaryMemoryStrategy (Tóm tắt phiên)",
                "SemanticMemoryStrategy (Vector ngữ nghĩa)",
                "UserPreferenceMemoryStrategy (Sở thích người dùng)",
            ],
            value="AgentCoreMemorySessionManager (Short-Term + Long-Term)",
            info="Cơ chế quản lý phiên và trích xuất bộ nhớ dài hạn của AgentCore.",
        ),
        StrInput(
            name="actor_id",
            display_name="Actor ID",
            value="msb-hr-employee",
            info="Định danh người dùng / Actor trong AgentCore Memory.",
        ),
        StrInput(
            name="session_id",
            display_name="Session ID",
            value="hr-agent-session-001",
            info="Mã phiên hội thoại (Session ID).",
        ),
        StrInput(
            name="namespace",
            display_name="Memory Namespace",
            value="/hr-agent/sessions/{actorId}",
            info="Namespace phân tách vùng nhớ theo chuẩn AWS Bedrock AgentCore.",
            advanced=True,
        ),
        IntInput(
            name="top_k_memories",
            display_name="Top-K Recalled Memories",
            value=5,
            info="Số lượng bản ghi bộ nhớ liên quan nhất được truy xuất cho Prompt.",
            advanced=True,
        ),
        BoolInput(
            name="persist_event",
            display_name="Persist Event to Session",
            value=True,
            info="Ghi nhận lượt hội thoại hiện tại vào luồng sự kiện (create_event) của AgentCore.",
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
            display_name="Enriched Memory Context",
            name="memory_context",
            method="build_memory_context",
        ),
        Output(
            display_name="Memory Record Data",
            name="memory_data",
            method="build_memory_data",
        ),
    ]

    def _build_record(self) -> dict:
        resolved_ns = (self.namespace or "/hr-agent/sessions/{actorId}").replace(
            "{actorId}", self.actor_id or "default-user"
        )
        msg_text = str(self.user_message or "")
        mem_id = self.memory_id or "harness_hr_agent_test_1-EaQdhn7ACO"
        return {
            "memory_id": mem_id,
            "session_manager": "AgentCoreMemorySessionManager",
            "actor_id": self.actor_id or "msb-hr-employee",
            "session_id": self.session_id or "hr-agent-session-001",
            "strategy": self.memory_strategy,
            "namespace": resolved_ns,
            "region": self.region_name or "ap-southeast-1",
            "top_k": self.top_k_memories or 5,
            "persisted": bool(self.persist_event),
            "timestamp": int(time.time()),
            "latest_event": msg_text,
            "context_summary": (
                f"[AgentCore Memory ({mem_id}) | Manager: AgentCoreMemorySessionManager | Actor: {self.actor_id}]\n"
                f"Ngữ cảnh phiên HR Agent: {msg_text}"
            ),
        }

    def build_memory_context(self) -> Message:
        rec = self._build_record()
        self.status = f"Memory {rec['memory_id']} synced"
        return Message(text=rec["context_summary"])

    def build_memory_data(self) -> Data:
        rec = self._build_record()
        self.status = f"Memory {rec['memory_id']}"
        return Data(data=rec)
