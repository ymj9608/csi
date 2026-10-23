"""Real image-selected file/function -> evidence validation -> bounded local patch."""
import argparse,ast,re,shutil
import benchmark_retry_boundary as base
from benchmark_retry_boundary import *
from retry_boundary_evidence import plan
from coding_agent.scoped_handoff import build_handoff,replace_function
from coding_agent.call_contract import CONTRACT_RULES
OUT=ROOT/'docs/benchmarks/retry-boundary-scoped'

def main():
 global OUT
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,default=OUT)
 OUT=parser.parse_args().output.resolve()
 OUT.mkdir(exist_ok=False)
 previous=ROOT/'docs/benchmarks/retry-boundary'
 shutil.copyfile(previous/'architecture.png',OUT/'architecture.png')
 texts={p.name:p.read_text() for p in FIX.iterdir() if p.name!='test_contract.py'}
 old=json.loads((previous/'protocol.json').read_text())
 assert old['sourceHashes']=={n:hashlib.sha256(t.encode()).hexdigest() for n,t in texts.items()}
 assert old['testsSha256']==hashlib.sha256((FIX/'test_contract.py').read_bytes()).hexdigest()
 evidence=plan(texts,INITIAL)
 declarations={n:[x.name for x in ast.parse(t).body if isinstance(x,ast.FunctionDef)] for n,t in texts.items() if n.endswith('.py')}
 write(OUT/'protocol.json',{'task':TASK,'evidencePlan':evidence,'declarations':declarations,'visionModel':'qwen3-vl:8b','codingModel':CODER,'newVisionCall':True,'maxCodingCalls':4,'maxRetriesPerArm':1,'testsSha256':old['testsSha256'],'sourceHashes':old['sourceHashes'],'contractVersion':2,'contractRules':CONTRACT_RULES,'retryBase':'original source, never failed patch','scope':'One existing function only. Same caller contracts, boundary restriction and tests in both arms. Benchmark scope guard; production has its existing profile validator.'})
 base.OUT=OUT
 v=base.vision('Read the architecture image and choose ONE existing function to inspect/modify for preventing phone from reaching external failure observability, preserving internal notification and replay. Available source declarations: '+json.dumps(declarations)+'. Return these three lines, no JSON: FILE: exact filename; FUNCTION: exact function name; REASON: brief diagram-grounded instruction. Do not invent code or claim tests passed. Keep the final answer under 80 words.')
 if v['status']!='COMPLETED':return
 m=re.search(r'FILE:\s*`?([\w]+\.py)',v['final']);n=re.search(r'FUNCTION:\s*`?(\w+)',v['final'])
 if not m or not n:
  write(OUT/'selection-validation.json',{'status':'REJECTED','reason':'SELECTION_FORMAT'});return
 selected=m.group(1);symbol=n.group(1)
 # Candidate must be a reachable config-reading boundary, never just an image label.
 allowed=set(evidence['configReaders'])
 if selected not in allowed:
  write(OUT/'selection-validation.json',{'status':'REJECTED','reason':'TARGET_NOT_VERIFIED_BOUNDARY','file':selected});return
 contexts=[p for p in evidence['selected'] if p!=selected]
 preserve=['Internal phone and archive stay intact','External export still contains event id, error and attempts','No modifications outside selected function']
 visual=build_handoff(texts,selected,symbol,allowed,contexts,v['final'],preserve)
 write(OUT/'selection-validation.json',{'status':'SOURCE_VERIFIED','file':selected,'function':symbol,'basis':'existing AST declaration; reachable imports; actual external configuration. Not proof of safety.'})
 # Code-only uses the identical deterministic boundary rule, without image-derived instructions.
 target=sorted(allowed)[0]
 names=declarations[target]
 if len(names)!=1:raise ValueError('AMBIGUOUS_CODE_ONLY_TARGET')
 plain=build_handoff(texts,target,names[0],allowed,[p for p in evidence['selected'] if p!=target],TASK,preserve)
 client=LocalClient(OUT,{});rows=[]
 for arm,packet in [('code_only',plain),('vision_context',visual)]:
  write(OUT/f'{arm}-handoff.json',packet);trials=[];current=texts[packet['path']];feedback=None
  for attempt in range(1,3):
   trial={'attempt':attempt}
   try:
    # Refresh binding on retry while preserving initial scope.
    active=build_handoff({**texts,packet['path']:current},packet['path'],packet['function'],allowed,list(packet['evidence']),packet['instruction'],preserve)
    answer=client.call(f'{arm}_{attempt}','ollama',CODER,SYSTEM+'\n'+CONTRACT_RULES,{'task':TASK,'handoff':active,'feedback':feedback,'instruction':'Read inputContract.calls first: arguments describe the INPUT before the function wraps its OUTPUT. Return the complete replacement function only in functionCode, with its original signature. All imports already visible remain available. Preserve the original envelope structure and diagnostic fields; change only the private field in a copy for the external destination. Do not stop allowed delivery or change unrelated functions. Do not claim validation passed.'},obj({'functionCode':TEXT,'risk':TEXT}))
    after=replace_function(current,active,answer['functionCode'])
    folder=OUT/f'{arm}-{attempt}';folder.mkdir()
    for p in FIX.iterdir():(folder/p.name).write_bytes(p.read_bytes())
    (folder/packet['path']).write_text(after);(folder/'risk.txt').write_text(answer['risk'])
    (folder/'candidate.patch').write_text(''.join(difflib.unified_diff(texts[packet['path']].splitlines(True),after.splitlines(True),fromfile='a/'+packet['path'],tofile='b/'+packet['path'])))
    result=verify(folder);write(folder/'validation.json',result)
    passed=result['exitCode']==0 and result['passed']==8
    trial.update(status='PASSED' if passed else 'VALIDATION_FAILED',validation=result)
    feedback={'failedCases':{k:x for k,x in result['cases'].items() if x!='ok'},'errors':[line for line in (folder/'test.log').read_text().splitlines() if line.startswith(('NameError:','TypeError:','KeyError:','AssertionError:'))][:10]}
   except Exception as exc:
    trial.update(status='FAILED',error=type(exc).__name__+': '+str(exc));feedback={'error':trial['error']}
   trials.append(trial);write(OUT/f'{arm}-trials.json',trials);print(json.dumps({'arm':arm,**trial}),flush=True)
   if trial['status']=='PASSED':break
  rows.append({'arm':arm,'trials':trials});write(OUT/'comparison.json',rows)
if __name__=='__main__':main()
