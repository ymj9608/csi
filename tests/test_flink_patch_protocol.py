"""Protocol invariants and grading failures; never call a model or Docker."""
import sys
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from flink_patch_protocol import (ARMS, schedule, context_plan, batches,
                                 inspect_context, apply_edits, compare)
from flink_patch_validation import SECURITY_TESTS, gate, read_reports

SOURCES = {'src/Entry.java': 'class Entry { Store store; }',
           'src/Store.java': 'class Store { void save(String secret) {} }',
           'jobs/Hidden.java': 'class Hidden {}',
           'config/Settings.java': 'class Settings { boolean verify = false; }'}
TASK = {'finding': {'filePath': 'src/Entry.java', 'field': 'secret'},
        'changedPaths': ['jobs/Hidden.java'], 'scannerPaths': [],
        'readOnlyContractPaths': ['config/Settings.java']}
ARCH = {'diagramType': 'ARCHITECTURE', 'components': [], 'flows': [],
        'codeHints': ['src/Entry.java'], 'trustBoundaries': [], 'assumptions': [],
        'uncertainties': [], 'summary': 'Entry only; intentionally omits other files.'}


def test_image_omission_cannot_remove_changed_scanner_or_config_evidence():
    baseline = context_plan(SOURCES, TASK, 'code_index', commit='abc')
    vision = context_plan(SOURCES, TASK, 'vision_index', ARCH, 'abc')
    assert set(baseline['selectedPaths']) <= set(vision['selectedPaths'])
    assert set(vision['mandatoryPaths']) == {'src/Entry.java', 'jobs/Hidden.java', 'config/Settings.java'}
    settings = next(f for f in baseline['codePlan']['files'] if f['path'] == 'config/Settings.java')
    assert settings['reasons'] == ['CONTRACT']


def test_over_budget_mandatory_files_are_batched_without_loss():
    plan = context_plan(SOURCES, TASK, 'vision_index', ARCH, 'abc', max_bytes=1)
    assert plan['codePlan']['status'] == 'NEEDS_BATCHING'
    groups = batches(plan['selectedPaths'], SOURCES, max_bytes=70)
    assert set(sum(groups, [])) == set(plan['selectedPaths'])
    with pytest.raises(ValueError, match='SINGLE_FILE_OVER_BUDGET'):
        batches(plan['selectedPaths'], SOURCES, max_bytes=1)


def test_missing_or_fabricated_path_is_not_silently_dropped():
    with pytest.raises(ValueError, match='MISSING_MANDATORY'):
        context_plan(SOURCES, {**TASK, 'scannerPaths': ['missing/Source.java']}, 'code_index')
    with pytest.raises(ValueError, match='INVALID_MANIFEST_PATH'):
        context_plan(SOURCES, {**TASK, 'scannerPaths': ['../.env']}, 'code_index')


def test_bounded_extra_read_delivers_actual_source_to_inspector():
    seen = []
    def inspect(group):
        seen.extend(group)
        return {'notes': 'Need storage implementation.', 'readPaths': ['src/Store.java']}
    result = inspect_context(SOURCES, TASK,
        {'selectedPaths': ['src/Entry.java'], 'mandatoryPaths': ['src/Entry.java']}, inspect)
    assert seen == ['src/Entry.java', 'src/Store.java']
    assert result['extraReads'] == [['src/Store.java']]


def test_unresolved_retrieval_fails_instead_of_claiming_complete_context():
    with pytest.raises(ValueError, match='UNRESOLVED_READ_BUDGET'):
        inspect_context(SOURCES, TASK,
            {'selectedPaths': ['src/Entry.java'], 'mandatoryPaths': ['src/Entry.java']},
            lambda _: {'notes': '', 'readPaths': ['src/Store.java']}, max_extra_reads=0)


def test_edits_cannot_change_tests_or_ambiguous_matches():
    answer = {'reason': 'repair', 'edits': [{'path': '../tests/Test.java', 'before': 'a', 'after': 'b'}]}
    with pytest.raises(ValueError, match='EDIT_OUTSIDE_ALLOWLIST'):
        apply_edits(SOURCES, answer, set(SOURCES))
    with pytest.raises(ValueError, match='NON_UNIQUE'):
        apply_edits({'A.java': 'a a'}, {'reason': '', 'edits': [
            {'path': 'A.java', 'before': 'a', 'after': 'b'}]}, {'A.java'})


