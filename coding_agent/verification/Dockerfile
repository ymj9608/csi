FROM python:3.11-slim
COPY coding_agent/verification/requirements.lock.txt /opt/verification/requirements.txt
RUN pip install --no-cache-dir -r /opt/verification/requirements.txt
COPY coding_agent/verification/run.py /opt/verification/run.py
COPY coding_agent/verification/contract.py /opt/verification/contract.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
WORKDIR /source/backend
ENTRYPOINT ["python", "/opt/verification/run.py"]
