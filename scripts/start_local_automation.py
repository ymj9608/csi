"""Launch the configured local automation service in the background."""
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not dotenv_values(ROOT / '.env').get('CSI_LOCAL_AUTOMATION_CONFIG'):
        print('Local automation not configured.')
        return
    output = ROOT / '.runtime/local-automation'
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'stdout.log').open('ab') as out, (output / 'stderr.log').open('ab') as err:
        process = subprocess.Popen([sys.executable, '-m', 'scripts.local_automation'], cwd=ROOT,
            env=os.environ.copy() | {'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'},
            stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    print(f'Local automation requested (launcher PID {process.pid}); duplicate instances exit via process lock.')


if __name__ == '__main__':
    main()
