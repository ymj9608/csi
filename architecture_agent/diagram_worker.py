"""Process the upload UI's project diagram queue.

This API is separate from the legacy durable context queue. Report safe failure
codes immediately; the backend expires abandoned jobs if delivery is unavailable.
"""
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


def report_failure(api, diagram_id, code):
    for attempt in range(3):
        try:
            response = api.post(f"/internal/architecture/{diagram_id}/failure", json={"errorCode": code})
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                break  # Deleted/replaced/finished jobs must never be overwritten.
        except httpx.RequestError:
            pass
        if attempt < 2:
            time.sleep(1)
    print({"diagramId": diagram_id, "event": "FAILURE_DELIVERY_PENDING_EXPIRY"}, flush=True)
    return False


def run_once(api, project_id, ollama_url=extractor.DEFAULT_OLLAMA_URL, model=extractor.DEFAULT_MODEL):
    claim = api.post(f"/internal/projects/{project_id}/architecture/claim")
    if claim.status_code == 204:
        return False
    claim.raise_for_status()
    diagram_id = claim.json()["diagramId"]
    print({"diagramId": diagram_id, "phase": "LOADING_MODEL"}, flush=True)
    stage = "BACKEND"
    try:
        api.post(f"/internal/architecture/{diagram_id}/progress", json={"phase": "ANALYZING"}).raise_for_status()
        print({"diagramId": diagram_id, "phase": "ANALYZING"}, flush=True)
        image = api.get(f"/internal/architecture/{diagram_id}/image")
        image.raise_for_status()
        stage = "INFERENCE"
        result = extractor.extract(image.content, model=model, ollama_url=ollama_url)
        stage = "BACKEND"
        api.post(f"/internal/architecture/{diagram_id}/result", json=result).raise_for_status()
    except Exception as exc:
        if isinstance(exc, httpx.TimeoutException):
            code = "MODEL_TIMEOUT" if stage == "INFERENCE" else "BACKEND_UNAVAILABLE"
        elif isinstance(exc, httpx.HTTPError):
            code = "MODEL_UNAVAILABLE" if stage == "INFERENCE" else "BACKEND_UNAVAILABLE"
        elif isinstance(exc, (ValueError, KeyError, TypeError)) and stage == "INFERENCE":
            code = "INVALID_RESULT"
        else:
            code = "WORKER_ERROR"
        # Never publish exception messages, image bytes or provider response bodies.
        delivered = report_failure(api, diagram_id, code)
        print({"diagramId": diagram_id, "event": "ANALYSIS_FAILED", "errorCode": code,
               "failureReported": delivered}, flush=True)
        return True
    print({"diagramId": diagram_id, "phase": "EXTRACTED"}, flush=True)
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backend", default="http://127.0.0.1:8080")
    p.add_argument("--env-file", default=".env")
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument("--project-id")
    selection.add_argument("--repository")
    p.add_argument("--ollama-url", default=extractor.DEFAULT_OLLAMA_URL)
    p.add_argument("--model", default=extractor.DEFAULT_MODEL)
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    run(args)


def run(args):
    from .worker import backend_url
    from coding_agent.runtime_settings import load_environment
    load_environment(dotenv_values(args.env_file))
    backend = backend_url(args.backend)
    project_id = args.project_id
    if getattr(args, 'repository', None):
        from coding_agent.project_lookup import lookup_project
        project_id = lookup_project(backend, args.env_file, args.repository)
        print({'repository': args.repository, 'projectId': project_id}, flush=True)
    with client(backend, args.env_file) as api:
        while True:
            try:
                processed = run_once(api, project_id, ollama_url=args.ollama_url, model=args.model)
            except httpx.HTTPError:
                print({"event": "ARCHITECTURE_BACKEND_UNAVAILABLE"}, flush=True)
                if args.once:
                    raise SystemExit("ARCHITECTURE_BACKEND_UNAVAILABLE") from None
                processed = False
            if args.once:
                return
            if not processed:
                time.sleep(5)


if __name__ == "__main__":
    main()
