"""Advisory vision extraction and durable delivery; never calls a live model."""
import base64
import copy
import hashlib
import json
import stat
import struct

import httpx
import pytest

from architecture_agent import vision, worker
from architecture_agent.vision import ArchitectureError


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=")
JOB_ID = "11111111-1111-4111-8111-111111111111"
LEASE = "22222222-2222-4222-8222-222222222222"
CONTEXT = {
    "diagramType": "ARCHITECTURE",
    "components": [{"id": "api", "label": "API", "kind": "backend"}, {"id": "db", "label": "DB", "kind": "database"}],
    "flows": [{"from": "api", "to": "db", "data": "UNKNOWN", "protection": "UNKNOWN"}],
    "trustBoundaries": [], "codeHints": ["backend/app/main.py"], "assumptions": [],
    "uncertainties": ["저장 암호화는 그림에서 확인할 수 없습니다."], "summary": "API와 데이터베이스 연결을 보여주는 구조도입니다.",
}
METRICS = {"prompt_eval_count": 1000, "eval_count": 200, "total_duration": 3_000_000,
           "load_duration": 500_000, "prompt_eval_duration": 1_000_000, "eval_duration": 1_500_000}
RESULT = {"schemaVersion": 1, "imageSha256": hashlib.sha256(PNG).hexdigest(), "model": vision.DEFAULT_MODEL,
          "promptVersion": vision.PROMPT_VERSION, **CONTEXT, "metrics": {**METRICS, "wallDurationMs": 42.0}}
JOB = {"id": JOB_ID, "leaseToken": LEASE, "model": vision.DEFAULT_MODEL, "promptVersion": vision.PROMPT_VERSION,
       "imageBase64": base64.b64encode(PNG).decode(), "imageSha256": hashlib.sha256(PNG).hexdigest()}


def transport(raw=None, capabilities=None):
    def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": capabilities if capabilities is not None else ["completion", "vision"]})
        assert request.url.host in {"localhost", "127.0.0.1"}
        body = json.loads(request.content)
        assert body["messages"][1]["images"] == [JOB["imageBase64"]]
        assert body["think"] is False and body["stream"] is False
        assert "UNTRUSTED DATA" in body["messages"][0]["content"]
        return httpx.Response(200, json=raw if raw is not None else {
            "done": True, "done_reason": "stop", "message": {"content": json.dumps(CONTEXT)}, **METRICS})
    return httpx.MockTransport(handle)


def test_extraction_preserves_real_usage_and_separates_unknowns():
    result = vision.analyze_image(PNG, transport=transport())
    assert result["imageSha256"] == JOB["imageSha256"]
    assert result["diagramType"] == "ARCHITECTURE"
    assert result["flows"][0]["protection"] == "UNKNOWN"
    assert {key: result["metrics"][key] for key in METRICS} == METRICS
    assert result["metrics"]["wallDurationMs"] >= 0
    assert "prompt_eval_cached_count" not in result["metrics"]


def test_reported_cache_usage_is_preserved_not_assumed():
    raw = {"done": True, "done_reason": "stop", "message": {"content": json.dumps(CONTEXT)},
           **METRICS, "prompt_eval_cached_count": 100}
    assert vision.analyze_image(PNG, transport=transport(raw))["metrics"]["prompt_eval_cached_count"] == 100


def test_nonvision_model_fails_before_chat():
    with pytest.raises(ArchitectureError, match="MODEL_VISION_UNSUPPORTED"):
        vision.analyze_image(PNG, transport=transport(capabilities=["completion"]))


@pytest.mark.parametrize("raw", [
    {"done": False},
    {"done": True, "done_reason": "length", "message": {"content": json.dumps(CONTEXT)}, **METRICS},
])
def test_truncated_generation_cannot_become_ready(raw):
    with pytest.raises(ArchitectureError, match="VISION_OUTPUT_INCOMPLETE"):
        vision.analyze_image(PNG, transport=transport(raw))


def test_missing_usage_is_not_reported_as_zero():
    raw = {"done": True, "done_reason": "stop", "message": {"content": json.dumps(CONTEXT)}}
    with pytest.raises(ArchitectureError, match="VISION_USAGE_MISSING"):
        vision.analyze_image(PNG, transport=transport(raw))


def test_timeout_is_safe_code():
    def timeout(request):
        raise httpx.ReadTimeout("private image and credentials must not appear", request=request)
    with pytest.raises(ArchitectureError, match="^VISION_TIMEOUT$"):
        vision.analyze_image(PNG, transport=httpx.MockTransport(timeout))


@pytest.mark.parametrize("url", ["https://external.example", "http://evil.example:11434", "http://user:password@localhost:11434", "http://localhost:11434?token=secret"])
def test_extractor_only_uses_local_ollama(url):
    with pytest.raises(ArchitectureError, match="LOCAL_OLLAMA_URL_REQUIRED"):
        vision.analyze_image(PNG, ollama_url=url, transport=transport())


