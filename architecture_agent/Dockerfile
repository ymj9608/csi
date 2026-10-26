FROM python:3.11-slim
WORKDIR /app
COPY architecture_agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home csi
COPY architecture_agent /app/architecture_agent
COPY coding_agent /app/coding_agent
USER csi
CMD ["python", "-m", "architecture_agent.diagram_worker", "--all", "--backend", "http://backend:8080", "--ollama-url", "http://host.docker.internal:11434"]
