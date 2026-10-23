"""Poll CSI for one project's queued architecture diagram, run it through the
local VLM once, and report the result back. Not a long-running crash-safe
pipeline like coding_agent/worker.py — extraction is a single fast call, so
on failure the diagram just stays QUEUED and the next poll retries it."""
import argparse
import os
import time
import httpx
from dotenv import dotenv_values
from . import extractor


def client(backend, env_file):
    token = os.environ.get("CSI_INTERNAL_TOKEN") or dotenv_values(env_file).get("CSI_INTERNAL_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("CSI_INTERNAL_TOKEN required")
    return httpx.Client(base_url=backend.rstrip("/"), headers={"Authorization": "Bearer " + token}, timeout=30, trust_env=False)


def run_once(api, project_id, ollama_url=extractor.DEFAULT_OLLAMA_URL, model=extractor.DEFAULT_MODEL):
    claim = api.post(f"/internal/projects/{project_id}/architecture/claim")
    if claim.status_code == 204:
        return False
    claim.raise_for_status()
    diagram_id = claim.json()["diagramId"]
    print({"diagramId": diagram_id, "phase": "LOADING_MODEL"}, flush=True)
    api.post(f"/internal/architecture/{diagram_id}/progress", json={"phase": "ANALYZING"}).raise_for_status()
    print({"diagramId": diagram_id, "phase": "ANALYZING"}, flush=True)
    image = api.get(f"/internal/architecture/{diagram_id}/image")
    image.raise_for_status()
    result = extractor.extract(image.content, model=model, ollama_url=ollama_url)
    api.post(f"/internal/architecture/{diagram_id}/result", json=result).raise_for_status()
    print({"diagramId": diagram_id, "phase": "EXTRACTED"}, flush=True)
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backend", default="http://127.0.0.1:8080")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--project-id", required=True)
    p.add_argument("--ollama-url", default=extractor.DEFAULT_OLLAMA_URL)
    p.add_argument("--model", default=extractor.DEFAULT_MODEL)
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    with client(args.backend, args.env_file) as api:
        while True:
            processed = run_once(api, args.project_id, ollama_url=args.ollama_url, model=args.model)
            if args.once:
                return
            if not processed:
                time.sleep(5)


if __name__ == "__main__":
    main()
