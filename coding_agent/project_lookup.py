"""Resolve registered projects by repository, without caching resettable UUIDs."""
from uuid import UUID

import httpx
from dotenv import dotenv_values


def login(api, env_file):
    cfg = dotenv_values(env_file)
    api.headers['X-CSRF-TOKEN'] = api.get('/api/auth/csrf').json()['token']
    response = api.post('/api/auth/login', json={
        'username': cfg.get('CSI_ADMIN_USERNAME', 'reviewer'),
        'password': cfg['CSI_ADMIN_PASSWORD'],
    })
    response.raise_for_status()
    api.headers['X-CSRF-TOKEN'] = api.get('/api/auth/csrf').json()['token']


def resolve_project(api, repository, project_id=None):
    response = api.get('/api/projects')
    response.raise_for_status()
    matches = [p for p in response.json() if p.get('repository', '').casefold() == repository.casefold()]
    if not matches:
        raise ValueError(f'PROJECT_NOT_REGISTERED: register {repository} in CSI first')
    if len(matches) != 1:
        raise ValueError(f'PROJECT_AMBIGUOUS: multiple projects match {repository}')
    resolved = str(UUID(matches[0]['id']))
    if project_id is not None and str(UUID(project_id)) != resolved:
        raise ValueError('PROJECT_REPOSITORY_MISMATCH: UUID does not match the profile repository')
    return resolved


def lookup_project(backend, env_file, repository):
    # Caller validates the backend URL before credentials are sent.
    with httpx.Client(base_url=backend, timeout=30, trust_env=False) as api:
        login(api, env_file)
        return resolve_project(api, repository)
