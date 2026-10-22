import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath

class Rejected(ValueError):
    def __init__(self, code, details=None):
        super().__init__(code)
        self.details = details or {}

def git(repo, *args, timeout=20):
    p = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-C', str(repo), *args], capture_output=True, timeout=timeout)
    if p.returncode:
        raise Rejected('COMMIT_OR_SOURCE_UNAVAILABLE')
    return p.stdout

def commit(repo, sha):
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise Rejected('EXACT_GIT_COMMIT_REQUIRED')
    if git(repo, 'rev-parse', '--verify', sha+'^{commit}').decode().strip() != sha:
        raise Rejected('EXACT_GIT_COMMIT_REQUIRED')
    return sha

def read(repo, sha, path):
    if path.startswith('/') or '..' in PurePosixPath(path).parts or not re.fullmatch(r'[A-Za-z0-9_./-]+', path):
        raise Rejected('SOURCE_PATH')
    meta = git(repo, 'ls-tree', sha, '--', path).decode().split()
    if len(meta) < 3 or meta[0] not in {'100644', '100755'} or meta[1] != 'blob':
        raise Rejected('REGULAR_SOURCE_FILE_REQUIRED')
    if int(git(repo, 'cat-file', '-s', meta[2])) > 200_000:
        raise Rejected('SOURCE_TOO_LARGE')
    return git(repo, 'cat-file', 'blob', meta[2]).decode('utf-8')

def digest(content):
    return hashlib.sha256(content.encode()).hexdigest()

def snapshot(repo, sha, destination):
    """Export only application/test Python and the API contract. Never .env, .git or hooks."""
    total = 0
    for raw in git(repo, 'ls-tree', '-rz', '--full-tree', sha).split(b'\0'):
        if not raw:
            continue
        meta, name = raw.split(b'\t', 1)
        path = name.decode('utf-8')
        selected = (path.startswith(('backend/app/', 'backend/tests/')) and path.endswith('.py')) or path in {
            'backend/pytest.ini', 'docs/CLASS_NAME_Lichu-API.yml'}
        if not selected:
            continue
        content = read(repo, sha, path)
        total += len(content.encode())
        if total > 5_000_000:
            raise Rejected('SNAPSHOT_TOO_LARGE')
        target = Path(destination)/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
