"""Recheck a single evaluator-authored API correction; never overwrite first-pass results."""
import difflib
import json
from datetime import datetime, timezone

from benchmark_flink import ROOT, TARGETS, SSL, source
from flink_patch_protocol import apply_edits, sha
from flink_patch_validation import validate, gate, SECURITY_TESTS


def main():
    original = ROOT / 'docs/benchmarks/flink/openai-quick'
    output = original / 'compile-repair'
    output.mkdir(exist_ok=False)
    config = json.loads((original / 'protocol.json').read_text())
    calibration = json.loads((original / 'calibration.json').read_text())
    texts = {p: source(p, 'mutated').decode() for p in config['paths']}
    assert {p: sha(t.encode()) for p, t in texts.items()} == config['sources']
    answer = json.loads((original / 'calls/code_index.json').read_text())['answer']
    edited, _ = apply_edits(texts, answer, set(TARGETS))
    before = edited[SSL]
    bad = 'SecurityOptions.isRestSSLHostnameVerificationEnabled(config)'
    good = 'config.get(SecurityOptions.SSL_REST_VERIFY_HOSTNAME)'
    assert before.count(bad) == 1
    edited[SSL] = before.replace(bad, good)
    (output / 'correction.patch').write_text(''.join(difflib.unified_diff(
        before.splitlines(True), edited[SSL].splitlines(True), fromfile='a/' + SSL, tofile='b/' + SSL)))
    (output / 'candidate.patch').write_text(''.join(''.join(difflib.unified_diff(
        texts[p].splitlines(True), edited[p].splitlines(True), fromfile='a/' + p, tofile='b/' + p))
        for p in TARGETS))
    record = {'status': 'STARTED', 'startedAtUtc': datetime.now(timezone.utc).isoformat(),
              'intervention': 'EVALUATOR_AUTHORED_ONE_API_EXPRESSION_CORRECTION',
              'baseArm': 'code_index', 'newModelCalls': 0, 'additionalApiCostUsd': 0,
              'humanRepairTimeMeasured': False, 'otherArmsRerun': False,
              'originalCallSha256': sha((original / 'calls/code_index.json').read_bytes()),
              'note': 'Diagnostic follow-up, not an autonomous model retry or a controlled superiority comparison.'}
    def save():
        (output / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    save()
    result = validate(edited, output / 'validation', calibration['imageId'])
    cases = result['cases']
    record.update(verification=result, accepted=gate(result, calibration['requiredPassingTests']),
                  securityPassed=sum(v == 'PASSED' and k.split('#')[-1] in SECURITY_TESTS for k, v in cases.items()),
                  functionalPassed=sum(v == 'PASSED' and k.split('#')[-1] not in SECURITY_TESTS for k, v in cases.items()),
                  failedTests=[k for k, v in cases.items() if v != 'PASSED'])
    record['status'] = 'PASSED' if record['accepted'] else 'VALIDATION_FAILED'
    save()
    print(json.dumps({k: v for k, v in record.items() if k != 'verification'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
