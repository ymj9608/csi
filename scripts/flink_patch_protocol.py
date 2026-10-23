"""Paired patch experiment primitives. No model calls, labels or filesystem writes."""
import difflib
import hashlib
import json
from collections import deque

from architecture_agent.context import plan_context

ARMS = ('full_code', 'code_index', 'vision_index')


def sha(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(value).hexdigest()


def schedule(repeats=3):
    """Balanced order, paired seeds; never drop a failed scheduled trial."""
    return [{'repeat': repeat + 1, 'seed': 42 + repeat, 'arm': arm}
            for repeat in range(repeats)
            for arm in ARMS[repeat % 3:] + ARMS[:repeat % 3]]


def context_plan(sources, task, arm, architecture=None, commit=None, max_bytes=100_000):
    if arm not in ARMS:
        raise ValueError('INVALID_ARM')
    common = dict(changed_paths=task['changedPaths'], scanner_paths=task['scannerPaths'],
                  required_paths=task.get('readOnlyContractPaths', []),
                  expected_commit=commit, context_commit=commit, max_files=20,
                  max_bytes=max_bytes, max_hops=2)
    baseline = plan_context(sources, task['finding'], use_vision_context=False, **common)
    if baseline['unresolvedMandatory']:
        raise ValueError('MISSING_MANDATORY')
    selected = set(baseline['selectedPaths'])
    result = {'arm': arm, 'codePlan': baseline, 'visionPlan': None,
              'fallback': None, 'selectionRule': 'CODE_EVIDENCE_PRESERVING_UNION'}
    if arm == 'full_code':
        selected = set(sources)
    elif arm == 'vision_index':
        vision = plan_context(sources, task['finding'], architecture=architecture, **common)
        result['visionPlan'] = vision
        # Images may add/prioritize context, never evict code-only evidence.
        selected.update(vision['selectedPaths'])
        if not vision['decision']['useVisionContext']:
            result['fallback'] = vision['decision']['reason']
    mandatory = set(baseline['mandatoryPaths'])
    assert mandatory <= selected <= set(sources)
    result.update(selectedPaths=sorted(selected), mandatoryPaths=sorted(mandatory),
                  sourceBytes=sum(len(sources[p].encode()) for p in selected),
                  extraVisionPaths=sorted(selected - set(baseline['selectedPaths'])))
    return result


def batches(paths, sources, max_bytes=48_000):
    """Deliver every selected byte. An oversize file fails, never silently truncates."""
    result, batch, size = [], [], 0
    for path in sorted(set(paths)):
        n = len(sources[path].encode())
        if n > max_bytes:
            raise ValueError('SINGLE_FILE_OVER_BUDGET')
        if batch and size + n > max_bytes:
            result.append(batch)
            batch, size = [], 0
        batch.append(path)
        size += n
    if batch:
        result.append(batch)
    return result


def inspect_context(sources, task, plan, inspect, max_extra_reads=2):
    """Same bounded retrieval tools for all arms; labels/tests are never exposed."""
    pending = deque(batches(plan['selectedPaths'], sources))
    seen, notes, requests = set(), [], []
    extra_reads = 0
    while pending:
        group = pending.popleft()
        answer = inspect(group)
        seen.update(group)
        if (not isinstance(answer, dict) or set(answer) != {'notes', 'readPaths'}
                or not isinstance(answer['notes'], str) or len(answer['notes']) > 8000
                or not isinstance(answer['readPaths'], list)
                or any(not isinstance(p, str) or p not in sources for p in answer['readPaths'])):
            raise ValueError('INVALID_INSPECTION')
        notes.append({'paths': group, 'notes': answer['notes']})
        queued = {p for batch in pending for p in batch}
        missing = sorted(set(answer['readPaths']) - seen - queued)
        if missing:
            extra_reads += 1
            if extra_reads > max_extra_reads:
                raise ValueError('UNRESOLVED_READ_BUDGET')
            pending.extend(batches(missing, sources))
            requests.append(missing)
    if not set(plan['mandatoryPaths']) <= seen:
        raise ValueError('MISSING_MANDATORY')
    return {'notes': notes, 'seenPaths': sorted(seen), 'extraReads': requests}


def apply_edits(sources, answer, allowed):
    """Exact, unique replacements against supplied immutable bytes, no shell patch."""
    if (not isinstance(answer, dict) or set(answer) != {'edits', 'reason'}
            or not isinstance(answer['reason'], str) or not isinstance(answer['edits'], list)
            or not 1 <= len(answer['edits']) <= 24):
        raise ValueError('INVALID_PATCH_RESPONSE')
    edited = dict(sources)
    for edit in answer['edits']:
        if not isinstance(edit, dict) or set(edit) != {'path', 'before', 'after'}:
            raise ValueError('INVALID_EDIT')
        path, before, after = edit['path'], edit['before'], edit['after']
        if not isinstance(path, str) or path not in allowed or path not in sources:
            raise ValueError('EDIT_OUTSIDE_ALLOWLIST')
        if (not isinstance(before, str) or not before or not isinstance(after, str)
                or len(after) > 40_000 or before == after or edited[path].count(before) != 1):
            raise ValueError('NON_UNIQUE_OR_INVALID_EDIT')
        edited[path] = edited[path].replace(before, after, 1)
    changed = sorted(p for p in sources if edited[p] != sources[p])
    if not changed:
        raise ValueError('NO_CHANGE')
    diff = ''.join(''.join(difflib.unified_diff(sources[p].splitlines(True),
        edited[p].splitlines(True), fromfile='a/' + p, tofile='b/' + p)) for p in changed)
    return edited, {'changedPaths': changed, 'diff': diff,
                    'addedLines': sum(s.startswith('+') and not s.startswith('+++') for s in diff.splitlines()),
                    'removedLines': sum(s.startswith('-') and not s.startswith('---') for s in diff.splitlines())}


def compare(rows, expected_schedule, setup):
    """Only complete paired cohorts may claim observed quality preservation."""
    output = {'arms': {}, 'comparisons': {}, 'statisticalNoninferiorityProven': False}
    for arm in ARMS:
        data = [r for r in rows if r['arm'] == arm]
        expected = {s['repeat'] for s in expected_schedule if s['arm'] == arm}
        actual = [r['repeat'] for r in data]
        complete = len(actual) == len(set(actual)) and set(actual) == expected
        passed = {r['repeat'] for r in data if r.get('accepted') is True}
        tokens = [r.get('inputTokens') for r in data]
        metrics_complete = complete and all(isinstance(n, int) for n in tokens)
        output['arms'][arm] = {
            'scheduled': len(expected), 'recorded': len(data), 'cohortComplete': complete,
            'accepted': len(passed), 'passRate': len(passed) / len(expected) if expected else None,
            'inputTokens': sum(tokens) if metrics_complete else None,
            'requestWallMs': sum(r['wallMs'] for r in data),
            'firstUseTotalMs': (sum(r['wallMs'] for r in data) + setup.get(arm, 0)) if complete else None,
            'acceptedRepeats': sorted(passed),
        }
    vision = output['arms']['vision_index']
    for base in ('full_code', 'code_index'):
        control = output['arms'][base]
        comparable = control['cohortComplete'] and vision['cohortComplete']
        # Two equally broken pipelines must not be reported as quality-preserving.
        improved = (comparable and vision['accepted'] > control['accepted']
                    and set(control['acceptedRepeats']) <= set(vision['acceptedRepeats']))
        quality = improved or (comparable and control['accepted'] > 0 and vision['accepted'] > 0
                   and set(control['acceptedRepeats']) <= set(vision['acceptedRepeats']))
        faster = comparable and vision['firstUseTotalMs'] < control['firstUseTotalMs']
        fewer_tokens = (comparable and control['inputTokens'] is not None
                        and vision['inputTokens'] is not None
                        and vision['inputTokens'] < control['inputTokens'])
        output['comparisons'][base] = {
            'observedQualityPreserved': bool(quality),
            'observedQualityImproved': bool(improved),
            'firstUseTimeImproved': bool(faster) if comparable else None,
            'requestTokensReduced': bool(fewer_tokens) if comparable else None,
            'conclusion': 'INCOMPLETE' if not comparable else 'QUALITY_GATE_FAILED' if not quality
            else 'OBSERVED_QUALITY_IMPROVED_AND_TIME_IMPROVED' if improved and faster
            else 'OBSERVED_QUALITY_IMPROVED' if improved
            else 'OBSERVED_QUALITY_PRESERVED_AND_TIME_IMPROVED' if faster
            else 'QUALITY_PRESERVED_NO_TOTAL_TIME_GAIN',
        }
    return output
