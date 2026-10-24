"""The upload queue and legacy durable queue must keep their own API contracts."""
import json
import sys

import httpx

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


def test_repository_resolves_before_claim_without_inference(monkeypatch):
    from argparse import Namespace
    from coding_agent import project_lookup
    claims = []
    monkeypatch.setattr(project_lookup, 'lookup_project', lambda backend, env, repo: 'resolved-id')
    monkeypatch.setattr(diagram_worker, 'client', lambda *_: httpx.Client(base_url='http://localhost:8080'))
    monkeypatch.setattr(diagram_worker, 'run_once', lambda api, project_id, **kw: claims.append(project_id))
    diagram_worker.run(Namespace(backend='http://localhost:8080', env_file='.env', project_id=None,
        repository='org/demo', once=True, model='qwen3-vl:8b', ollama_url='http://localhost:11434'))
    assert claims == ['resolved-id']
