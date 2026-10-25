"""Execute fixed Flink regression tests in an offline, disposable Docker workspace."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET

from benchmark_flink import ROOT, UPSTREAM, RUNTIME, S3, TARGETS, TOKENS, RECEIVER, SSL, source

FIXTURES = ROOT / 'tests/fixtures/flink_patch_eval'
BUILD_CACHE = ROOT / '.runtime/flink-patch-v2/m2'
TEST_FILES = {
    'CsiTokenSecurityTest.java': (RUNTIME + 'security/token/').replace('/main/', '/test/'),
    'CsiSslSecurityTest.java': (RUNTIME + 'net/').replace('/main/', '/test/'),
    'CsiS3SecurityTest.java': S3.replace('/main/', '/test/'),
}
SECURITY_TESTS = {
    'securityV1NoSerializedTokenLogging', 'securityV2NoSessionCredentialLogging',
    'securityV3NoSecretKeyLogging', 'securityV4HonorsExplicitHostnameVerification',
    'securityV5NoKeystorePasswordLoggingOnFailure',
}
SAFE_TESTS = {'functionalityPreservesByteCountLog', 'functionalityPreservesRefreshEventLog',
              'functionalityPreservesRedactedDiagnostic'}
SUITES = ('CsiTokenSecurityTest', 'CsiSslSecurityTest', 'CsiS3SecurityTest',
          'DelegationTokenReceiverRepositoryTest', 'SSLUtilsTest',
          'AbstractS3DelegationTokenProviderTest', 'AbstractS3DelegationTokenReceiverTest')
SAFE_CONTROLS = {
    TOKENS: 'LOG.info("Delegation payload byte count: {}", containerBytes.length);',
    RECEIVER: 'LOG.info("Session credential refresh complete");',
    SSL: 'String password = "[REDACTED]";\n            LOG.info("Keystore diagnostic: {}", password);',
}


def controls_preserved(texts):
    return all(''.join(statement.split()) in ''.join(texts[p].split())
               for p, statement in SAFE_CONTROLS.items())


def read_reports(tree):
    cases = {}
    for report in tree.glob('**/target/surefire-reports/TEST-*.xml'):
        for item in ET.parse(report).getroot().iter('testcase'):
            identifier = item.get('classname', '') + '#' + item.get('name', '')
            if identifier in cases:
                raise ValueError('DUPLICATE_TEST_RESULT')
            state = 'FAILED' if item.find('failure') is not None or item.find('error') is not None else (
                'SKIPPED' if item.find('skipped') is not None else 'PASSED')
            cases[identifier] = state
    return cases


def gate(result, required_passes):
    cases = result.get('cases', {})
    security = {name: [v for k, v in cases.items() if k.endswith('#' + name)] for name in SECURITY_TESTS}
    return (result.get('exitCode') == 0 and result.get('controlsPreserved') is True
            and result.get('testsUnchanged') is True and bool(required_passes)
            and all(cases.get(k) == 'PASSED' for k in required_passes)
            and all(values == ['PASSED'] for values in security.values())
            and not any(v == 'FAILED' for v in cases.values()))


def available(image):
    """Read-only; never starts Docker Desktop or pulls an image implicitly."""
    if not shutil.which('docker'):
        return {'ready': False, 'reason': 'DOCKER_NOT_INSTALLED'}
    result = subprocess.run(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'],
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 0:
        return {'ready': True, 'imageId': result.stdout.strip(), 'reason': None}
    daemon = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'],
                            capture_output=True, text=True, timeout=20)
    return {'ready': False, 'imageId': None, 'image': image,
            'reason': 'VALIDATION_IMAGE_NOT_INSTALLED' if daemon.returncode == 0 else 'DOCKER_UNAVAILABLE'}


def validate(texts, output, image_id, timeout=1800):
    from flink_patch_protocol import sha
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / '.runtime/flink-patch-v2'
    runtime.mkdir(parents=True, exist_ok=True)
    result = {'exitCode': None, 'cases': {}, 'controlsPreserved': None,
              'sourceControlMarkersUnchanged': controls_preserved(texts),
              'testsUnchanged': False, 'wallMs': None}
    with tempfile.TemporaryDirectory(dir=runtime, prefix='validation-') as tmp:
        root = Path(tmp)
        tree, m2 = root / 'source', root / 'm2'
        # Never share generated classes or writable dependency caches between trials.
        shutil.copytree(UPSTREAM, tree, ignore=shutil.ignore_patterns('.git', 'target'), symlinks=True)
        shutil.copytree(BUILD_CACHE, m2, symlinks=True)
        shutil.copyfile(FIXTURES / 'maven-settings.xml', tree / 'csi-maven-settings.xml')
        for path in TARGETS:
            (tree / path).write_text(texts[path])
        protected = {}
        for name, directory in TEST_FILES.items():
            target = tree / directory / name
            target.write_bytes((FIXTURES / name).read_bytes())
            protected[str(target.relative_to(tree))] = sha(target.read_bytes())
        container_name = 'csi-flink-eval-' + uuid.uuid4().hex
        command = ['docker', 'run', '--rm', '--pull=never', '--network=none', '--read-only',
                   '--name', container_name,
                   '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=512',
                   '--memory=4g', '--memory-swap=4g', '--cpus=2', '--user', f'{os.getuid()}:{os.getgid()}',
                   '--tmpfs', '/tmp:rw,size=256m', '-e', 'MAVEN_CONFIG=/tmp/.m2',
                   '-e', 'MAVEN_OPTS=-Xmx1536m -XX:ActiveProcessorCount=2',
                   '-v', f'{tree}:/work', '-v', f'{m2}:/m2', '-w', '/work', image_id,
                   'mvn', '-o', '-B', '-s', '/work/csi-maven-settings.xml', '-Dmaven.repo.local=/m2', '-Duser.home=/tmp',
                   '-pl', 'flink-runtime,flink-filesystems/flink-s3-fs-base', '-am',
                   '-Dcheckstyle.skip', '-Dspotless.skip=true', '-Drat.skip=true',
                   '-Dcyclonedx.skip=true',
                   '-DfailIfNoTests=false', '-Dsurefire.failIfNoSpecifiedTests=false',
                   '-Dmaven.test.failure.ignore=true',
                   '-Dtest=' + ','.join(SUITES), '-DskipITs', 'package']
        try:
            with (output / 'maven.log').open('w') as log:
                run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            result['exitCode'] = run.returncode
            result['cases'] = read_reports(tree)
            # Behavioral assertions accept equivalent code; literal source matches are audit-only.
            result['controlsPreserved'] = all(
                [v for k, v in result['cases'].items() if k.endswith('#' + name)] == ['PASSED']
                for name in SAFE_TESTS)
            result['testsUnchanged'] = all((tree / p).exists() and sha((tree / p).read_bytes()) == h
                                           for p, h in protected.items())
            result['executedSuites'] = sorted({k.split('#')[0].split('.')[-1] for k in result['cases']})
        except subprocess.TimeoutExpired:
            result['error'] = 'VALIDATION_TIMEOUT'
        finally:
            # A killed docker client does not stop its container. Remove only ours.
            subprocess.run(['docker', 'rm', '-f', container_name], capture_output=True, timeout=20)
        result['wallMs'] = round((time.perf_counter() - started) * 1000, 3)
    return result


def calibrate(out, image):
    """No model inference until tests fail on all 5 mutations and pass on a reference."""
    from benchmark_flink import write
    from flink_patch_protocol import sha
    attempts = out / 'calibration-attempts'
    attempts.mkdir(parents=True, exist_ok=True)
    attempt = attempts / str(len(list(attempts.iterdir())) + 1)
    attempt.mkdir()
    def finish(value):
        value['attempt'] = str(attempt.relative_to(out))
        write(attempt / 'result.json', value)
        write(out / 'calibration.json', value)
    status = available(image)
    if not status['ready']:
        finish({**status, 'status': 'BLOCKED', 'modelCalls': 0})
        return
    if not BUILD_CACHE.is_dir():
        finish({'status': 'BLOCKED', 'reason': 'MAVEN_DEPENDENCIES_NOT_PREPARED', 'modelCalls': 0})
        return
    variants = {}
    for variant in ('mutated', 'remediated_controls_retained'):
        texts = {p: source(p, variant).decode() for p in TARGETS}
        variants[variant] = validate(texts, attempt / variant, status['imageId'])
    before, after = variants.values()
    observed = {k.split('#')[-1] for k, state in before['cases'].items() if state == 'FAILED'}
    required = sorted(k for k, state in after['cases'].items() if state == 'PASSED')
    ready = (observed == SECURITY_TESTS and gate(after, required)
             and set(before['cases']) == set(after['cases'])
             and set(SUITES) <= set(after.get('executedSuites', [])))
    finish({
        'status': 'READY' if ready else 'BLOCKED', 'imageId': status['imageId'],
        'requiredPassingTests': required, 'variants': variants, 'modelCalls': 0,
        'testHashes': {p.name: sha(p.read_bytes()) for p in sorted(FIXTURES.glob('*.java'))},
        'referenceIsAiGenerated': False,
    })
