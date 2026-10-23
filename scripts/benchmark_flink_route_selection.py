"""Counterfactual Flink route selection with a shared verified sanitizer.

Same code and policy, two different diagram-only collector bindings. One code-only
candidate is reused because its input is identical. Five fresh local model calls.
Previous pilots and failures remain intact. No automatic or manual candidate repair.
"""
import argparse
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

import httpx
import benchmark_flink_deployment_boundary as base
from benchmark_flink import ROOT, UPSTREAM, PIN, RUNTIME, write
from benchmark_flink_deployment_handoff import CLARIFICATION
from benchmark_signup_events_local import LocalClient, CODER
from flink_patch_protocol import apply_edits
from flink_patch_validation import BUILD_CACHE, FIXTURES, read_reports
import benchmark_retry_boundary as vision_runner

OUT = ROOT / 'docs/benchmarks/flink/route-selection-v3'
WORK = ROOT / '.runtime/flink-route-selection-v3'
HELPER = '''    // Shared, benchmark-validated diagnostic utility; no route policy is encoded here.
    static String sanitizeDiagnosticName(String name) {
        return name == null ? null : name.replaceAll("010[0-9]{8}", "[REDACTED]");
    }

'''
HELPER_TEST = '''package org.apache.flink.runtime.rest.handler.job;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
class CsiDiagnosticSanitizerTest {
 @Test void handlesNull() { assertThat(JobConfigHandler.sanitizeDiagnosticName(null)).isNull(); }
 @Test void preservesNonPhone() { assertThat(JobConfigHandler.sanitizeDiagnosticName("batch-20261023")).isEqualTo("batch-20261023"); }
 @Test void masksBeginning() { assertThat(JobConfigHandler.sanitizeDiagnosticName("01012345678-orders")).isEqualTo("[REDACTED]-orders"); }
 @Test void masksEmbedded() { assertThat(JobConfigHandler.sanitizeDiagnosticName("orders-01012345678")).isEqualTo("orders-[REDACTED]"); }
 @Test void masksMultiple() { assertThat(JobConfigHandler.sanitizeDiagnosticName("merge-01012345678-01087654321")).isEqualTo("merge-[REDACTED]-[REDACTED]"); }
}
'''
NAMES = ['code_only', 'vision_a', 'vision_b']


def swap_routes(text):
    return text.replace('csi.route.a', 'CSI_SWAP_TEMP').replace('csi.route.b', 'csi.route.a').replace('CSI_SWAP_TEMP', 'csi.route.b')


def sources():
    return {p: (OUT / 'mutated' / p).read_text() for p in base.PATHS}


