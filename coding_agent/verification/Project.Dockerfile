FROM csi-coding-verifier:local
COPY coding_agent/verification/project_runner.py coding_agent/verification/project_plugin.py /opt/verification/
ENTRYPOINT ["python", "/opt/verification/project_runner.py"]
