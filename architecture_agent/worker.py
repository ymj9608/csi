"""Pull architecture images from CSI and extract advisory context on local Ollama."""
import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse
import uuid

import httpx
from dotenv import dotenv_values

from coding_agent.private_files import write_private, restrict_private
from .vision import ArchitectureError, DEFAULT_MODEL, MAX_IMAGE_BYTES, PROMPT_VERSION, analyze_image


def lock_worker(stream):
    """Nonblocking process lock on Windows and POSIX; released when the file closes."""
    if os.name == 'nt':
        import msvcrt
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write('0'); stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def backend_url(value):
    parsed = urlparse(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
            or (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}))):
        raise ArchitectureError("HTTPS_BACKEND_REQUIRED")
    return value.rstrip("/")


def client(args):
    token = os.environ.get("CSI_INTERNAL_TOKEN") or dotenv_values(args.env_file).get("CSI_INTERNAL_TOKEN", "")
    if not token or len(token) < 32:
        raise ArchitectureError("INTERNAL_TOKEN_REQUIRED")
    return httpx.Client(base_url=backend_url(args.backend), headers={"Authorization": "Bearer " + token},
                        timeout=20, trust_env=False)


def emit(job_id, status, **fields):
    # Deliberately exclude lease, source image, context, HTTP bodies, and exceptions.
    print(json.dumps({"architectureId": job_id, "status": status, **fields}), flush=True)


class InvalidEnvelope(ValueError):
    """Local corrupt input, distinguished from valid delivery/storage failures."""


def read_envelope(pending):
    try:
        if pending.is_symlink() or not pending.is_file() or pending.stat().st_size > 2_000_000:
            raise ValueError("not a bounded regular file")
        receipt = json.loads(pending.read_text(encoding='utf-8'))
        if not isinstance(receipt, dict) or set(receipt) != {"id", "backend", "kind", "payload"}:
            raise ValueError("invalid envelope")
        job_id = str(uuid.UUID(receipt["id"]))
        if receipt["kind"] not in {"result", "failure"} or pending.name != job_id + ".pending.json":
            raise ValueError("invalid envelope identity")
        backend_url(receipt["backend"])
        payload = receipt["payload"]
        field = "result" if receipt["kind"] == "result" else "errorCode"
        if not isinstance(payload, dict) or set(payload) != {"leaseToken", field}:
            raise ValueError("invalid envelope payload")
        uuid.UUID(payload["leaseToken"])
        if field == "result" and not isinstance(payload[field], dict):
            raise ValueError("invalid result")
        if field == "errorCode" and (not isinstance(payload[field], str) or not re.fullmatch(r"[A-Z_]{1,80}", payload[field])):
            raise ValueError("invalid error code")
        return receipt
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        raise InvalidEnvelope() from exc


def quarantine(pending):
    """Keep corrupt data for inspection once, without reprocessing or logging it."""
    destination = pending.with_name("quarantine-" + uuid.uuid4().hex + ".corrupt")
    if pending.is_symlink():
        # Move the link itself, never read or chmod its possibly external target.
        pending.replace(destination)
    else:
        restrict_private(pending)
        pending.replace(destination)
    emit(None, "LOCAL_RESULT_QUARANTINED", file=destination.name)


def deliver_pending(api, pending):
    """Retry exactly the persisted envelope; never re-run vision after a lost ACK."""
    receipt = read_envelope(pending)
    job_id = receipt["id"]
    kind = receipt["kind"]
    if receipt["backend"] != str(api.base_url):
        return True  # A worker for another backend must not send this result.
    payload = receipt["payload"]
    for attempt in range(1, 4):
        try:
            response = api.post(f"/internal/architectures/{job_id}/{kind}", json=payload)
            response.raise_for_status()
            reply = response.json()
            if not isinstance(reply, dict) or reply.get("status") != ("READY" if kind == "result" else "FAILED"):
                raise ValueError("invalid acknowledgement")
        except (httpx.HTTPError, ValueError) as exc:
            code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            retryable = code is None or code in {408, 429} or code >= 500
            if not retryable:
                write_private(pending.with_name(job_id + ".delivery.json"), {"status": "REJECTED", "httpStatus": code})
                pending.unlink(missing_ok=True)
                emit(job_id, "DELIVERY_REJECTED", httpStatus=code)
                return False
            if attempt < 3:
                emit(job_id, "DELIVERY_RETRYING", attempt=attempt)
                time.sleep(attempt)
                continue
            emit(job_id, "DELIVERY_PENDING")
            return False
        # Persist a lease-free audit receipt before removing the recoverable envelope.
        write_private(pending.with_name(job_id + ".delivery.json"), {"status": reply["status"], "replayed": bool(reply.get("replayed"))})
        pending.unlink(missing_ok=True)
        emit(job_id, reply["status"])
        return True


