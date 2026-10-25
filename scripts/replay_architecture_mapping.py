"""Replay cached extraction through old/new routing, without model inference."""
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE_REVISION='fbdbce563a8d2b98ac4e3a2a05cc5c4141707bbb'
sys.path.insert(0,str(ROOT))
from scripts.build_complex_architecture_fixture import DOMAINS, service_sources, specialized_sources
from architecture_agent.routing import plan_routed_context


def main():
    out=Path(sys.argv[1])
    if out.exists(): raise ValueError('REFUSE_OVERWRITE')
    sources={}
    for domain in DOMAINS: sources.update(service_sources(domain))
    sources.update(specialized_sources())
    manifest=json.loads((ROOT/'tests/fixtures/complex_architecture/manifest.json').read_text(encoding='utf-8'))
    assert {e['path']:e['sha256'] for e in manifest['files']}=={
        p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources.items()}
    old=types.ModuleType('architecture_agent.previous_routing'); old.__package__='architecture_agent'
    previous=subprocess.check_output(['git','show',BASE_REVISION+':architecture_agent/routing.py'],cwd=ROOT).decode('utf-8')
    exec(compile(previous,'<previous committed routing>','exec'),old.__dict__)
    context_path=ROOT/'docs/benchmarks/complex-mock/readable-v2/qwen3-vl-8b-final/context-1-original.json'
    context=json.loads(context_path.read_text(encoding='utf-8'))
    expected=json.loads((ROOT/'tests/fixtures/complex_architecture/ground_truth.json').read_text(encoding='utf-8'))
    required={item['path'] for item in expected['required_context_paths']}
    rows={}
    for name,fn in [('before',old.plan_routed_context),('after',plan_routed_context)]:
        plan=fn(sources,{'filePath':'services/customer_profile/service.py','field':'telephone'},
                architecture=context,use_vision_context=True,max_files=96,max_bytes=96000,max_hops=3)
        rows[name]={'mapping':plan['mappingCount'],'decision':plan['decision'],
                    'selectedCount':len(plan['selectedPaths']),
                    'requiredPathsFound':sorted(required & set(plan['selectedPaths'])),
                    'requiredPathsMissing':sorted(required-set(plan['selectedPaths']))}
    out.parent.mkdir(parents=True,exist_ok=True)
    result={'kind':'cached-response replay; ZERO new model calls',
            'beforeRevision':BASE_REVISION,
            'sourceFiles':len(sources),'contextSha256':hashlib.sha256(context_path.read_bytes()).hexdigest(),
            'beforeCodeSha256':hashlib.sha256(previous.encode()).hexdigest(),
            'afterCodeSha256':hashlib.sha256((ROOT/'architecture_agent/routing.py').read_bytes()).hexdigest(),
            'results':rows,'limit':'Tests mapping/selection only; does not establish detection or remediation quality.'}
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__': main()
