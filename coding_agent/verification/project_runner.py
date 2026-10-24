"""Fixed Python/pytest adapter. Runs only inside the network-disabled verifier image."""
import json
import os
from pathlib import Path
import subprocess
import sys

os.environ.update(TEST_DATABASE_URL='sqlite://', DATABASE_URL='sqlite://',
                  JWT_SECRET='isolated-csi-coding-test-secret-only', CSI_LAB_MODE='false',
                  HOME='/tmp', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONPATH='/opt/verification:' + os.getcwd())
config = json.loads(Path('/plan/config.json').read_text())
try:
    process = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                              '-p', 'project_plugin', '--rootdir=.', *config['testPaths']],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=110)
    report = json.loads(Path('/tmp/csi-results.json').read_text())
    report['exitCode'] = process.returncode
except subprocess.TimeoutExpired:
    report = {'inventory': [], 'checks': [], 'exitCode': 124, 'error': 'TIMEOUT'}
except (OSError, ValueError):
    report = {'inventory': [], 'checks': [], 'exitCode': 2, 'error': 'HARNESS_ERROR'}
print('CSI_PROJECT_VERIFICATION=' + json.dumps(report))
