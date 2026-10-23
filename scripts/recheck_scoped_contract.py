"""Replay BOTH first model responses through the improved boundary adapter.

No sampling, hand-written fixes, new model calls or changed tests. Preserve failed
original attempts and expose their incurred costs separately from replay results.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

from benchmark_retry_boundary import ROOT, FIX, verify, write
from coding_agent.scoped_handoff import replace_function


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs/benchmarks/retry-boundary-contract-v2')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/benchmarks/retry-boundary-contract-v3')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    out.mkdir(exist_ok=False)
    original = json.loads((source / 'protocol.json').read_text())
    texts = {p.name: p.read_text() for p in FIX.iterdir() if p.is_file() and p.name != 'test_contract.py'}
    hashes = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in texts.items()}
    assert hashes == original['sourceHashes']
    assert hashlib.sha256((FIX / 'test_contract.py').read_bytes()).hexdigest() == original['testsSha256']
    responses = {arm: source / 'calls' / (arm + '_1.json') for arm in ('code_only', 'vision_context')}
    write(out / 'protocol.json', {
        'sourceRun': str(source.relative_to(ROOT)), 'newModelCalls': 0,
        'selection': 'First response of each arm, no best-of selection',
        'sourceHashes': hashes, 'testsSha256': original['testsSha256'],
        'responseHashes': {arm: hashlib.sha256(path.read_bytes()).hexdigest() for arm, path in responses.items()},
        'normalization': 'If entire module returned, require unchanged AST outside target, then extract original model function verbatim. No semantic edits.',
        'limitations': ['Offline replay of recorded model responses, not a fresh inference trial.',
                       'Single small synthetic scenario. No evidence of general vision superiority.'],
    })
    rows = []
    for arm, response_path in responses.items():
        row = {'arm': arm}
        response = json.loads(response_path.read_text())
        packet = json.loads((source / (arm + '-handoff.json')).read_text())
        folder = out / arm
        folder.mkdir()
        try:
            candidate = replace_function(texts[packet['path']], packet, response['answer']['functionCode'])
            for path in FIX.iterdir():
                if path.is_file():
                    (folder / path.name).write_bytes(path.read_bytes())
            (folder / packet['path']).write_text(candidate)
            (folder / 'candidate.patch').write_text(''.join(difflib.unified_diff(
                texts[packet['path']].splitlines(True), candidate.splitlines(True),
                fromfile='a/' + packet['path'], tofile='b/' + packet['path'])))
            result = verify(folder)
            row.update(status='PASSED' if result['exitCode'] == 0 and result['passed'] == 8 else 'FAILED', validation=result)
        except (ValueError, KeyError) as exc:
            row.update(status='BLOCKED', error=str(exc))
        row['recordedFirstGenerationMs'] = response['wallMs']
        row['recordedFirstInputTokens'] = response['inputTokens']
        row['recordedFirstOutputTokens'] = response['outputTokens']
        # All attempts really incurred remain visible, even if unnecessary under new adapter.
        calls = [json.loads(p.read_text()) for p in (source / 'calls').glob(arm + '_[0-9].json')]
        row['incurredGenerationMsAllAttempts'] = sum(c['wallMs'] for c in calls)
        row['incurredInputTokensAllAttempts'] = sum(c['inputTokens'] for c in calls)
        if arm == 'vision_context':
            vision = json.loads((source / 'vision.json').read_text())
            row['recordedVisionMs'] = vision['seconds'] * 1000
            row['recordedVisionInputTokens'] = vision['inputTokens']
        write(folder / 'validation.json', row)
        rows.append(row)
        print(json.dumps(row), flush=True)
    write(out / 'comparison.json', rows)


if __name__ == '__main__':
    main()