def test_exact_patch_produces_reviewable_diff_without_changing_other_files():
    updated, patch = apply_edits(SOURCES, {'reason': 'repair', 'edits': [
        {'path': 'config/Settings.java', 'before': 'false', 'after': 'true'}]}, {'config/Settings.java'})
    assert updated['src/Entry.java'] == SOURCES['src/Entry.java']
    assert patch['changedPaths'] == ['config/Settings.java']
    assert '+++ b/config/Settings.java' in patch['diff']


def test_balanced_schedule_and_paired_seeds():
    planned = schedule(3)
    for position in range(3):
        assert {planned[r * 3 + position]['arm'] for r in range(3)} == set(ARMS)
    for repeat in range(3):
        assert len({r['seed'] for r in planned[repeat * 3:repeat * 3 + 3]}) == 1


def rows(accepted=True):
    return [{**s, 'accepted': accepted, 'wallMs': 10, 'inputTokens': 100} for s in schedule(3)]


def test_fast_but_broken_and_both_broken_never_pass_quality_gate():
    values = rows()
    next(r for r in values if r['arm'] == 'vision_index').update(accepted=False, wallMs=1)
    result = compare(values, schedule(3), {})
    assert not result['comparisons']['full_code']['observedQualityPreserved']
    assert compare(rows(False), schedule(3), {})['comparisons']['code_index']['conclusion'] == 'QUALITY_GATE_FAILED'


def test_missing_duplicate_and_unknown_tokens_are_not_reported_as_complete_savings():
    values = rows()[:-1]
    assert compare(values, schedule(3), {})['comparisons']['code_index']['conclusion'] == 'INCOMPLETE'
    values = rows() + [rows()[0]]
    assert not compare(values, schedule(3), {})['arms']['full_code']['cohortComplete']
    values = rows()
    values[0]['inputTokens'] = None
    assert compare(values, schedule(3), {})['arms']['full_code']['inputTokens'] is None


def test_cold_vision_setup_can_cancel_warm_request_gain():
    values = rows()
    for row in values:
        if row['arm'] == 'vision_index':
            row['wallMs'] = 5
    report = compare(values, schedule(3), {'vision_index': 20})
    assert report['arms']['vision_index']['firstUseTotalMs'] == 35
    assert report['comparisons']['code_index']['observedQualityPreserved']
    assert not report['comparisons']['code_index']['firstUseTimeImproved']


def test_new_verified_success_can_improve_on_a_failing_baseline():
    values = rows(False)
    for value in values:
        if value['arm'] == 'vision_index':
            value['accepted'] = True
    report = compare(values, schedule(3), {'vision_index': 1})
    assert report['comparisons']['full_code']['observedQualityImproved']
    assert report['comparisons']['full_code']['conclusion'] == 'OBSERVED_QUALITY_IMPROVED'


def test_gate_rejects_missing_skipped_functional_tests_and_deleted_safe_logs():
    result = {'exitCode': 0, 'controlsPreserved': True, 'testsUnchanged': True,
              'cases': {'Suite#' + k: 'PASSED' for k in SECURITY_TESTS}}
    result['cases']['Suite#functional'] = 'PASSED'
    required = list(result['cases'])
    assert gate(result, required)
    result['cases']['Suite#functional'] = 'SKIPPED'
    assert not gate(result, required)
    result['cases']['Suite#functional'] = 'PASSED'
    result['controlsPreserved'] = False
    assert not gate(result, required)


def test_surefire_failures_and_skips_are_not_successes(tmp_path):
    reports = tmp_path / 'module/target/surefire-reports'
    reports.mkdir(parents=True)
    (reports / 'TEST-A.xml').write_text('''<testsuite>
      <testcase classname="A" name="good"/>
      <testcase classname="A" name="bad"><failure/></testcase>
      <testcase classname="A" name="notRun"><skipped/></testcase></testsuite>''')
    assert read_reports(tmp_path) == {'A#good': 'PASSED', 'A#bad': 'FAILED', 'A#notRun': 'SKIPPED'}


