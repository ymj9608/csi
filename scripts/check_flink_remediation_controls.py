"""Post-hoc sanity check: remove synthetic defects, keep safe logging controls."""
import difflib
import json
import time
from benchmark_flink import (OUT, WORK, TARGETS, TOKENS, RECEIVER, PROVIDER, SSL,
                             RUNTIME, source, configure_scanner, scan_paths, write)


def main():
    if (OUT/'controls-retained-scan.json').exists():
        raise SystemExit('Control check already recorded; use a fresh output directory')
    variant = 'remediated_controls_retained'
    texts = {p: source(p, 'mutated').decode() for p in TARGETS}
    def replace(path, before, after=''):
        assert texts[path].count(before) == 1
        texts[path] = texts[path].replace(before, after)
    replace(TOKENS, '        String accessToken = java.util.Base64.getEncoder().encodeToString(containerBytes);\n        LOG.info("Delegation payload: {}", accessToken);\n')
    replace(RECEIVER, '        String accessToken = credentials.getSessionToken();\n        LOG.info("Session credential: {}", accessToken);\n')
    replace(PROVIDER, '+ secretKey', '+ GlobalConfiguration.HIDDEN_CONTENT')
    replace(SSL, '        {\n            String password = keystorePassword;\n            LOG.info("Keystore password: {}", password);\n        }\n')
    replace(SSL, 'sslContextBuilder.endpointIdentificationAlgorithm(\n                    null);',
            'sslContextBuilder.endpointIdentificationAlgorithm(\n                    config.get(SecurityOptions.SSL_REST_VERIFY_HOSTNAME) ? "HTTPS" : null);')
    patch = []
    for path, content in texts.items():
        target = WORK/variant/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        patch.extend(difflib.unified_diff(source(path, 'mutated').decode().splitlines(True),
            content.splitlines(True), fromfile='a/'+path, tofile='b/'+path))
    (OUT/'remediation-controls-retained.patch').write_text(''.join(patch))
    inventory = json.loads((OUT/'source-inventory.json').read_text())
    paths = sorted({f['path'] for f in inventory if f['path'].startswith(
        (RUNTIME+'security/', RUNTIME+'net/'))} | set(TARGETS))
    configure_scanner()
    start = time.perf_counter()
    findings, _ = scan_paths(paths, variant)
    wall = (time.perf_counter()-start)*1000
    expected = next(i for i, line in enumerate(texts[SSL].splitlines(), 1)
                    if 'LOG.info("Keystore diagnostic: {}", password);' in line)
    assert len(findings) == 1 and findings[0]['filePath'] == SSL and findings[0]['startLine'] == expected
    write(OUT/'controls-retained-scan.json', {'variant': variant, 'postHoc': True,
        'purpose': 'Remove injected positive defects but retain all three safe logging controls; distinguish source restoration from scanner false-positive improvement.',
        'complete': True, 'files': len(paths), 'wallMs': wall, 'findings': findings,
        'remainingLabeledFalsePositive': 'N3', 'expectedPositiveMutationsReverted': 5,
        'runtimeTestExecuted': False})


if __name__ == '__main__':
    main()
