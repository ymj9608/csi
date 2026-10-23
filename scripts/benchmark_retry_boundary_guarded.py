"""Paired source-grounded follow-up; cached actual Qwen observation; max one retry."""
from benchmark_retry_boundary import *
from retry_boundary_evidence import plan
OUT=ROOT/'docs/benchmarks/retry-boundary-guarded'

def main():
 OUT.mkdir(exist_ok=False)
 texts={p.name:p.read_text() for p in FIX.iterdir() if p.name!='test_contract.py'}
 previous=ROOT/'docs/benchmarks/retry-boundary'
 old=json.loads((previous/'protocol.json').read_text())
 assert old['sourceHashes']=={n:hashlib.sha256(t.encode()).hexdigest() for n,t in texts.items()}
 assert old['testsSha256']==hashlib.sha256((FIX/'test_contract.py').read_bytes()).hexdigest()
 vision=json.loads((previous/'vision.json').read_text());assert vision['status']=='COMPLETED'
 plans={arm:plan(texts,INITIAL,vision['final'] if arm=='vision_context' else None) for arm in ['code_only','vision_context']}
 write(OUT/'protocol.json',{'task':TASK,'plans':plans,'codingModel':CODER,'vision':'Reused actual Qwen image response; no new image call','visionResponseHash':hashlib.sha256((previous/'vision.json').read_bytes()).hexdigest(),'visionFirstUseSeconds':vision['seconds'],'maxRetriesPerArm':1,'maxNewModelCalls':4,'sourceHashes':old['sourceHashes'],'testsSha256':old['testsSha256'],'scope':'Benchmark harness only, not deployed production orchestration'})
 client=LocalClient(OUT,{})
 rows=[]
 schema=obj({'edits':{'type':'array','items':obj({'path':TEXT,'before':TEXT,'after':TEXT})},'risk':TEXT})
 for arm,p in plans.items():
  current=dict(texts);feedback=None;trials=[]
  editable=[x for x in p['selected'] if x.endswith('.py') and x!='storage.py']
  # Same verified import/config facts for both; vision adds only validated filename hints.
  evidence={k:p[k] for k in ['importGraph','externalConfig','configReaders','note']}
  for attempt in range(1,3):
   trial={'attempt':attempt,'status':'STARTED'}
   try:
    a=client.call(f'{arm}_{attempt}','ollama',CODER,SYSTEM,{'task':TASK,'sources':{x:current[x] for x in p['selected']},'evidence':evidence,'architectureFileHints':[x for x in p['visionMentionedFiles'] if x in p['selected']] if arm=='vision_context' else None,'editablePaths':editable,'feedback':feedback,'instruction':'Trace the original phone through failure processing to the configured external sink. Change only necessary code. Copying does not redact. Preserve internal records. Exact before/after edits against supplied current source; before must match once. If evidence is missing, do not claim safety.'},schema)
    changed=dict(current)
    for e in a['edits']:
     if e['path'] not in editable or not e['before'] or changed[e['path']].count(e['before'])!=1:raise ValueError('INVALID_EDIT')
     changed[e['path']]=changed[e['path']].replace(e['before'],e['after'])
    for path in editable:compile(changed[path],path,'exec')
    f=OUT/f'{arm}-{attempt}';f.mkdir()
    for path in FIX.iterdir():(f/path.name).write_bytes(path.read_bytes())
    for n,t in changed.items():(f/n).write_text(t)
    (f/'risk.txt').write_text(a['risk'])
    (f/'candidate.patch').write_text(''.join(''.join(difflib.unified_diff(texts[n].splitlines(True),changed[n].splitlines(True),fromfile='a/'+n,tofile='b/'+n)) for n in changed))
    result=verify(f);write(f/'validation.json',result)
    passed=result['exitCode']==0 and result['passed']==8
    trial.update(status='PASSED' if passed else 'VALIDATION_FAILED',validation=result)
    current=changed
    feedback={'failedCases':{k:v for k,v in result['cases'].items() if v!='ok'},'runtimeErrors':[line for line in (f/'test.log').read_text().splitlines() if line.startswith(('NameError:','TypeError:','KeyError:','ImportError:','AssertionError:'))][:12]}
   except Exception as e:
    trial.update(status='FAILED',error=type(e).__name__+': '+str(e));feedback={'error':trial['error']}
   trials.append(trial);write(OUT/f'{arm}-trials.json',trials);print(json.dumps({'arm':arm,**trial}),flush=True)
   if trial['status']=='PASSED':break
  rows.append({'arm':arm,'trials':trials});write(OUT/'comparison.json',rows)
if __name__=='__main__':main()
