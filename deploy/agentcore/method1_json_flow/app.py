"""AgentCore Runtime Entrypoint - Method 1: Standalone JSON Flow (agent_flow.json).

Executes a JSON flow exported from Langflow UI (`https://langflow.daido.dev`)
directly inside AWS Bedrock AgentCore Runtime using the lightweight `lfx` engine.

Implements the AWS Bedrock AgentCore Runtime HTTP contract:
- GET  /ping        -> Health check (200 OK, {"status": "Healthy"})
- POST /invocations -> Agent execution endpoint on port 8080
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from lfx.run.base import run_flow

FLOW_JSON_PATH = Path(__file__).parent / "agent_flow.json"


async def invoke_agent(payload: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Execute the exported Langflow JSON file using LFX runtime."""
    prompt = payload.get("prompt") or payload.get("input_value") or "Hello AgentCore!"
    resolved_session_id = (
        session_id
        or payload.get("session_id")
        or "agentcore-session-default"
    )

    result = await run_flow(
        script_path=FLOW_JSON_PATH,
        input_value=prompt,
        session_id=resolved_session_id,
        output_format="json",
        check_variables=False,
    )
    return {
        "mode": "method1_json_flow",
        "session_id": resolved_session_id,
        "output": result.get("result") or result.get("text") or result,
    }


app = FastAPI(title="Langflow AgentCore Runtime (Method 1 - JSON Flow)")


@app.get("/ping")
async def ping() -> dict[str, str]:
    """AgentCore Runtime required health check endpoint."""
    return {"status": "Healthy"}


@app.post("/invocations")
async def invocations(request: Request) -> dict[str, Any]:
    """AgentCore Runtime required invocation endpoint."""
    payload = await request.json()
    session_id = request.headers.get("X-Amzn-Bedrock-AgentCore-Runtime-Session-Id")
    return await invoke_agent(payload, session_id=session_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)

