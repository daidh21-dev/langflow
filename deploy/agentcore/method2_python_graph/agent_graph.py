"""Standalone Langflow Graph in Python (Code-First) for AgentCore Runtime."""

from lfx.components.input_output import ChatInput, ChatOutput
from lfx.components.models_and_agents import PromptComponent
from lfx.graph import Graph


def get_graph() -> Graph:
    """Build a standalone Langflow graph executable by LFX without the Langflow server."""
    chat_input = ChatInput()

    prompt_component = PromptComponent()
    prompt_component.set(
        template=(
            "✅ [AgentCore Runtime - Cách 2: Python Graph (Code-First, Port 8082)]\n"
            "• Trạng thái: Đang chạy độc lập qua giao thức chuẩn AgentCore (/ping & /invocations)\n"
            "• Nội dung yêu cầu nhận được: \"{user_input}\"\n"
            "• Kết quả xử lý: Agent Python Graph đã xử lý thành công yêu cầu nghiệp vụ của bạn!"
        ),
        user_input=chat_input.message_response,
    )

    chat_output = ChatOutput()
    chat_output.set(input_value=prompt_component.build_prompt)

    return Graph(start=chat_input, end=chat_output)


graph = get_graph()

