"""Diagnostic only: finish all shards, retain parser errors, never mark partial as CSI success."""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from benchmark_flink import ROOT, OUT, source, configure_scanner, write, evaluate


def main():
    dest = OUT / 'raw-scanner-audit.json'
    if dest.exists():
        raise SystemExit('Audit already exists')
    configure_scanner()
    inventory = json.loads((OUT / 'source-inventory.json').read_text())
    groups, current, size = [], [], 0
    for item in inventory:
        n = len(source(item['path'], 'mutated'))
        if current and size+n > 12_000_000:
            groups.append(current); current = []; size = 0
        current.append(item['path']); size += n
    if current:
        groups.append(current)
    started = time.perf_counter()
    findings, runs = [], []
    for index, group in enumerate(groups, 1):
        t = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix='flink-raw-audit-') as tmp:
            for p in group:
                target = Path(tmp)/p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source(p, 'mutated'))
            env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'SSL_CERT_FILE',
                'SEMGREP_LOG_FILE', 'SEMGREP_SETTINGS_FILE') if k in os.environ}
            env.update(SEMGREP_SEND_METRICS='off', SEMGREP_ENABLE_VERSION_CHECK='0')
            run = subprocess.run([os.environ['SEMGREP_BIN'], 'scan', '--config',
                str(ROOT/'rules/java-security.yml'), '--config', str(ROOT/'rules/python-security.yml'),
                '--json', '--metrics=off', '--disable-version-check', '--timeout', '10',
                '--max-memory', '512', '--max-target-bytes', '1000000', '--no-git-ignore', '.'],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=90)
            raw = json.loads(run.stdout)
            entry = {'batch': index, 'inputFiles': len(group), 'exitCode': run.returncode,
                'wallMs': round((time.perf_counter()-t)*1000, 3), 'errors': raw.get('errors', []),
                'scannedFiles': len(raw.get('paths', {}).get('scanned', [])),
                'findingCount': len(raw.get('results', []))}
            runs.append(entry)
            for f in raw.get('results', []):
                findings.append({'ruleId': f['check_id'].split('.')[-1], 'filePath': f['path'],
                    'startLine': f['start']['line'], 'endLine': f['end']['line']})
        print(json.dumps(entry), flush=True)
    errors = [e for r in runs for e in r['errors']]
    write(dest, {'complete': not errors and all(r['exitCode'] == 0 for r in runs),
        'csiAccepted': not errors and all(r['exitCode'] == 0 for r in runs),
        'wallMs': (time.perf_counter()-started)*1000, 'batches': runs,
        'files': len(inventory), 'errors': errors, 'findings': findings,
        'quality': evaluate(findings, json.loads((OUT/'ground-truth.json').read_text())),
        'note': 'Raw rule coverage diagnostic, not successful production CSI ingestion; parser failures are retained.'})


if __name__ == '__main__':
    main()
