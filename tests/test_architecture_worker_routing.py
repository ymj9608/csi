"""The upload queue and legacy durable queue must keep their own API contracts."""
import json
import sys

import httpx
import pytest

from architecture_agent import diagram_worker, worker


def test_project_cli_dispatches_to_diagram_worker_with_qwen(monkeypatch):
    received = []
    monkeypatch.setattr(sys, "argv", ["worker", "--project-id", "project", "--once"])
    monkeypatch.setattr(diagram_worker, "run", lambda args: received.append(args))
    monkeypatch.setattr(worker, "client", lambda _: (_ for _ in ()).throw(AssertionError("legacy queue selected")))
    worker.main()
    assert received[0].project_id == "project"
    assert received[0].model == "qwen3-vl:8b"
    assert received[0].once


def test_diagram_worker_claim_image_and_result_contract(monkeypatch):
    calls = []
    result = {"summary": "실습 API", "components": [{"name": "API", "role": "실습", "isolationStatus": "ISOLATED", "state": "OBSERVED"}]}

    def handle(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json={"diagramId": "diagram"})
        if request.url.path.endswith("/image"):
            return httpx.Response(200, content=b"image")
        if request.url.path.endswith("/result"):
            assert json.loads(request.content) == result
        return httpx.Response(200, json={})

    def extract(image, **kwargs):
        assert image == b"image"
        assert kwargs["model"] == "qwen3-vl:8b"
        return result

    monkeypatch.setattr(diagram_worker.extractor, "extract", extract)
    with httpx.Client(base_url="http://localhost:8080", transport=httpx.MockTransport(handle)) as api:
        assert diagram_worker.run_once(api, "project")
    assert calls == [
        ("POST", "/internal/projects/project/architecture/claim"),
        ("POST", "/internal/architecture/diagram/progress"),
        ("GET", "/internal/architecture/diagram/image"),
        ("POST", "/internal/architecture/diagram/result"),
    ]


def test_diagram_empty_queue_does_not_load_model(monkeypatch):
    monkeypatch.setattr(diagram_worker.extractor, "extract", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected inference")))
    with httpx.Client(base_url="http://localhost:8080", transport=httpx.MockTransport(lambda _: httpx.Response(204))) as api:
        assert not diagram_worker.run_once(api, "project")


def test_repository_cli_selects_project_queue_with_qwen(monkeypatch):
    received = []
    monkeypatch.setattr(sys, 'argv', ['worker', '--repository', 'org/demo', '--once'])
    monkeypatch.setattr(diagram_worker, 'run', lambda args: received.append(args))
    worker.main()
    assert received[0].repository == 'org/demo'
    assert received[0].model == 'qwen3-vl:8b'


def test_repository_resolves_before_claim_without_inference(monkeypatch, tmp_path):
    from argparse import Namespace
    from coding_agent import project_lookup
    claims = []
    monkeypatch.setattr(project_lookup, 'lookup_project', lambda backend, env, repo: 'resolved-id')
    monkeypatch.setattr(diagram_worker, 'client', lambda *_: httpx.Client(base_url='http://localhost:8080'))
    monkeypatch.setattr(diagram_worker, 'run_once', lambda api, project_id, **kw: claims.append(project_id))
    diagram_worker.run(Namespace(backend='http://localhost:8080', env_file=str(tmp_path / 'missing.env'), project_id=None,
        repository='org/demo', once=True, model='qwen3-vl:8b', ollama_url='http://localhost:11434'))
    assert claims == ['resolved-id']


@pytest.mark.parametrize('error,code', [
    (httpx.ReadTimeout('private provider details'), 'MODEL_TIMEOUT'),
    (httpx.ConnectError('private connection details'), 'MODEL_UNAVAILABLE'),
    (ValueError('private malformed output'), 'INVALID_RESULT'),
    (RuntimeError('private unexpected error'), 'WORKER_ERROR'),
])
def test_analysis_failure_is_reported_without_private_details(monkeypatch, capsys, error, code):
    posted = []
    def handle(request):
        if request.url.path.endswith('/claim'):
            return httpx.Response(200, json={'diagramId': 'diagram'})
        if request.url.path.endswith('/failure'):
            posted.append(json.loads(request.content))
        return httpx.Response(200, json={})
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(diagram_worker.extractor, 'extract', fail)
    with httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(handle)) as api:
        assert diagram_worker.run_once(api, 'project')
    assert posted == [{'errorCode': code}]
    assert 'private' not in capsys.readouterr().out


def test_failure_delivery_retries_backend_outage_without_reinference(monkeypatch):
    attempts = []
    inference = []
    monkeypatch.setattr(diagram_worker.time, 'sleep', lambda _: None)
    def fail(*args, **kwargs):
        inference.append(True)
        raise ValueError('invalid')
    monkeypatch.setattr(diagram_worker.extractor, 'extract', fail)
    def handle(request):
        if request.url.path.endswith('/claim'):
            return httpx.Response(200, json={'diagramId': 'diagram'})
        if request.url.path.endswith('/failure'):
            attempts.append(request.content)
            return httpx.Response(503 if len(attempts) < 3 else 200, json={})
        return httpx.Response(200, json={})
    with httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(handle)) as api:
        assert diagram_worker.run_once(api, 'project')
    assert len(inference) == 1 and len(attempts) == 3
    assert len(set(attempts)) == 1


def test_unavailable_failure_delivery_is_bounded_and_leaves_expiry_to_backend(monkeypatch, capsys):
    monkeypatch.setattr(diagram_worker.time, 'sleep', lambda _: None)
    requests = []
    def unavailable(request):
        requests.append(request)
        raise httpx.ConnectError('private', request=request)
    with httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(unavailable)) as api:
        assert not diagram_worker.report_failure(api, 'diagram', 'WORKER_ERROR')
    assert len(requests) == 3
    out = capsys.readouterr().out
    assert 'FAILURE_DELIVERY_PENDING_EXPIRY' in out and 'private' not in out


def test_late_result_failure_does_not_retry_or_replace_finished_job(monkeypatch):
    paths = []
    monkeypatch.setattr(diagram_worker.extractor, 'extract', lambda *a, **kw: {'summary': 'done', 'components': []})
    def handle(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/claim'):
            return httpx.Response(200, json={'diagramId': 'old-diagram'})
        if request.url.path.endswith(('/result', '/failure')):
            return httpx.Response(409, json={})
        return httpx.Response(200, json={})
    with httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(handle)) as api:
        assert diagram_worker.run_once(api, 'project')
    assert paths.count('/internal/architecture/old-diagram/result') == 1
    assert paths.count('/internal/architecture/old-diagram/failure') == 1