def test_equal_pass_counts_on_different_seeds_are_not_paired_quality_preservation():
    values = rows()
    next(r for r in values if r['arm'] == 'full_code' and r['repeat'] == 1)['accepted'] = False
    next(r for r in values if r['arm'] == 'vision_index' and r['repeat'] == 2)['accepted'] = False
    assert not compare(values, schedule(3), {})['comparisons']['full_code']['observedQualityPreserved']


def test_model_run_requires_successful_real_test_calibration(tmp_path):
    from benchmark_flink_patches import run
    (tmp_path / 'protocol.json').write_text('{}')
    (tmp_path / 'calibration.json').write_text('{"status":"BLOCKED"}')
    with pytest.raises(SystemExit, match='Calibration blocked'):
        run(tmp_path, allow_openai=True)
    assert not (tmp_path / 'calls').exists()


def test_truncated_model_output_keeps_tokens_failure_and_reservation(tmp_path, monkeypatch):
    import benchmark_flink_patches as module
    class Response:
        status_code = 200
        is_error = False
        def raise_for_status(self): pass
        def json(self):
            return {'done_reason': 'length', 'prompt_eval_count': 100, 'eval_count': 50,
                    'message': {'content': '{"incomplete":'}}
    class Transport:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs: Transport())
    client = module.Client(tmp_path, {'contextTokens': 32768, 'maxOutputTokens': 4096})
    with pytest.raises(ValueError, match='MODEL_CALL_FAILED'):
        client.call('trial', 'ollama', 'model', 'rules', {'publicSource': 'class A {}'}, {})
    receipt = json.loads((tmp_path / 'calls/trial.json').read_text())
    assert receipt['status'] == 'FAILED' and receipt['inputTokens'] == 100
    assert receipt['answerText'] == '{"incomplete":'
    with pytest.raises(ValueError, match='CALL_ALREADY_RESERVED'):
        client.call('trial', 'ollama', 'model', '', {}, {})


def test_unknown_provider_and_unenabled_external_call_fail_before_credentials(tmp_path):
    from benchmark_flink_patches import Client
    client = Client(tmp_path, {})
    with pytest.raises(ValueError, match='INVALID_PROVIDER'):
        client.call('x', 'remote', 'model', '', {}, {})
    with pytest.raises(ValueError, match='OPENAI_DISABLED'):
        client.call('x', 'openai', 'model', '', {}, {})
    assert not list(tmp_path.glob('calls/*.json'))


def test_inspection_length_still_enforced_outside_provider_grammar():
    with pytest.raises(ValueError, match='INVALID_INSPECTION'):
        inspect_context(SOURCES, TASK,
            {'selectedPaths': ['src/Entry.java'], 'mandatoryPaths': ['src/Entry.java']},
            lambda _: {'notes': 'x' * 8001, 'readPaths': []})


def test_reusing_real_vision_requires_matching_input_and_retains_provenance(tmp_path):
    from benchmark_flink_patches import reuse_vision, SYSTEM_PROMPT, _schema
    from flink_patch_protocol import sha
    src, out = tmp_path / 'source', tmp_path / 'out'
    (src / 'calls').mkdir(parents=True)
    config = {'commit': 'abc', 'imageSha256': 'image', 'visionProvider': 'openai', 'visionModel': 'model'}
    request = {'imageSha256': 'image', 'system': SYSTEM_PROMPT, 'schema': _schema()}
    call = {'status': 'COMPLETED', 'inputSha256': sha(request), 'answer': ARCH, 'wallMs': 100}
    cache = {'key': 'key', 'status': 'READY', 'context': ARCH, 'contextSha256': sha(ARCH), 'setupWallMs': 101}
    for name, data in [('protocol.json', config), ('architecture-cache.json', cache),
                       ('calls/architecture.json', call), ('calls/architecture-input.json', request)]:
        (src / name).write_text(json.dumps(data))
    result = reuse_vision(src, out, config, 'key')
    assert result['setupWallMs'] == 101
    assert result['reuse']['inferencePerformedInThisRun'] is False
    request['imageSha256'] = 'tampered'
    (src / 'calls/architecture-input.json').write_text(json.dumps(request))
    with pytest.raises(ValueError, match='VISION_REUSE_ARTIFACT_MISMATCH'):
        reuse_vision(src, tmp_path / 'tampered', config, 'key')
