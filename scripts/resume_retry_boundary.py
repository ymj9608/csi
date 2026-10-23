"""Recover valid array selections rejected by old benchmark parser; no resampling."""
from benchmark_retry_boundary import *
texts={p.name:p.read_text() for p in FIX.iterdir() if p.name!='test_contract.py'}
protocol=json.loads((OUT/'protocol.json').read_text())
assert protocol['sourceHashes']=={n:hashlib.sha256(t.encode()).hexdigest() for n,t in texts.items()}
assert protocol['testsSha256']==hashlib.sha256((FIX/'test_contract.py').read_bytes()).hexdigest()
client=LocalClient(OUT,{})
rows=[]
for arm in ['code_only','vision_context']:
 row={'arm':arm,'selectionRecovery':'Original valid response reused after harness rejected array type; no model retry.'}
 try:
  call=json.loads((OUT/'calls'/f'{arm}_select.json').read_text());selection=json.loads(call['answerText']);paths=selection['paths']
  assert len(paths)<=4 and len(set(paths))==len(paths) and all(p in texts and p not in INITIAL for p in paths)
  visible={p:texts[p] for p in INITIAL+paths};editable=[p for p in visible if p.endswith('.py') and p!='storage.py']
  write(OUT/(arm+'-selection.json'),{'paths':paths,'reason':selection['reason'],'visible':list(visible)})
  handoff=json.loads((OUT/'vision.json').read_text())['final'] if arm=='vision_context' else None
  answer=client.call(arm+'_patch','ollama',CODER,SYSTEM,{'task':TASK,'sources':visible,'architectureHandoff':handoff,'editablePaths':editable,'instruction':'Provide minimal exact before/after replacements. Every before must match exactly once in the file. Use only visible evidence. Explain the concrete exposure path, or acknowledge missing evidence.'},obj({'edits':{'type':'array','items':obj({'path':TEXT,'before':TEXT,'after':TEXT})},'risk':TEXT}))
  changed=dict(texts)
  for e in answer['edits']:
   if e['path'] not in editable or not e['before'] or changed[e['path']].count(e['before'])!=1:raise ValueError('INVALID_EDIT')
   changed[e['path']]=changed[e['path']].replace(e['before'],e['after'])
  f=setup(arm,changed);(f/'risk.txt').write_text(answer['risk'])
  (f/'candidate.patch').write_text(''.join(''.join(difflib.unified_diff(texts[p].splitlines(True),changed[p].splitlines(True),fromfile='a/'+p,tofile='b/'+p)) for p in changed))
  result=verify(f);write(f/'validation.json',result);row.update(status='PASSED' if result['exitCode']==0 and result['passed']==8 else 'VALIDATION_FAILED',selected=paths,validation=result)
 except Exception as e:row.update(status='FAILED',error=type(e).__name__+': '+str(e))
 rows.append(row);write(OUT/'recovered-comparison.json',rows);print(json.dumps(row),flush=True)
