"""Post-run evidence audit. Does not alter prompts, raw outputs or candidate code."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_privacy_mvp import frozen, summarize, ARMS
from scripts.privacy_mvp_data import case
from scripts.benchmark_windows_vlm import sha, write


def analyze(out):
    frozen(out); summary=summarize(out); rows=[]; candidate_count=0
    for path in sorted((out/'runs').glob('*/*/*/result.json')):
        result=json.loads(path.read_text(encoding='utf-8')); value=case(result['case'])
        truth=value['graph']; actual_external=sorted({c for c in truth['normal']+truth['failure'] if truth['routes'][c]['boundary']=='EXTERNAL'})
        aliases={}
        for channel,route in truth['routes'].items():
            aliases[channel]=channel
            aliases[f"{channel} / {route['boundary']}"]=channel
            aliases[f"{channel} / {route['boundary']} {route['name']}"]=channel
        normalize=lambda values: [aliases.get(v,v) for v in values]
        plans=[]
        for attempt in result['attempts']:
            plan=attempt.get('plan')
            if plan:
                plans.append({'attempt':attempt['number'],
                              'externalCorrect':sorted(plan['external_recipients'])==actual_external,
                              'normalCorrect':plan['normal_recipients']==truth['normal'],
                              'failureCorrect':plan['failure_recipients']==truth['failure'],
                              'posthocLabelNormalizedExternalCorrect':sorted(normalize(plan['external_recipients']))==actual_external,
                              'posthocLabelNormalizedNormalCorrect':normalize(plan['normal_recipients'])==truth['normal'],
                              'posthocLabelNormalizedFailureCorrect':normalize(plan['failure_recipients'])==truth['failure']})
        for folder in path.parent.glob('candidate-*'):
            candidate_count+=1
            assert (folder/'test_contract.py').read_text(encoding='utf-8')==value['tests']
            for name,source in value['sources'].items():
                if name not in value['editable']: assert (folder/name).read_text(encoding='utf-8')==source
            assert (folder/'validation.json').exists(), str(folder)
        for request in (path.parent/'calls').glob('*-input.json'):
            packet=json.loads(request.read_text(encoding='utf-8'))
            image_count=sum(len(m.get('imageHashes',[])) for m in packet['messages'])
            expected=1 if request.name.startswith('plan-') and result['arm']=='code_image' else 0
            assert image_count==expected
            if request.name in ('plan-1-input.json','coder-1-input.json'):
                content='\n'.join(m['content'] for m in packet['messages'])
                assert value['tests'] not in content
                assert value['solution']['adapter.py'] not in content
        last=result['attempts'][-1].get('verification',{}) if result['attempts'] else {}
        rows.append({**{k:result.get(k) for k in ('seed','case','arm','status','bestPassed','wallSeconds','vlmSeconds','coderSeconds','inputTokens','outputTokens','usageComplete')},
                     'attemptCount':len(result['attempts']),'lastPassed':last.get('passed'),
                     'lastTotal':last.get('total'),'plans':plans,
                     'verification': [a.get('verification',{}) for a in result['attempts']]})
    summary['executedSeeds']=sorted({r['seed'] for r in rows})
    summary['replicationStatus']='EXECUTED' if 43 in summary['executedSeeds'] else 'NOT_RUN'
    aggregates={}
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm]
        aggregates[arm]={'conditions':len(selected),'passed':sum(r['status']=='PASSED' for r in selected),
                         'firstAttemptPasses':sum(r['status']=='PASSED' and r['attemptCount']==1 for r in selected),
                         'meanWallSeconds':round(sum(r['wallSeconds'] for r in selected)/len(selected),3) if selected else None,
                         'meanCoderSeconds':round(sum(r['coderSeconds'] for r in selected)/len(selected),3) if selected else None,
                         'firstPlanFullyCorrect':sum(bool(r['plans']) and all(r['plans'][0][k] for k in ('externalCorrect','normalCorrect','failureCorrect')) for r in selected),
                         'posthocLabelNormalizedFirstPlanFullyCorrect':sum(bool(r['plans']) and all(r['plans'][0][k] for k in ('posthocLabelNormalizedExternalCorrect','posthocLabelNormalizedNormalCorrect','posthocLabelNormalizedFailureCorrect')) for r in selected)}
    paired=[]
    for seed in (42,43):
        for name in ('fanout','recovery','audit','profile'):
            pair={r['arm']:r for r in rows if r['seed']==seed and r['case']==name}
            if len(pair)==2 and all(r['status']=='PASSED' for r in pair.values()):
                paired.append({'seed':seed,'case':name,'codeSeconds':pair['code_only']['wallSeconds'],
                               'imageSeconds':pair['code_image']['wallSeconds'],
                               'codeOverImageRatio':round(pair['code_only']['wallSeconds']/pair['code_image']['wallSeconds'],3)})
    memory=[json.loads(line)['availableRamBytes'] for line in (out/'resources.jsonl').read_text(encoding='utf-8').splitlines()]
    audit={'inputAndRunnerHashesValid':True,'unchangedTestCandidates':candidate_count,
           'imageOnlyGivenToImageArmPlanner':True,'noInitialTestsOrReferencePatchInPrompts':True,
           'minimumAvailableRamBytes':min(memory) if memory else None,
           'designLimitations':[
               'Diagram scenario titles are not separately included in the text-only packet. Route/trust facts are shared, but this is not a perfectly matched text-versus-image representation ablation.',
               'Exact external-payload tests require deleting phone/email fields. A safe constant replacement can fail despite removing the original sensitive value. Do not equate every failed contract with continued disclosure.',
               'Four synthetic scenarios and one initial run per condition cannot establish statistical superiority.',
               'Normalized plan labels are an explicitly post-hoc representation diagnostic, not a prespecified perception accuracy metric.'],
           'note':'Static prompt checks are supplemented by source review; test failure feedback is intentionally provided on retry.'}
    report={'summary':summary,'aggregates':aggregates,'matchedSuccessfulPairs':paired,'audit':audit,'conditions':rows}
    write(out/'diagnostics.json',report)
    (out/'README.txt').write_text(
        'Privacy MVP paired experiment\n'
        'Branch: experiment/privacy-mvp-vision\n'
        'Read protocol.json for frozen inputs, budgets, schedule and the predeclared integration gate.\n'
        'comparison.csv: per-condition measured times and best verification score.\n'
        'diagnostics.json: source/test audit, first-plan structural accuracy and matched-success timings.\n'
        'runs/: original model requests/responses, unchanged candidate sources and WASI verifier logs.\n'
        'controls/: known-correct and intentionally wrong candidates, not supplied to models.\n'
        'calibration/: separate direct-coder task; excluded from paired success rates.\n'
        'Images are authored source-derived component diagrams. Route/trust facts exist in code-only input; scenario titles are image-only context (see diagnostics design limitations).\n'
        'This measures known-vulnerability remediation, not detection recall or a real production deployment.\n'
        'A best partial score is diagnostic only and never a publishable patch.\n',encoding='utf-8')
    print(json.dumps({'summary':summary,'aggregates':aggregates,'audit':audit}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=Path)
    analyze(parser.parse_args().out.resolve())
