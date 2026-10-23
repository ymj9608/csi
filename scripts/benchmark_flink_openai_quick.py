"""One-shot OpenAI pilot, sequential memory-capped verification, no local inference."""
import argparse
import json
import time
from pathlib import Path

from benchmark_flink_patches import Client, SYSTEM, patch_schema, implementation_hashes
from benchmark_flink import ROOT, PIN, TARGETS, source, write
from flink_patch_protocol import ARMS, context_plan, apply_edits, sha
from flink_patch_validation import validate, gate

OUT = ROOT / 'docs/benchmarks/flink/openai-quick'


def run(out):
    if out.exists():
        raise SystemExit('Keep previous attempts; choose a new output directory.')
    prior = ROOT / 'docs/benchmarks/flink/patch-v2-run'
    old = json.loads((prior / 'protocol.json').read_text())
    calibration = json.loads((prior / 'calibration.json').read_text())
    assert calibration['status'] == 'READY'
    texts = {p: source(p, 'mutated').decode() for p in old['paths']}
    assert {p: sha(t.encode()) for p, t in texts.items()} == old['sources']
    cache = json.loads((prior / 'architecture-cache.json').read_text())
    assert cache['status'] == 'READY' and sha(cache['context']) == cache['contextSha256']
    config = {**old, 'experiment': 'OPENAI_SINGLE_PASS_PILOT', 'codingProvider': 'openai',
              'codingModel': 'gpt-5.4-mini-2026-03-17', 'maxOutputTokens': 4096,
              'implementationHashes': implementation_hashes(),
              'runnerSha256': sha(Path(__file__).read_bytes()),
              'schedule': [{'arm': arm, 'repeat': 1} for arm in ARMS],
              'notes': ['One direct code request per arm, no inspection batching or repair retries.',
                        'Not a controlled model-speed comparison with the interrupted local batched run.',
                        'Real previous vision extraction reused; charge/time included once.',
                        'Fresh offline validation: 4GiB, no swap, 2 CPUs, Maven heap 1536MiB.',
                        'Reference calibration reused for unchanged fixtures; runtime resources reduced.']}
    write(out / 'protocol.json', config)
    write(out / 'calibration.json', calibration)
    write(out / 'architecture-cache.json', cache)
    client = Client(out, config, allow_openai=True)
    # Generate all three first, then compile sequentially; paid responses survive interruption.
    for arm in ARMS:
        start = time.perf_counter()
        architecture = cache['context'] if arm == 'vision_index' else None
        plan = context_plan(texts, old['task'], arm, architecture, PIN)
        write(out / arm / 'selection.json', plan)
        row = {'arm': arm, 'repeat': 1, 'accepted': False, 'status': 'STARTED'}
        try:
            answer = client.call(arm, 'openai', config['codingModel'], SYSTEM,
                {'task': old['task'], 'architectureAdvisory': architecture,
                 'sources': [{'path': p, 'source': texts[p]} for p in plan['selectedPaths']],
                 'editablePaths': TARGETS,
                 'instruction': 'Inspect all supplied sources and repair ALL stated regressions. Produce minimal exact search/replace edits; before must occur exactly once. Preserve safe logs and true/false configuration semantics. Do not claim tests passed.'}, patch_schema())
            _, patch = apply_edits(texts, answer, set(TARGETS))
            (out / arm / 'candidate.patch').write_text(patch.pop('diff'))
            row.update(status='GENERATED', patch=patch)
        except ValueError as exc:
            row.update(status='GENERATION_FAILED', error=str(exc))
        row['generationMs'] = round((time.perf_counter() - start) * 1000, 3)
        write(out / arm / 'result.json', row)
        print(json.dumps(row), flush=True)
    verify_all(out)


def verify_all(out):
    config = json.loads((out / 'protocol.json').read_text())
    calibration = json.loads((out / 'calibration.json').read_text())
    texts = {p: source(p, 'mutated').decode() for p in config['paths']}
    assert {p: sha(t.encode()) for p, t in texts.items()} == config['sources']
    for arm in ARMS:
        path = out / arm / 'result.json'
        row = json.loads(path.read_text())
        if row['status'] == 'GENERATED':
            answer = json.loads((out / 'calls' / (arm + '.json')).read_text())['answer']
            edited, _ = apply_edits(texts, answer, set(TARGETS))
            # No automatic rerun of an interrupted verification: preserve its artifacts.
            row['verification'] = validate(edited, out / arm / 'validation', calibration['imageId'])
            row['accepted'] = gate(row['verification'], calibration['requiredPassingTests'])
            row['status'] = 'PASSED' if row['accepted'] else 'VALIDATION_FAILED'
            write(path, row)
            print(json.dumps({'arm': arm, 'status': row['status']}), flush=True)
    rows = [json.loads((out / a / 'result.json').read_text()) for a in ARMS]
    (out / 'measurements.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    (verify_all if args.verify_only else run)(args.output)
