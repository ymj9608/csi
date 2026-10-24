"""Windows-compatible isolated verifier for pure-Python synthetic experiments.

Only the fixture and a pinned Python stdlib are exposed, read-only. No host
environment, sockets, processes or directories are inherited. This is NOT the
production Docker verifier and does not validate deployment/native extensions.
Run: python scripts/experiment_wasi.py <fixture-directory>
Dependencies: wasmtime==50.0.1; pinned Python WASI distribution in .runtime/tools.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime/tools/python-wasi'


def verify(folder, timeout=90):
    started = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(Path(folder).resolve())],
            capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        value = json.loads(result.stdout)
        if result.returncode and value.get('exitCode') == 0:
            raise ValueError('VERIFIER_PROCESS_FAILED')
    except (subprocess.TimeoutExpired, ValueError) as exc:
        value = {'exitCode': -1, 'error': type(exc).__name__, 'cases': {}, 'passed': 0, 'total': 0}
    value.update(seconds=round(time.perf_counter()-started, 3), isolation='WASI_READ_ONLY_NO_NETWORK')
    return value


def run(folder):
    import wasmtime
    config = wasmtime.Config()
    config.consume_fuel = True
    engine = wasmtime.Engine(config)
    module = wasmtime.Module.from_file(engine, str(RUNTIME/'bin/python-3.12.0.wasm'))
    store = wasmtime.Store(engine)
    store.set_fuel(2_000_000_000)
    store.set_limits(memory_size=256*1024*1024)
    wasi = wasmtime.WasiConfig()
    wasi.argv = ['python', '-B', '-c',
                 "import os,unittest; os.chdir('/case'); unittest.main(module='test_contract', verbosity=2)"]
    wasi.env = [('PYTHONPATH', '/case'), ('PYTHONHOME', '/usr/local'), ('PYTHONHASHSEED', '0')]
    wasi.preopen_dir(str(RUNTIME/'usr'), '/usr', fs_mutable=False)
    wasi.preopen_dir(str(Path(folder).resolve()), '/case', fs_mutable=False)
    chunks = []
    size = 0
    def output(data):
        nonlocal size
        if size < 65536:
            chunks.append(data[:65536-size])
            size += len(chunks[-1])
        return len(data)
    wasi.stdout_custom = output
    wasi.stderr_custom = output
    store.set_wasi(wasi)
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    instance = linker.instantiate(store, module)
    code, error = 0, None
    try:
        instance.exports(store)['_start'](store)
    except wasmtime.ExitTrap as exc:
        code = exc.code
    except wasmtime.Trap as exc:
        code, error = -1, str(exc)
    log = b''.join(chunks).decode('utf-8', errors='replace')
    cases = {line.split(' ')[0]: line.rsplit(' ... ', 1)[-1]
             for line in log.splitlines() if line.startswith('test_') and ' ... ' in line}
    return {'exitCode': code, 'error': error, 'cases': cases,
            'passed': sum(v == 'ok' for v in cases.values()), 'total': len(cases), 'log': log}


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), ensure_ascii=True))
