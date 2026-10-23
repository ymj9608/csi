"""Same frozen small event task, Qwen handoff and Ministral patches, no cloud calls."""
import json,time,hashlib
from pathlib import Path
import httpx
import benchmark_signup_events as run
from benchmark_signup_micro import write
QWEN='qwen3-vl:8b'
CODER='ministral-3:8b-instruct-2512-q4_K_M'
OUT=run.ROOT/'docs/benchmarks/signup-events-local-v3'
class LocalClient:
 def __init__(self,out,config,allow_openai=False):
  self.out=out
 def call(self,name,provider,model,system,body,schema):
  model=QWEN if name=='handoff' else CODER
  path=self.out/'calls'/f'{name}.json';path.parent.mkdir(exist_ok=True)
  if path.exists():raise ValueError('CALL_ALREADY_RESERVED')
  payload={'model':model,'stream':False,'think':name=='handoff','format':schema,'keep_alive':0,
   'options':{'num_ctx':8192,'num_predict':1800 if name=='handoff' else 2400,'temperature':0,'seed':42},
   'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(body,ensure_ascii=False)}]}
  if name=='handoff':
   payload.pop('format')
   payload['messages'][0]['content'] += ' Return a short plain-text implementation instruction, not JSON.'
  write(path.with_name(name+'-input.json'),payload)
  row={'model':model,'provider':'ollama','status':'STARTED','startedAtUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};write(path,row)
  start=time.perf_counter()
  try:
   with httpx.Client(timeout=180,trust_env=False) as api:
    response=api.post('http://127.0.0.1:11434/api/chat',json=payload);response.raise_for_status();raw=response.json()
   # Do not persist private thinking content.
   answer=raw.get('message',{}).get('content','')
   row.update(finalContentChars=len(answer),thinkingPresent=bool(raw.get('message',{}).get('thinking')),answerText=answer,inputTokens=raw.get('prompt_eval_count'),outputTokens=raw.get('eval_count'),doneReason=raw.get('done_reason'),loadNs=raw.get('load_duration'),generationNs=raw.get('eval_duration'))
   if raw.get('done_reason')!='stop':raise ValueError('OUTPUT_INCOMPLETE')
   if not answer.strip():raise ValueError('EMPTY_FINAL_CONTENT')
   value={'handoff':answer} if name=='handoff' else json.loads(answer)
   if not isinstance(value,dict) or set(value)!=set(schema['required']):raise ValueError('INVALID_SCHEMA')
   for key, spec in schema['properties'].items():
    expected = str if spec['type']=='string' else list if spec['type']=='array' else dict
    if not isinstance(value[key],expected):raise ValueError('INVALID_SCHEMA')
   row.update(status='COMPLETED',answer=value)
   return value
  except Exception as exc:
   row.update(status='FAILED',error=type(exc).__name__+': '+str(exc)[:180]);raise
  finally:
   row['wallMs']=round((time.perf_counter()-start)*1000,3);write(path,row)
   with httpx.Client(timeout=20,trust_env=False) as api:
    api.post('http://127.0.0.1:11434/api/generate',json={'model':model,'keep_alive':0})
   print(json.dumps({k:row.get(k) for k in ['model','status','wallMs','inputTokens','outputTokens']}),flush=True)
if __name__=='__main__':
 OUT.mkdir(exist_ok=True)
 if (OUT/'protocol.json').exists():raise SystemExit('Existing experiment; refusing overwrite')
 with httpx.Client(timeout=10,trust_env=False) as api:
  tags=api.get('http://127.0.0.1:11434/api/tags').json()
  loaded=api.get('http://127.0.0.1:11434/api/ps').json()
  if loaded.get('models'):raise SystemExit('Other models loaded; refusing to overlap')
  models={m['name']:m for m in tags['models']}
  for model in [QWEN,CODER]:
   if model not in models:raise SystemExit('Model not installed: '+model)
 write(OUT/'local-protocol.json',{'handoffModel':QWEN,'codingModel':CODER,'models':{m:models[m] for m in [QWEN,CODER]},'contextTokens':8192,'handoffOutputLimit':1800,'codeOutputLimit':2400,'keepAlive':0,'timeoutSeconds':180,'maxCalls':3,'retries':0,'perception':'assumed correct; no image inference','cloudCalls':0,'amendment':'User requires qwen3-vl:8b unchanged. Preserve two previous failures. This run requests think=true and increases handoff budget from 600 to 1800; no Instruct model used. Three fresh calls; prior failures remain.'})
 run.OUT=OUT;run.MODEL=CODER;run.Client=LocalClient
 run.main()