def prepare():
    assert subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip() == PIN
    assert not subprocess.check_output(['git', '-C', str(UPSTREAM), 'status', '--porcelain'])
    OUT.mkdir(exist_ok=False); WORK.mkdir(exist_ok=True)
    for path in base.PATHS:
        text = (UPSTREAM / path).read_text()
        if path == base.TARGET:
            marker = '        ResponseBody json = createJobConfigInfo(graph);'
            assert text.count(marker) == 1
            text = text.replace(marker, base.INJECTION + marker)
            marker = '    private JobConfigInfo createJobConfigInfo('
            assert text.count(marker) == 1
            text = text.replace(marker, HELPER + marker)
        dest = OUT / 'mutated' / path; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(text)
    (OUT / 'synthetic-mutation.patch').write_text(''.join(difflib.unified_diff(
        (UPSTREAM / base.TARGET).read_text().splitlines(True), sources()[base.TARGET].splitlines(True),
        fromfile='a/' + base.TARGET, tofile='b/' + base.TARGET)))
    for name in ['LICENSE', 'NOTICE']:
        shutil.copyfile(UPSTREAM / name, OUT / ('APACHE-' + name))
    testdir = OUT / 'frozen-tests'; testdir.mkdir()
    original = base.TEST.read_text()
    for topology in ['a', 'b']:
        classname = 'CsiDeployment' + topology.upper() + 'Test'
        test = original.replace('CsiDeploymentBoundaryTest', classname)
        if topology == 'b': test = swap_routes(test)
        (testdir / (classname + '.java')).write_text(test)
    (testdir / 'CsiDiagnosticSanitizerTest.java').write_text(HELPER_TEST)
    svg = (base.OUT / 'architecture.svg').read_text()
    js = """const {chromium}=require('./frontend/node_modules/playwright');const fs=require('fs');
(async()=>{const b=await chromium.launch({headless:true,channel:'chrome'});try{
const p=await b.newPage({viewport:{width:1280,height:760}});await p.setContent(fs.readFileSync(process.argv[1],'utf8'));
await p.locator('svg').screenshot({path:process.argv[2]});}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1)});"""
    for topology in ['a', 'b']:
        folder = OUT / ('vision_' + topology); folder.mkdir()
        (folder / 'architecture.svg').write_text(svg if topology == 'a' else swap_routes(svg))
        subprocess.run(['node', '-e', js, str(folder / 'architecture.svg'), str(folder / 'architecture.png')], cwd=ROOT, check=True, timeout=25)
    # Trustworthy host-authored helper calibration, not execution of model output.
    helper_check = WORK / 'helper-check'; helper_check.mkdir()
    java = 'public class HelperCheck {\n' + HELPER + '''public static void main(String[] args) {
String[][] cases = {{null,null},{"batch-20261023","batch-20261023"},{"01012345678-orders","[REDACTED]-orders"},
{"orders-01012345678","orders-[REDACTED]"},{"merge-01012345678-01087654321","merge-[REDACTED]-[REDACTED]"}};
for(String[] c:cases) if(!java.util.Objects.equals(sanitizeDiagnosticName(c[0]),c[1])) throw new AssertionError();
System.out.println("5/5 helper checks passed"); }}'''
    (helper_check / 'HelperCheck.java').write_text(java)
    subprocess.run(['javac', '-d', str(helper_check), str(helper_check / 'HelperCheck.java')], check=True, timeout=25)
    result = subprocess.run(['java', '-cp', str(helper_check), 'HelperCheck'], capture_output=True, text=True, check=True, timeout=10)
    write(OUT / 'helper-calibration.json', {'passed': 5, 'total': 5, 'output': result.stdout.strip(), 'helperSha256': base.sha(HELPER)})
    write(OUT / 'protocol.json', {
        'repository': 'https://github.com/apache/flink', 'commit': PIN,
        'models': {'vision': 'qwen3-vl:8b', 'coding': CODER}, 'maxCalls': 5, 'retries': 0,
        'sourceHashes': {p: base.sha(t) for p, t in sources().items()},
        'sourceBytes': sum(len(t.encode()) for t in sources().values()),
        'testHashes': {p.name: base.sha(p.read_bytes()) for p in testdir.iterdir()},
        'imageHashes': {t: base.sha((OUT / ('vision_' + t) / 'architecture.png').read_bytes()) for t in ['a', 'b']},
        'task': base.TASK, 'system': base.SYSTEM, 'handoffRules': CLARIFICATION,
        'helperContract': 'Use the supplied sanitizeDiagnosticName helper only for evidenced external destinations. It is already implemented and verified; do not edit it or write a new regex. Preserve raw values on explicitly authorized internal routes.',
        'groundTruth': {'a': {'internal': 'csi.route.a', 'external': 'csi.route.b'}, 'b': {'internal': 'csi.route.b', 'external': 'csi.route.a'}},
        'scope': 'Same full three files and same verified helper in both arms. Only JobConfigHandler may be edited. Test data and ground truth are withheld from model inputs.',
        'resources': {'modelConcurrency': 1, 'keepAlive': 0, 'buildMemoryGB': 4, 'buildCPUs': 2, 'buildNetwork': 'none'},
        'limitations': [
            'Synthetic injected diagnostic calls on real Flink. Collector ownership is deliberately outside source and supplied by diagrams.',
            'Both conditions receive a working sanitizer: evaluates where to apply protection, not ability to invent sanitization code.',
            'Code-only input is identical across deployments. One generated candidate is evaluated under both bindings; not two independent inference trials.',
            'Two fresh image calls and two fresh vision-informed coder calls, one per deployment. No candidate repair or discarded model results.',
            'Missing-fact abstention is legitimate; lower patch coverage does not imply worse uncertainty calibration.',
            'No text control; added deployment information is measured, not image-exclusive capability.',
            'Targeted tests capture logger outputs; no real external collector, full-cluster or repository navigation test.',
            'Earlier no-patch/compilation/security failures are retained in deployment-boundary and deployment-boundary-handoff-v2.',
        ],
    })
    print(json.dumps({'prepared': str(OUT), 'helperChecks': 5, 'calls': 5}), flush=True)


