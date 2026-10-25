#!/usr/bin/env python3
"""Real OpenAI-orchestrated smoke test; incurs API usage, no source-repository edits.

Uses real commit source and catalog excerpts with explicitly synthetic finding IDs.
Outputs may contain code: keep the private output directory out of Git.
"""
import argparse, base64, hashlib, json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import dotenv_values
from coding_agent.engine import generate
from coding_agent.profile import TARGET
from coding_agent.repository import git, Rejected
from coding_agent.worker import write_private
from coding_agent.openai_vlm import ResponsesClient, model_name
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo',type=Path,default=ROOT.parent/'Lichu')
parser.add_argument('--commit',default='95345dbd8ba45fe77ea8cd926c84e40e4d16f83a')
parser.add_argument('--diagram',type=Path,default=ROOT/'docs/benchmarks/lichu-architecture.png')
parser.add_argument('--output',type=Path,default=ROOT/'.runtime/vlm-orchestrator-smoke')
parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
args=parser.parse_args()
values=dotenv_values(args.env_file)
for key in ('OPENAI_API_KEY','CSI_VLM_MODEL','CSI_VLM_PROVIDER'):
    if values.get(key) and key not in os.environ:os.environ[key]=values[key]
api=ResponsesClient()
model_name()
repo=args.repo.resolve()
sha=args.commit
image=args.diagram.read_bytes()
refs=[r for r in json.loads((ROOT/'rag/catalog.json').read_text()) if r['sectionId'] in ('POL-04','POL-05')]
job={'repository':'ymj9608/Lichu','commitSha':sha,'policy':json.loads((ROOT/'rag/policy.json').read_text()),
     'findings':[{'id':'smoke-'+rule,'ruleId':rule,'filePath':TARGET,'analysis':{'references':refs}} for rule in ('SEC-02','SEC-03','SEC-05')],
     'architectureId':'11111111-1111-4111-8111-111111111111'}
job['architecture']={'id':job['architectureId'],'imageBase64':base64.b64encode(image).decode(),'imageSha256':hashlib.sha256(image).hexdigest(),'sourceCommitSha':sha}
out=args.output;out.mkdir(parents=True,exist_ok=True)
def vlm(payload):
    raw=api(payload)
    print(json.dumps({'stage':'VLM_RESPONSE','status':raw.get('status'),
                     'tools':[x.get('name') for x in raw.get('output',[]) if x.get('type')=='function_call'],
                     'usage':raw.get('usage')}),flush=True)
    return raw
original_state=(git(repo,'status','--porcelain'),git(repo,'diff','HEAD'))
started=time.monotonic()
try:
    result=generate(repo,job,vlm_chat=vlm,progress=lambda p:print(json.dumps(p),flush=True),diagnostics_dir=out)
    write_private(out/'result.json',result)
    summary={'status':result['status'],'commitSha':sha,'imageSha256':job['architecture']['imageSha256'],'durationMs':result['durationMs'],
             'handoffMetrics':result.get('handoff',{}).get('metrics'),
             'orchestratorModel':result.get('handoff',{}).get('model'),'trace':result.get('handoff',{}).get('trace'),
             'baseline':result.get('baseline'),'attempts':result['attempts'],'verification':result.get('verification'),'failureReason':result.get('failureReason'),
             'inputKind':'Lichu commit source + source-derived architecture PNG + catalog policy excerpts; synthetic finding IDs (not a live CSI job)',
             'backendDeliveryTested':False,'sourceRepositoryChanged':original_state!=(git(repo,'status','--porcelain'),git(repo,'diff','HEAD'))}
except Rejected as exc:
    summary={'status':'FAILED','errorCode':str(exc),'elapsedMs':round((time.monotonic()-started)*1000)}
write_private(out/'summary.json',summary)
print(json.dumps(summary,ensure_ascii=False),flush=True)

raise SystemExit(0 if summary['status']=='READY' else 1)