@pytest.mark.parametrize("hint", ["../.env", "/etc/passwd", "C:/secrets", "foo/../../.env", "https://example.com", "foo\\bar", "~/private"])
def test_untrusted_code_hints_cannot_escape_manifest(hint):
    context = {**CONTEXT, "codeHints": [hint]}
    with pytest.raises(ArchitectureError, match="CONTEXT_PATH_HINT_INVALID"):
        vision.validate_context(context)


def test_unknown_flow_target_and_duplicate_ids_are_rejected():
    context = copy.deepcopy(CONTEXT)
    context["flows"][0]["to"] = "invented"
    with pytest.raises(ArchitectureError, match="CONTEXT_FLOW_REFERENCE_INVALID"):
        vision.validate_context(context)
    context = copy.deepcopy(CONTEXT)
    context["components"][1]["id"] = "api"
    with pytest.raises(ArchitectureError, match="CONTEXT_COMPONENT_ID_INVALID"):
        vision.validate_context(context)


def test_extra_security_verdict_is_rejected():
    with pytest.raises(ArchitectureError, match="CONTEXT_SCHEMA_INVALID"):
        vision.validate_context({**CONTEXT, "secure": True})


def test_image_limits_are_checked_before_encoding_or_network(monkeypatch):
    monkeypatch.setattr(vision, "MAX_IMAGE_BYTES", 20)
    with pytest.raises(ArchitectureError, match="IMAGE_SIZE_INVALID"):
        vision.analyze_image(PNG, transport=httpx.MockTransport(lambda _: pytest.fail("network must not run")))
    with pytest.raises(ArchitectureError, match="IMAGE_FORMAT_OR_DIMENSIONS_INVALID"):
        vision.image_dimensions(b"<svg>unsafe</svg>")


def test_dimensions_are_bounded():
    assert vision.image_dimensions(PNG) == (1, 1)
    excessive = PNG[:16] + struct.pack(">II", 9000, 9000) + PNG[24:]
    with pytest.raises(ArchitectureError, match="IMAGE_FORMAT_OR_DIMENSIONS_INVALID"):
        vision.image_dimensions(excessive)


def api(handler):
    return httpx.Client(base_url="http://localhost:8080", transport=httpx.MockTransport(handler))


@pytest.fixture
def inference(monkeypatch):
    calls = []
    def analyze(*args, **kwargs):
        calls.append((args, kwargs))
        return RESULT.copy()
    monkeypatch.setattr(worker, "analyze_image", analyze)
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)
    return calls


def test_lost_ack_replays_identical_result_without_reinference(inference, tmp_path):
    requests = []
    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("ACK lost", request=request)
        return httpx.Response(200, json={"status": "READY", "replayed": True})
    assert worker.process(api(handle), JOB, tmp_path, "http://localhost:11434")
    assert len(inference) == 1 and len(requests) == 2
    assert requests[0].content == requests[1].content
    assert all(request.url.path.endswith("/result") for request in requests)
    assert not list(tmp_path.glob("*.pending.json"))
    assert stat.S_IMODE((tmp_path / (JOB_ID + ".json")).stat().st_mode) == 0o600


def test_backend_outage_restart_recovers_without_inference(inference, tmp_path, capsys):
    assert not worker.process(api(lambda _: httpx.Response(503)), JOB, tmp_path, "http://localhost:11434")
    pending = tmp_path / (JOB_ID + ".pending.json")
    assert stat.S_IMODE(pending.stat().st_mode) == 0o600
    deliveries = []
    def handle(request):
        deliveries.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "READY"})
    assert worker.resume_deliveries(api(handle), tmp_path)
    assert deliveries == [{"leaseToken": LEASE, "result": RESULT}]
    assert len(inference) == 1 and not pending.exists()
    output = capsys.readouterr().out
    assert LEASE not in output and JOB["imageBase64"] not in output and CONTEXT["summary"] not in output


def test_pending_result_cannot_be_delivered_to_another_backend(inference, tmp_path):
    worker.process(api(lambda _: httpx.Response(503)), JOB, tmp_path, "http://localhost:11434")
    client = api(lambda _: pytest.fail("wrong backend"))
    client.base_url = "http://localhost:8081"
    assert worker.resume_deliveries(client, tmp_path)
    assert (tmp_path / (JOB_ID + ".pending.json")).exists()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 413])
def test_permanent_rejection_never_overwrites_job_with_failure(inference, tmp_path, status):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(status)
    assert not worker.process(api(handle), JOB, tmp_path, "http://localhost:11434")
    assert len(requests) == 1 and requests[0].url.path.endswith("/result")
    assert not list(tmp_path.glob("*.pending.json"))
    assert json.loads((tmp_path / (JOB_ID + ".delivery.json")).read_text())["httpStatus"] == status


