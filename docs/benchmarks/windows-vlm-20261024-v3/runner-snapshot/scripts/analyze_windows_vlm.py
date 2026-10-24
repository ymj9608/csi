"""Post-run diagnostics only; never supplies evaluator facts to the models.

Usage: python scripts/analyze_windows_vlm.py docs/benchmarks/windows-vlm-<id>
Keeps workflow success separate from test results and perception calibration.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.vlm_experiment_data import make_case


def analyze(out):
    protocol = json.loads((out / 'protocol.json').read_text(encoding='utf-8'))
    rows = []
    for case_id, arms in protocol['order'].items():
        family, size = case_id.split('-', 1)
        case = make_case(family, size == 'expanded')
        reference_paths = set(case['solution'])
        for arm in arms:
            folder = out / 'pilot' / case_id / arm
            if not (folder / 'result.json').exists():
                continue
            result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
            calls = {p.stem: json.loads(p.read_text(encoding='utf-8'))
                     for p in (folder / 'calls').glob('*.json')
                     if not p.name.endswith('-input.json')}
            models = {}
            for call in calls.values():
                value = models.setdefault(call['model'], {'calls': 0, 'failedCalls': 0,
                    'callsWithoutUsage': 0,
                    'wallSeconds': 0, 'loadSeconds': 0, 'promptSeconds': 0,
                    'generationSeconds': 0, 'inputTokens': 0, 'outputTokens': 0})
                value['calls'] += 1
                value['failedCalls'] += call['status'] != 'COMPLETED'
                value['callsWithoutUsage'] += any(call.get(k) is None for k in ['inputTokens', 'outputTokens'])
                value['wallSeconds'] += call.get('wallSeconds', 0)
                for target, source in [('loadSeconds', 'loadNs'), ('promptSeconds', 'promptNs'),
                                       ('generationSeconds', 'generationNs')]:
                    value[target] += (call.get(source) or 0) / 1e9
                for key in ['inputTokens', 'outputTokens']:
                    value[key] += call.get(key) or 0
            for value in models.values():
                for key in ['wallSeconds', 'loadSeconds', 'promptSeconds', 'generationSeconds']:
                    value[key] = round(value[key], 3)
            validations = []
            for path in sorted(folder.glob('candidate-*/validation.json')):
                value = json.loads(path.read_text(encoding='utf-8'))
                validations.append({'candidate': path.parent.name,
                    **{k: value.get(k) for k in ['exitCode', 'passed', 'total', 'cases', 'seconds']},
                    'exceptionLines': sorted({line[:300] for line in value.get('log', '').splitlines()
                        if re.match(r'^[A-Za-z_]\w*(?:Error|Exception):', line)})[:20]})
            first_input = folder / 'calls/coder-1-input.json'
            action_input = folder / 'calls/action-0-input.json'
            initial_paths = set()
            if action_input.exists():
                messages = json.loads(action_input.read_text(encoding='utf-8'))['messages']
                initial_paths = set(json.loads(messages[1]['content'])['sources'])
            seen = initial_paths.copy()
            redundant_reads = 0
            for action in result['trace']:
                if action['action'] == 'read' and action['path'] in case['sources']:
                    redundant_reads += action['path'] in seen
                    seen.add(action['path'])
            first_read = None
            if first_input.exists():
                messages = json.loads(first_input.read_text(encoding='utf-8'))['messages']
                supplied = json.loads(messages[1]['content'])['sources']
                first_read = reference_paths <= set(supplied)
            rows.append({'case': case_id, 'arm': arm, 'status': result['status'],
                         'error': result.get('error'), 'wallSeconds': result['wallSeconds'],
                         'attempts': result['attempts'],
                         'actions': dict(Counter(a['action'] for a in result['trace'])),
                         'initialReadFiles': len(initial_paths),
                         'newlyReadPaths': sorted(set(result['readPaths']) - initial_paths),
                         'readActionsOnAlreadySuppliedFiles': redundant_reads,
                         'referenceRepairFilesReadBeforeFirstDelegation': first_read,
                         'referenceRepairFilesReadByEnd': reference_paths <= set(result['readPaths']),
                         'failedModelCalls': [{'call': name, 'error': call.get('error'),
                                              'wallSeconds': call.get('wallSeconds')}
                                             for name, call in calls.items() if call['status'] != 'COMPLETED'],
                         'candidateValidations': validations, 'byModel': models})
    memory = []
    resource_path = out / 'resources.jsonl'
    if resource_path.exists():
        for line in resource_path.read_text(encoding='utf-8').splitlines():
            try:
                memory.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a live monitor may not have finished its last line
    result = {'kind': 'POST_RUN_DIAGNOSTICS',
              'notes': ['Reference repair file coverage is evaluator-only and does not prove correct reasoning.',
                        'Alternative repairs may exist; reference file coverage is not a pass criterion.',
                        'Token and model timing sums include failed calls when usage was returned.',
                        'Missing usage on timeouts is unmeasured, not zero; token sums are lower bounds if callsWithoutUsage is nonzero.',
                        'Provider load/prompt/generation timing is not an exact wall-time decomposition.',
                        'Resource samples describe the whole desktop, not isolated process memory.'],
              'conditions': rows,
              'minimumAvailableRamGiB': round(min(r['availableRamBytes'] for r in memory)/2**30, 3) if memory else None,
              'maximumSystemMemoryLoadPercent': max(r['memoryLoadPercent'] for r in memory) if memory else None}
    (out / 'diagnostics.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    result = analyze(Path(sys.argv[1]))
    print(json.dumps({'conditions': len(result['conditions']),
                      'minimumAvailableRamGiB': result['minimumAvailableRamGiB']}))
