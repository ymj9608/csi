import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from .repository import Rejected
from .verification.contract import SECURITY_TESTS, complete_security_report

ROOT = Path(__file__).resolve().parent

def verify(snapshot, image='csi-coding-verifier:local'):
    """Only this fixed command runs; model-suggested tests/commands are never executed."""
    snapshot = Path(snapshot)
    snapshot.chmod(0o755)
    shutil.copy2(ROOT/'verification/security_checks.py', snapshot/'backend/tests/test_csi_coding_security.py')
    try:
        inspected = subprocess.run(['docker','image','inspect','--format','{{.Id}}',image],
            capture_output=True,text=True,timeout=10,check=True)
    except (OSError,subprocess.SubprocessError):
        raise Rejected('VERIFIER_UNAVAILABLE') from None
    image_id = inspected.stdout.strip()
    if not image_id.startswith('sha256:'):
        raise Rejected('VERIFIER_IMAGE_ID')
    name = 'csi-verify-'+uuid.uuid4().hex
    command = ['docker','run','--rm','--name',name,'--network','none','--read-only',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128',
        '--memory','1g','--cpus','1','--tmpfs','/tmp:rw,nosuid,noexec,size=128m',
        '--mount',f'type=bind,src={snapshot},dst=/source,readonly',image_id]
    started=time.monotonic()
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=100)
        lines=[line for line in result.stdout.splitlines() if line.startswith('CSI_VERIFICATION_JSON=')]
        if result.returncode or len(lines)!=1:
            raise Rejected('VERIFIER_EXECUTION_FAILED')
        report=json.loads(lines[0].split('=',1)[1])
        report.update(durationMs=int((time.monotonic()-started)*1000),imageId=image_id,
                      isolation='DOCKER_NETWORK_NONE',database='SQLITE_IN_MEMORY')
        return report
    except (subprocess.TimeoutExpired,json.JSONDecodeError):
        raise Rejected('VERIFIER_TIMEOUT_OR_OUTPUT') from None
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)

def passed(report):
    return (complete_security_report(report) and report.get('exitCode')==0 and report.get('failed')==0
            and report.get('securityPassed')==len(SECURITY_TESTS) and report.get('passed',0)>=40
            and report.get('isolation')=='DOCKER_NETWORK_NONE')