def test_digest_mismatch_never_calls_model_and_reports_failure(inference, tmp_path):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "FAILED"})
    assert not worker.process(api(handle), {**JOB, "imageSha256": "0" * 64}, tmp_path, "http://localhost:11434")
    assert not inference
    assert requests[0].url.path.endswith("/failure")
    assert json.loads(requests[0].content)["errorCode"] == "IMAGE_DIGEST_MISMATCH"


def test_failed_inference_delivery_is_also_durable(inference, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise ArchitectureError("VISION_TIMEOUT")
    monkeypatch.setattr(worker, "analyze_image", fail)
    assert not worker.process(api(lambda _: httpx.Response(503)), JOB, tmp_path, "http://localhost:11434")
    deliveries = []
    def handle(request):
        deliveries.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"status": "FAILED", "replayed": True})
    assert worker.resume_deliveries(api(handle), tmp_path)
    assert deliveries == [(f"/internal/architectures/{JOB_ID}/failure", {"leaseToken": LEASE, "errorCode": "VISION_TIMEOUT"})]


def test_corrupt_local_receipt_does_not_transmit_private_data(tmp_path, capsys):
    pending = tmp_path / (JOB_ID + ".pending.json")
    pending.write_text("PRIVATE_CORRUPTED_DATA")
    assert worker.resume_deliveries(api(lambda _: pytest.fail("corrupt payload sent")), tmp_path)
    quarantined = list(tmp_path.glob("*.corrupt"))
    assert len(quarantined) == 1 and not pending.exists()
    assert quarantined[0].read_text() == "PRIVATE_CORRUPTED_DATA"
    assert stat.S_IMODE(quarantined[0].stat().st_mode) == 0o600
    diagnostic = json.loads(capsys.readouterr().out)
    assert diagnostic["status"] == "LOCAL_RESULT_QUARANTINED"
    assert diagnostic["file"] == quarantined[0].name
    assert "PRIVATE_CORRUPTED_DATA" not in json.dumps(diagnostic)
    # A later loop ignores quarantine files, so new claims can proceed.
    assert worker.resume_deliveries(api(lambda _: pytest.fail("quarantine must not retry")), tmp_path)
    assert capsys.readouterr().out == ""


def test_corrupt_and_healthy_pending_deliveries_do_not_block_each_other(inference, tmp_path, capsys):
    worker.process(api(lambda _: httpx.Response(503)), JOB, tmp_path, "http://localhost:11434")
    (tmp_path / "0_PRIVATE_FILENAME.pending.json").write_text(json.dumps({"payload": LEASE}))
    deliveries = []
    def handle(request):
        deliveries.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "READY"})
    assert worker.resume_deliveries(api(handle), tmp_path)
    assert deliveries == [{"leaseToken": LEASE, "result": RESULT}]
    assert len(inference) == 1 and not list(tmp_path.glob("*.pending.json"))
    assert len(list(tmp_path.glob("*.corrupt"))) == 1
    logs = capsys.readouterr().out
    assert LEASE not in logs and "PRIVATE_FILENAME" not in logs


def test_corruption_does_not_mask_real_backend_outage(inference, tmp_path):
    worker.process(api(lambda _: httpx.Response(503)), JOB, tmp_path, "http://localhost:11434")
    (tmp_path / "0.invalid.pending.json").write_text("corrupt")
    assert not worker.resume_deliveries(api(lambda _: httpx.Response(503)), tmp_path)
    assert (tmp_path / (JOB_ID + ".pending.json")).exists()
    assert len(list(tmp_path.glob("*.corrupt"))) == 1


def test_ack_storage_failure_keeps_valid_pending_instead_of_quarantining(inference, tmp_path, monkeypatch):
    worker.process(api(lambda _: httpx.Response(503)), JOB, tmp_path, "http://localhost:11434")
    def unavailable_storage(*args, **kwargs):
        raise OSError("storage unavailable")
    monkeypatch.setattr(worker, "write_private", unavailable_storage)
    assert not worker.resume_deliveries(api(lambda _: httpx.Response(200, json={"status": "READY"})), tmp_path)
    assert (tmp_path / (JOB_ID + ".pending.json")).exists()
    assert not list(tmp_path.glob("*.corrupt"))


def test_quarantine_cannot_follow_symlink_outside_output(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("PRIVATE_TARGET")
    original_mode = outside.stat().st_mode
    pending = tmp_path / (JOB_ID + ".pending.json")
    pending.symlink_to(outside)
    assert worker.resume_deliveries(api(lambda _: pytest.fail("symlink target sent")), tmp_path)
    assert outside.read_text() == "PRIVATE_TARGET" and outside.stat().st_mode == original_mode
    assert not pending.is_symlink()
    assert list(tmp_path.glob("*.corrupt"))[0].is_symlink()