def resume_deliveries(api, output):
    complete = True
    for pending in sorted(output.glob("*.pending.json")):
        try:
            complete = deliver_pending(api, pending) and complete
        except InvalidEnvelope:
            try:
                quarantine(pending)
            except OSError:
                emit(None, "LOCAL_QUARANTINE_FAILED")
                complete = False
        except OSError:
            # A valid result whose ACK receipt cannot be persisted remains pending.
            emit(None, "LOCAL_DELIVERY_STORAGE_FAILED")
            complete = False
    return complete


def process(api, job, output, ollama_url, model=DEFAULT_MODEL):
    job_id = str(uuid.UUID(job["id"]))
    lease = str(uuid.UUID(job["leaseToken"]))
    kind = "result"
    try:
        if job["model"] != model or job["promptVersion"] != PROMPT_VERSION:
            raise ArchitectureError("MODEL_OR_PROMPT_MISMATCH")
        encoded = job["imageBase64"]
        if not isinstance(encoded, str) or len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
            raise ArchitectureError("IMAGE_SIZE_INVALID")
        try:
            image = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ArchitectureError("IMAGE_ENCODING_INVALID") from exc
        if hashlib.sha256(image).hexdigest() != job["imageSha256"]:
            raise ArchitectureError("IMAGE_DIGEST_MISMATCH")
        result = analyze_image(image, model=model, ollama_url=ollama_url)
        # Store an audit artifact without pixels or credentials before delivery.
        write_private(output / (job_id + ".json"), result)
        payload = {"leaseToken": lease, "result": result}
    except Exception as exc:
        error = str(exc) if isinstance(exc, ArchitectureError) else "LOCAL_STORAGE_FAILED" if isinstance(exc, OSError) else "VISION_WORKER_FAILED"
        kind = "failure"
        payload = {"leaseToken": lease, "errorCode": error}
        emit(job_id, "INFERENCE_FAILED", errorCode=error)
    pending = output / (job_id + ".pending.json")
    # Atomic persistence is the delivery source of truth, including failed inference.
    write_private(pending, {"id": job_id, "backend": str(api.base_url), "kind": kind, "payload": payload})
    return deliver_pending(api, pending) and kind == "result"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--project-id", help="Process the project upload UI diagram queue instead of the legacy context queue")
    selection.add_argument("--repository", help="Resolve the registered project UUID from owner/repository")
    parser.add_argument("--backend", default="http://127.0.0.1:8080")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", help="Defaults to Qwen3-VL for --project-id; legacy context model otherwise")
    parser.add_argument("--output", type=Path, default=Path(".runtime/architecture"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.project_id or args.repository:
        from .diagram_worker import run
        from .extractor import DEFAULT_MODEL as DIAGRAM_MODEL
        args.model = args.model or DIAGRAM_MODEL
        run(args)
        return
    args.model = args.model or DEFAULT_MODEL
    args.output.mkdir(parents=True, exist_ok=True)
    with open(args.output / "worker.lock", "a") as lock, client(args) as api:
        try:
            lock_worker(lock)
        except OSError as exc:
            raise ArchitectureError("WORKER_ALREADY_RUNNING") from exc
        while True:
            try:
                complete = resume_deliveries(api, args.output)
                if complete:
                    response = api.post("/internal/architectures/claim", json={"model": args.model, "promptVersion": PROMPT_VERSION})
                    response.raise_for_status()
                    claim = response.json()
                    if claim["available"]:
                        complete = process(api, claim["job"], args.output, args.ollama_url, args.model)
                if args.once:
                    raise SystemExit(0 if complete else 1)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, OSError):
                emit(None, "WORKER_UNAVAILABLE")
                if args.once:
                    raise SystemExit(1)
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except ArchitectureError as exc:
        raise SystemExit(str(exc))
