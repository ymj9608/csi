"""Python/pytest adapter: pinned snapshots, trusted driver/pack and Docker execution."""
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from .project_verification import ROOT, fingerprint
from .repository import Rejected, digest


def verify(tree, profile):
    working = tree/profile['runtime']['workingDirectory']
    if digest((ROOT/'verification/privacy_pack.py').read_text(encoding='utf-8')) != profile['pack']['sha256'] or digest((ROOT/profile['driver']['path']).read_text(encoding='utf-8')) != profile['driver']['sha256']:
        raise Rejected('VERIFIER_BINDING_CHANGED')
    for source, target in [(ROOT/'verification/privacy_pack.py', working/'tests/test_csi_privacy_pack.py'),
                           (ROOT/profile['driver']['path'], working/'csi_project_driver.py')]:
        if target.exists():
            raise Rejected('VERIFIER_RESERVED_PATH')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    name = 'csi-project-' + uuid.uuid4().hex
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='csi-plan-') as directory:
            Path(directory, 'config.json').write_text(json.dumps({'testPaths': profile['testPaths']}), encoding='utf-8')
            cmd = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--read-only',
                   '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '128',
                   '--memory', '1g', '--cpus', '1', '--tmpfs', '/tmp:rw,nosuid,noexec,size=128m',
                   '--mount', f'type=bind,src={tree.resolve()},dst=/source,readonly',
                   '--mount', f'type=bind,src={directory},dst=/plan,readonly',
                   '--workdir', '/source/' + profile['runtime']['workingDirectory'], profile['runtime']['imageId']]
            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=130)
            lines = [line for line in process.stdout.splitlines() if line.startswith('CSI_PROJECT_VERIFICATION=')]
            if process.returncode or len(lines) != 1:
                raise Rejected('VERIFIER_EXECUTION_FAILED')
            result = json.loads(lines[0].split('=', 1)[1])
            checks = result['checks']
            security = [c for c in checks if c['id'].startswith('tests/test_csi_privacy_pack.py::')]
            result.update(schemaVersion=1, isolation='DOCKER_NETWORK_NONE', imageId=profile['runtime']['imageId'],
                          inventoryDigest=fingerprint(result['inventory']), durationMs=round((time.monotonic()-started)*1000),
                          passed=sum(c['status']=='PASS' for c in checks), failed=sum(c['status'] in {'FAIL','ERROR'} for c in checks),
                          skipped=sum(c['status']=='SKIP' for c in checks), securityTotal=len(security),
                          securityPassed=sum(c['status']=='PASS' for c in security),
                          failedTests=[c['id'] for c in checks if c['status'] in {'FAIL','ERROR'}],
                          securityChecks=[{'id': c['id'], 'status': {'PASS':'PASSED','FAIL':'FAILED','SKIP':'SKIPPED'}.get(c['status'],'ERROR')} for c in security])
            return result
    except (OSError, subprocess.SubprocessError, ValueError):
        raise Rejected('VERIFIER_UNAVAILABLE') from None
    finally:
        for target in (working/'tests/test_csi_privacy_pack.py', working/'csi_project_driver.py'):
            target.unlink(missing_ok=True)
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=15)
