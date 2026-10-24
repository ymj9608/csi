"""No real models: check setup, ownership, and queue dispatch using API contracts."""
import httpx
import pytest

from scripts.local_automation import Automation
from scripts.register_verification_profile import activate_prepared

P1 = '00000000-0000-4000-8000-000000000001'
P2 = '00000000-0000-4000-8000-000000000002'
PREPARED = {'config': {'repository': 'org/demo', 'inventory': ['test']}, 'configDigest': 'digest'}


class Child:
    pid = 123
    returncode = None

    def poll(self):
        return self.returncode


class Server:
    def __init__(self):
        self.projects = [{'id': P1, 'repository': 'org/demo'}, {'id': P2, 'repository': 'org/other'}]
        self.active = {}
        self.diagram = {}
        self.calls = []
        self.fail_validation = False

    def handle(self, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if path == '/api/projects':
            return httpx.Response(200, json=self.projects)
        project = path.split('/')[3]
        if path.endswith('/coding-capabilities'):
            return httpx.Response(200, json={'profile': self.active.get(project)})
        if path.endswith('/verification-profiles'):
            return httpx.Response(200, json={'version': 1})
        if path.endswith('/validate'):
            assert request.headers['Authorization'] == 'Bearer worker-test'
            assert 'cookie' not in request.headers
            return httpx.Response(400 if self.fail_validation else 200, json={})
        if path.endswith('/activate'):
            assert 'Authorization' not in request.headers
            self.active[project] = {'configDigest': 'digest', 'version': 1}
            return httpx.Response(200, json={})
        if path.endswith('/architecture'):
            return httpx.Response(200, json={'status': self.diagram[project]}) if project in self.diagram else httpx.Response(404)
        raise AssertionError(path)


@pytest.fixture
def service():
    server = Server()
    transport = httpx.MockTransport(server.handle)
    launched = []
    def launch(project):
        launched.append(project)
        server.diagram[project] = 'ANALYZING'
        return Child()
    with httpx.Client(base_url='http://localhost:8080', transport=transport) as api, httpx.Client(
            base_url='http://localhost:8080', transport=transport, headers={'Authorization': 'Bearer worker-test'}) as worker:
        yield server, Automation(api, worker, {'org/demo': PREPARED}, launch), launched


def test_setup_is_idempotent_and_only_configured_repository(service):
    server, automation, launched = service
    automation.tick()
    automation.tick()
    assert list(server.active) == [P1]
    assert len([p for method, p in server.calls if method == 'POST']) == 3
    assert not launched


def test_existing_different_profile_is_not_overwritten(service):
    server, automation, _ = service
    server.active[P1] = {'configDigest': 'operator-selected-profile', 'version': 2}
    automation.tick()
    assert not any(method == 'POST' for method, _ in server.calls)
    assert server.active[P1]['version'] == 2


def test_reset_and_registration_rebind_to_new_id(service):
    server, automation, _ = service
    automation.tick()
    server.projects = []
    automation.tick()
    server.projects = [{'id': P2, 'repository': 'org/demo'}]
    automation.tick()
    assert P2 in server.active
    assert P1 not in automation.reported


def test_queued_upload_starts_only_one_worker_and_never_coding(service):
    server, automation, launched = service
    server.diagram[P1] = 'QUEUED'
    automation.tick()
    automation.tick()
    assert launched == [P1]
    automation.child.returncode = 0
    server.diagram[P1] = 'EXTRACTED'
    automation.tick()
    assert launched == [P1]
    assert not any('/coding-proposals' in path for _, path in server.calls)


def test_failed_worker_is_not_retried_while_claimed(service):
    server, automation, launched = service
    server.diagram[P1] = 'QUEUED'
    automation.tick()
    automation.child.returncode = 1
    automation.tick()
    assert launched == [P1]


def test_validation_failure_never_activates_or_starts_worker(service):
    server, automation, launched = service
    server.fail_validation = True
    server.diagram[P1] = 'QUEUED'
    automation.tick()
    assert not server.active and not launched
    assert not any(path.endswith('/activate') for _, path in server.calls)
