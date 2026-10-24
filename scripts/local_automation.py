"""Attach operator-prepared profiles and run queued image extraction locally.

Never creates scans/coding proposals, approves patches, or sends Slack messages.
Only repositories explicitly configured with a prepared profile are managed.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import UUID

import httpx
from dotenv import dotenv_values

from architecture_agent.worker import lock_worker
from coding_agent.project_lookup import login
from coding_agent.worker import backend_url
from scripts.register_verification_profile import activate_prepared, read_prepared

ROOT = Path(__file__).resolve().parents[1]


def emit(event, **fields):
    print(json.dumps({'event': event, **fields}), flush=True)


def load_profiles(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    profiles = {}
    for path in config['preparedProfiles']:
        prepared = read_prepared(config_path.parent / path)
        repository = prepared['config']['repository']
        if repository in profiles:
            raise ValueError('DUPLICATE_REPOSITORY_PROFILE')
        profiles[repository] = prepared
    return profiles


class Automation:
    def __init__(self, api, worker, profiles, launch):
        self.api, self.worker, self.profiles, self.launch = api, worker, profiles, launch
        self.child = None
        self.child_project = None
        self.reported = {}

    def tick(self):
        response = self.api.get('/api/projects')
        response.raise_for_status()
        projects = response.json()
        ids = {p['id'] for p in projects}
        if self.child:
            if self.child.poll() is not None:
                emit('ARCHITECTURE_WORKER_EXIT', projectId=self.child_project, exitCode=self.child.returncode)
                self.child = None
            elif self.child_project not in ids:
                self.close()
        for project in projects:
            prepared = self.profiles.get(project['repository'])
            if prepared is None:
                continue
            project_id = str(UUID(project['id']))
            try:
                result = activate_prepared(self.api, self.worker, project_id, prepared, preserve_active=True)
                signature = (result['status'], result['version'])
                if self.reported.get(project_id) != signature:
                    emit('PROFILE_SETUP', **result)
                    self.reported[project_id] = signature
                if self.child is not None:
                    continue
                response = self.api.get(f'/api/projects/{project_id}/architecture')
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                if response.json().get('status') == 'QUEUED':
                    self.child = self.launch(project_id)
                    self.child_project = project_id
                    emit('ARCHITECTURE_WORKER_STARTED', projectId=project_id, pid=self.child.pid)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {401, 403}:
                    raise
                emit('PROJECT_SETUP_FAILED', projectId=project_id, httpStatus=exc.response.status_code)
        self.reported = {k: v for k, v in self.reported.items() if k in ids}

    def close(self):
        if self.child is not None:
            if self.child.poll() is None:
                if os.name == 'nt':
                    # Windows venv launchers may own a second Python process.
                    subprocess.run(['taskkill', '/PID', str(self.child.pid), '/T', '/F'],
                                   capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    self.child.terminate()
                try:
                    self.child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=5)
            self.child = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--backend', default='http://127.0.0.1:8080')
    parser.add_argument('--output', type=Path, default=ROOT / '.runtime/local-automation')
    parser.add_argument('--interval', type=float, default=5)
    args = parser.parse_args()
    if args.interval < 1:
        parser.error('--interval must be at least 1 second')
    cfg = dotenv_values(args.env_file)
    configured = args.config or cfg.get('CSI_LOCAL_AUTOMATION_CONFIG')
    if not configured:
        parser.error('Set --config or CSI_LOCAL_AUTOMATION_CONFIG')
    config_path = ROOT / configured
    profiles = load_profiles(config_path)
    backend = backend_url(args.backend)
    token = cfg.get('CSI_INTERNAL_TOKEN', '')
    if len(token) < 32:
        parser.error('CSI_INTERNAL_TOKEN required')
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'service.lock').open('a') as lock:
        try:
            lock_worker(lock)
        except OSError:
            emit('AUTOMATION_ALREADY_RUNNING')
            return
        (args.output / 'service.pid').write_text(str(os.getpid()), encoding='utf-8')
        def launch(project):
            # UUIDs only in filenames; never run commands supplied by a project.
            command = [sys.executable, '-m', 'architecture_agent.worker', '--project-id', project,
                       '--backend', backend, '--env-file', str(args.env_file.resolve()), '--once']
            env = os.environ.copy() | {'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'}
            with (args.output / f'architecture-{project}.log').open('ab') as log:
                return subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        with httpx.Client(base_url=backend, timeout=30, trust_env=False) as api, httpx.Client(
                base_url=backend, timeout=30, trust_env=False, headers={'Authorization': 'Bearer ' + token}) as worker:
            automation = Automation(api, worker, profiles, launch)
            authenticated = False
            emit('AUTOMATION_STARTED', repositories=sorted(profiles))
            try:
                while True:
                    try:
                        if not authenticated:
                            login(api, args.env_file)
                            authenticated = True
                        automation.tick()
                    except httpx.HTTPError as exc:
                        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {401, 403}:
                            authenticated = False
                        emit('AUTOMATION_BACKEND_UNAVAILABLE', errorType=type(exc).__name__)
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                pass
            finally:
                automation.close()


if __name__ == '__main__':
    main()
