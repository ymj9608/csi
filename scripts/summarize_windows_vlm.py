"""Summarize recorded trials, retaining failures and unexecuted conditions.

Usage: python scripts/summarize_windows_vlm.py docs/benchmarks/windows-vlm-<id>
No inference calls. Ratios require BOTH compared trials to pass all tests.
"""
import csv
import json
import sys
from pathlib import Path


def summarize(out):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    execution_path=out/'execution.json'
    execution=json.loads(execution_path.read_text(encoding='utf-8')) if execution_path.exists() else {}
    rows=[]; comparisons=[]
    for case,arms in protocol['order'].items():
        by_arm={}
        for arm in arms:
            path=out/'pilot'/case/arm/'result.json'
            if not path.exists():
                status='INTERRUPTED' if (path.parent/'calls').exists() else 'NOT_RUN'
                if status=='INTERRUPTED' and execution.get('phase')=='PILOT' and execution.get('case')==case:
                    status='RUNNING'
                row={'case':case,'arm':arm,'status':status,'wallSeconds':None,'inputTokens':None,'outputTokens':None}
            else:
                result=json.loads(path.read_text(encoding='utf-8'))
                row={k:result.get(k) for k in ['case','arm','status','wallSeconds','inputTokens','outputTokens','failedCalls','error']}
                validation=result.get('verification') or {}
                row.update(testsPassed=validation.get('passed'),testsTotal=validation.get('total'),
                           readFiles=len(result.get('readPaths',[])),sourceFiles=result.get('sourceFileCount'))
                row['passesAllTests']=validation.get('exitCode')==0 and validation.get('passed')==validation.get('total')==8
                calls=[json.loads(p.read_text(encoding='utf-8')) for p in (path.parent/'calls').glob('*.json')
                       if not p.name.endswith('-input.json')]
                missing=sum(any(c.get(k) is None for k in ['inputTokens','outputTokens']) for c in calls)
                row.update(missingUsageCalls=missing, usageComplete=missing==0)
            rows.append(row); by_arm[arm]=row
        base,vision=by_arm['code_search'],by_arm['image_search']
        both=base['status']==vision['status']=='PASSED'
        comparisons.append({'case':case,'bothPassed':both,
                            'imageToCodeTimeRatio':round(vision['wallSeconds']/base['wallSeconds'],4) if both and base['wallSeconds'] else None,
                            'interpretation':'paired successful pilot only; no statistical inference' if both else 'quality-matched speed comparison unavailable'})
    compat=out/'compatibility.json'
    result={'kind':'local Windows calibration, not a confirmatory or enterprise benchmark',
            'plannedConditions':len(rows),'completedConditions':sum(r['status'] in {'PASSED','FAILED'} for r in rows),
            'interruptedConditions':sum(r['status']=='INTERRUPTED' for r in rows),
            'runningConditions':sum(r['status']=='RUNNING' for r in rows),
            'passedConditions':sum(r['status']=='PASSED' for r in rows),
            'compatibility':json.loads(compat.read_text(encoding='utf-8')) if compat.exists() else None,
            'conditions':rows,'pairedComparisons':comparisons,'limitations':protocol['limits']}
    (out/'summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    fields=['case','arm','status','wallSeconds','inputTokens','outputTokens','usageComplete','missingUsageCalls','testsPassed','testsTotal','readFiles','sourceFiles','failedCalls','error']
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
    return result


if __name__=='__main__':
    result=summarize(Path(sys.argv[1]))
    print(json.dumps({k:result[k] for k in ['plannedConditions','completedConditions','passedConditions','pairedComparisons']}))