def models(names=None, recovery=False):
    protocol = json.loads((OUT / 'protocol.json').read_text())
    assert {p: base.sha(t) for p, t in sources().items()} == protocol['sourceHashes']
    with httpx.Client(timeout=10, trust_env=False) as api:
        assert not api.get('http://127.0.0.1:11434/api/ps').json().get('models'), 'Other models loaded'
    client = LocalClient(OUT, {})
    for name in names or NAMES:
        context = None
        if name.startswith('vision_'):
            vision_runner.OUT = OUT / name
            prompt = 'Read this deployment diagram carefully. In at most 90 words list the exact logger identifiers and each recipient: INTERNAL authorized or EXTERNAL no personal-phone access. Also identify the private archive path. Return a short factual inspection instruction. Do not infer route bindings from names or invent code fixes.'
            v = vision_runner.vision(prompt, read_timeout_seconds=60 if recovery else 20, wall_limit_seconds=120 if recovery else 90)
            if v['status'] != 'COMPLETED':
                write(OUT / (name + '-result.json'), {'name': name, 'status': 'VISION_FAILED'}); continue
            context = v['final']
        result = {'name': name, 'status': 'STARTED'}
        try:
            answer = client.call(name, 'ollama', CODER, base.SYSTEM, {
                'task': base.TASK, 'sources': sources(), 'architectureContext': context,
                'editablePaths': [base.TARGET], 'handoffRules': CLARIFICATION,
                'verifiedUtility': protocol['helperContract'],
                'instruction': 'Use the existing helper at the external log call only if its destination is evidenced. Give exact minimal before/after edits. Do not change the helper, private JSON, internal logger or route names.'}, base.SCHEMA)
            write(OUT / (name + '-diagnosis.json'), answer)
            if answer['edits']:
                changed, patch = apply_edits(sources(), {'edits': answer['edits'], 'reason': answer['reason']}, {base.TARGET})
                assert changed[base.TARGET].count(HELPER) == 1, 'READ_ONLY_HELPER_MODIFIED'
                diff = patch['diff']
            else:
                changed = sources(); diff = ''
            (OUT / (name + '.patch')).write_text(diff)
            (OUT / (name + '-candidate.java')).write_text(changed[base.TARGET])
            result.update(status='GENERATED' if answer['edits'] else 'NO_PATCH', findings=answer['findings'], candidateSha256=base.sha(changed[base.TARGET]))
        except Exception as exc:
            result.update(status='BLOCKED', error=type(exc).__name__ + ': ' + str(exc)[:250])
        write(OUT / (name + '-result.json'), result)
        print(json.dumps({'name': name, 'status': result['status']}), flush=True)


def recover():
    original = json.loads((OUT / 'vision_b/vision.json').read_text())
    assert original['status'] == 'FAILED' and not original['final'] and 'ReadTimeout' in original.get('error', '')
    folder = OUT / 'vision_b_retry'; folder.mkdir(exist_ok=False)
    for file in ['architecture.png', 'architecture.svg']:
        shutil.copyfile(OUT / 'vision_b' / file, folder / file)
    write(OUT / 'timeout-recovery-amendment.json', {
        'reason': 'The first B image request produced no content before the 20-second read timeout. Retain failure and allow exactly one transport-timeout recovery, not a patch-quality retry.',
        'originalResult': 'vision_b/vision.json', 'recoveryResult': 'vision_b_retry/vision.json',
        'readTimeoutSeconds': 60, 'wallLimitSeconds': 120, 'maxAdditionalCalls': 2,
        'expectedTotalCalls': 6, 'inputChanged': False, 'failedAttemptExcludedFromPrimaryResults': False,
    })
    models(['vision_b_retry'], recovery=True)


