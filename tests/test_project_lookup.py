import httpx
import pytest

from coding_agent.project_lookup import resolve_project

FIRST = '00000000-0000-4000-8000-000000000001'
SECOND = '00000000-0000-4000-8000-000000000002'


def client(rows):
    def handle(request):
        assert request.method == 'GET'
        assert request.url.path == '/api/projects'
        return httpx.Response(200, json=rows)
    return httpx.Client(base_url='http://localhost:8080', transport=httpx.MockTransport(handle))


def test_resolves_repository_not_first_project_and_refreshes_after_reset():
    rows = [{'id': FIRST, 'repository': 'org/other'}, {'id': SECOND, 'repository': 'org/demo'}]
    with client(rows) as api:
        assert resolve_project(api, 'org/demo') == SECOND
        rows[:] = [{'id': FIRST, 'repository': 'org/demo'}]
        assert resolve_project(api, 'org/demo') == FIRST


@pytest.mark.parametrize('rows,error', [
    ([], 'PROJECT_NOT_REGISTERED'),
    ([{'id': FIRST, 'repository': 'org/demo'}, {'id': SECOND, 'repository': 'ORG/DEMO'}], 'PROJECT_AMBIGUOUS'),
])
def test_missing_or_ambiguous_project_fails_without_mutations(rows, error):
    with client(rows) as api, pytest.raises(ValueError, match=error):
        resolve_project(api, 'org/demo')


def test_explicit_uuid_must_match_profile_repository():
    with client([{'id': FIRST, 'repository': 'org/demo'}]) as api:
        assert resolve_project(api, 'org/demo', FIRST) == FIRST
        with pytest.raises(ValueError, match='PROJECT_REPOSITORY_MISMATCH'):
            resolve_project(api, 'org/demo', SECOND)
