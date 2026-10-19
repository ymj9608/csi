FROM python:3.11-slim
WORKDIR /app
COPY rules/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY rules /app/rules
COPY scripts/scan.py /app/scripts/scan.py
ENV SEMGREP_LOG_FILE=/tmp/semgrep.log SEMGREP_SETTINGS_FILE=/tmp/semgrep.yml SEMGREP_SEND_METRICS=off
USER 65532:65532
ENTRYPOINT ["python","/app/scripts/scan.py","/target","--output","/output/findings.json"]
