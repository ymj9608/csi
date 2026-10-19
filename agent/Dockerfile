FROM python:3.11-slim
WORKDIR /app
COPY agent/requirements.lock.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home csi
COPY agent /app/agent
COPY mcp_servers /app/mcp_servers
COPY rag /app/rag
USER csi
