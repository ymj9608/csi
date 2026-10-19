"""Scan another local Java/Python project through CSI without claiming a GitHub Push occurred."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from demo import env, login
from scan import scan, snapshot
from submit import submit
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(source, repository, branch='develop', base='http://127.0.0.1:8080', submit_base=None):
    env()
    os.environ['CSI_LOCAL_DEMO'] = '1'
    (ROOT / '.runtime').mkdir(exist_ok=True)
    if Path('/etc/ssl/cert.pem').exists():os.environ.setdefault('SSL_CERT_FILE', '/etc/ssl/cert.pem')
    os.environ.setdefault('SEMGREP_BIN', str(ROOT / '.scanner-venv/bin/semgrep'))
    os.environ.setdefault('SEMGREP_LOG_FILE', str(ROOT / '.runtime/semgrep.log'))
    os.environ.setdefault('SEMGREP_SETTINGS_FILE', str(ROOT / '.runtime/semgrep.yml'))
    source = Path(source).resolve(strict=True)
    # Hash exactly the copied Java/Python sources, not git HEAD (which may omit local edits).
    with tempfile.TemporaryDirectory(prefix='csi-local-source-') as temp:
        copied = Path(temp)
        snapshot(source, copied)
        digest = hashlib.sha1()
        for path in sorted(p for p in copied.rglob('*') if p.is_file()):
            digest.update(str(path.relative_to(copied)).encode() + b'\0' + path.read_bytes() + b'\0')
        findings = scan(copied)
        source_sha = digest.hexdigest()
    client = login(base)
    try:
        response = client.get('/api/projects')
        response.raise_for_status()
        if not any(p['repository'] == repository for p in response.json()):
            response = client.post('/api/projects', json={'repository': repository, 'defaultBranch': branch})
            if response.status_code == 400:
                raise SystemExit('Add the repository to CSI_REPOSITORY_ALLOWLIST and recreate the backend first.')
            response.raise_for_status()
        payload = dict(repository=repository, branch=branch, commitSha=source_sha,
                       workflowRunId=str(time.time_ns()), runAttempt=1, triggerType='LOCAL_DEMO',
                       scannerSuccess=True, findings=findings)
        receipt = submit(payload, submit_base or base, os.environ['CSI_INTEGRATION_SECRET'])
        scan_id = receipt['scanId']
        print(json.dumps({'scanId': scan_id, 'findings': len(findings), 'trigger': 'LOCAL_DEMO',
                          'sourceDigest': source_sha, 'rules': sorted({f['ruleId'] for f in findings})}), flush=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            response = client.get('/api/scans/' + scan_id)
            response.raise_for_status()
            state = response.json()
            if state['status'] in {'COMPLETED', 'FAILED'}:
                print(json.dumps({'scanId': scan_id, 'status': state['status'], 'analysisMode': state.get('analysisMode')}), flush=True)
                if state['status'] != 'COMPLETED':
                    raise SystemExit('CSI analysis failed; inspect Execution Logs.')
                return scan_id
            time.sleep(1)
        raise SystemExit('CSI accepted the scan but did not complete within 180 seconds; inspect Execution Logs.')
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--branch', default='develop')
    parser.add_argument('--base', default='http://127.0.0.1:8080')
    parser.add_argument('--submit-base', help='Optional intake gateway URL; authenticated dashboard queries still use --base')
    args = parser.parse_args()
    run(args.source, args.repository, args.branch, args.base, args.submit_base)
