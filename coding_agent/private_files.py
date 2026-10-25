"""Atomic UTF-8 receipts with user-only permissions on POSIX and Windows."""
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile


def restrict_private(path):
    if os.name == 'nt':
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', check=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW)
        sid = next(csv.reader([identity.stdout.strip()]))[1]
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', '*' + sid + ':F'],
            capture_output=True, check=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    temporary = Path(name)
    try:
        # Restrict the empty file before any token or generated source is written.
        restrict_private(temporary)
        stream = os.fdopen(descriptor, 'w', encoding='utf-8')
        descriptor = None
        with stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
