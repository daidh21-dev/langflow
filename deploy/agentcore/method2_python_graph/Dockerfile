FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install lightweight LFX executor + ASGI server for AgentCore Runtime
RUN pip install --no-cache-dir lfx fastapi uvicorn bedrock-agentcore

COPY agent_graph.py app.py ./

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