def validate(candidate, name, topologies):
    output = OUT / (name + '-validation'); output.mkdir(exist_ok=False)
    started = time.perf_counter(); container = 'csi-flink-route-' + uuid.uuid4().hex
    result = {'cases': {}, 'exitCode': None}
    protocol = json.loads((OUT / 'protocol.json').read_text())
    with tempfile.TemporaryDirectory(dir=WORK, prefix='validate-') as tmp:
        tree = Path(tmp) / 'source'; m2 = Path(tmp) / 'm2'
        shutil.copytree(UPSTREAM, tree, ignore=shutil.ignore_patterns('.git', 'target'), symlinks=True)
        shutil.copytree(BUILD_CACHE, m2, symlinks=True)
        (tree / base.TARGET).write_text(candidate)
        testdir = tree / (RUNTIME + 'rest/handler/job/').replace('/main/', '/test/')
        tests = [OUT / 'frozen-tests/CsiDiagnosticSanitizerTest.java'] + [OUT / ('frozen-tests/CsiDeployment' + t.upper() + 'Test.java') for t in topologies]
        for test in tests:
            assert base.sha(test.read_bytes()) == protocol['testHashes'][test.name]
            shutil.copyfile(test, testdir / test.name)
        shutil.copyfile(FIXTURES / 'maven-settings.xml', tree / 'csi-maven-settings.xml')
        suites = ','.join([p.stem for p in tests] + ['JobConfigHandlerTest'])
        cmd = ['docker', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--name', container,
               '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=512', '--memory=4g', '--memory-swap=4g', '--cpus=2',
               '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:rw,size=256m',
               '-e', 'MAVEN_CONFIG=/tmp/.m2', '-e', 'MAVEN_OPTS=-Xmx1536m -XX:ActiveProcessorCount=2',
               '-v', f'{tree}:/work', '-v', f'{m2}:/m2', '-w', '/work', base.IMAGE,
               'mvn', '-o', '-B', '-s', 'csi-maven-settings.xml', '-Dmaven.repo.local=/m2', '-Duser.home=/tmp',
               '-pl', 'flink-runtime', '-am', '-Dcheckstyle.skip', '-Dspotless.skip=true', '-Drat.skip=true', '-Dcyclonedx.skip=true',
               '-DfailIfNoTests=false', '-Dsurefire.failIfNoSpecifiedTests=false', '-Dmaven.test.failure.ignore=true',
               '-Dtest=' + suites, '-DskipITs', 'package']
        try:
            with (output / 'maven.log').open('w') as log:
                p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=240)
            result.update(exitCode=p.returncode, cases=read_reports(tree),
                          testsUnchanged=all(base.sha((testdir / t.name).read_bytes()) == protocol['testHashes'][t.name] for t in tests))
        except subprocess.TimeoutExpired:
            result['error'] = 'VALIDATION_TIMEOUT'
        finally:
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=20)
        result['seconds'] = time.perf_counter() - started
        result['helperPassed'] = sum(v == 'PASSED' for k, v in result['cases'].items() if 'CsiDiagnosticSanitizerTest#' in k)
        result['deployments'] = {}
        for topology in topologies:
            prefix = 'CsiDeployment' + topology.upper() + 'Test#'
            cases = {k: v for k, v in result['cases'].items() if prefix in k or 'JobConfigHandlerTest#' in k}
            passed = sum(v == 'PASSED' for v in cases.values())
            result['deployments'][topology] = {'passed': passed, 'total': len(cases),
                'securityPassed': sum(v == 'PASSED' for k, v in cases.items() if '#security' in k),
                'accepted': result['exitCode'] == 0 and result.get('testsUnchanged') is True and len(cases) == 9 and passed == 9 and result['helperPassed'] == 5}
    write(output / 'validation.json', result)
    print(json.dumps({'name': name, 'seconds': result['seconds'], 'deployments': result['deployments'], 'helperPassed': result['helperPassed']}), flush=True)
    return result


def verify():
    rows = []
    verified = {}
    for name in NAMES + (['vision_b_retry'] if (OUT / 'vision_b_retry-result.json').exists() else []):
        result = json.loads((OUT / (name + '-result.json')).read_text())
        if result['status'] in {'GENERATED', 'NO_PATCH'}:
            candidate = (OUT / (name + '-candidate.java')).read_text()
            topologies = ['a', 'b'] if name == 'code_only' else ['b' if name.startswith('vision_b') else 'a']
            digest = base.sha(candidate)
            cached = verified.get(digest)
            if cached and set(topologies) <= set(cached[1]['deployments']):
                check = json.loads(json.dumps(cached[1]))
                check.update(reusedFrom=cached[0], identicalCandidateSha256=digest,
                             originalValidationSeconds=check['seconds'], seconds=0,
                             timingNote='Exact same source and frozen tests: no second build was executed. This is not a measured speedup.')
                check['deployments'] = {t: check['deployments'][t] for t in topologies}
                prefixes = ['CsiDeployment' + t.upper() + 'Test#' for t in topologies] + ['CsiDiagnosticSanitizerTest#', 'JobConfigHandlerTest#']
                check['cases'] = {k: v for k, v in check['cases'].items() if any(p in k for p in prefixes)}
            else:
                check = validate(candidate, name, topologies)
                verified[digest] = (name, check)
            result['verification'] = check
        call = OUT / 'calls' / (name + '.json')
        if call.exists():
            c = json.loads(call.read_text()); result.update(modelMs=c.get('wallMs'), inputTokens=c.get('inputTokens'), outputTokens=c.get('outputTokens'))
        if name.startswith('vision_'):
            v = json.loads((OUT / name / 'vision.json').read_text())
            result.update(visionMs=v['seconds'] * 1000, visionInputTokens=v.get('inputTokens'), visionOutputTokens=v.get('outputTokens'))
        rows.append(result); write(OUT / 'comparison.json', rows)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=['prepare', 'models', 'recover', 'verify'])
    args = p.parse_args()
    {'prepare': prepare, 'models': models, 'recover': recover, 'verify': verify}[args.phase]()
