#!/usr/bin/env python3
"""Controlled diagram redraw experiment: Qwen vision, frozen Ministral review.

Old measurements are read-only. Image order is original/readable/readable/original.
Downstream review uses the first schema-valid extraction, never the best score.
"""
from __future__ import annotations

import argparse
import base64
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from scripts import benchmark_complex_architecture as base
from architecture_agent.vision import CONTEXT_KEYS, SYSTEM_PROMPT, _schema, image_dimensions, validate_context
from architecture_agent.routing import plan_routed_context

DRAWING=base.PUBLIC/'readable-v2'
PUBLIC=DRAWING/'qwen3-vl-8b'
VISION_MODEL='qwen3-vl:8b'
VISION_OPTIONS={**base.OPTIONS,'num_predict':6144}
VISION_ORDER=('original','readable','readable','original')
REVIEW_ORDER=('code_index','original','readable')
IMAGES={'original':base.PUBLIC/'architecture.png','readable':DRAWING/'architecture.png'}
USER_PROMPT='Extract visible components and arrows as advisory context.'


def frozen_hashes():
    previous=json.loads((base.PUBLIC/'protocol.json').read_text())
    for name,value in previous['hashes'].items():
        if base.digest((ROOT/name).read_bytes())!=value:
            raise ValueError('ORIGINAL_INPUT_CHANGED: '+name)
    paths=[Path(__file__),ROOT/'scripts/render_readable_architecture.py',ROOT/'architecture_agent/vision.py',
           DRAWING/'architecture.png',DRAWING/'architecture.svg',DRAWING/'architecture.render.json',
           base.PUBLIC/'measurements.jsonl',base.PUBLIC/'protocol.json']
    return {**previous['hashes'],**{str(p.relative_to(ROOT)):base.digest(p.read_bytes()) for p in paths}}


def prepare():
    target=PUBLIC/'protocol.json'
    if target.exists():
        raise ValueError('PROTOCOL_EXISTS')
    manifest,sources=base.read_sources()
    dimensions={name:image_dimensions(path.read_bytes()) for name,path in IMAGES.items()}
    if len(set(dimensions.values()))!=1:
        raise ValueError('IMAGE_DIMENSIONS_DIFFER')
    old=json.loads((base.PUBLIC/'protocol.json').read_text())
    base.write(target,{'schemaVersion':1,'createdAt':datetime.now(timezone.utc).isoformat(),
        'visionModel':VISION_MODEL,'reviewModel':base.DEFAULT_MODEL,'visionOptions':VISION_OPTIONS,
        'reviewOptions':base.OPTIONS,'visionOrder':VISION_ORDER,'reviewOrder':REVIEW_ORDER,
        'visionSystemPrompt':SYSTEM_PROMPT,'visionUserPrompt':USER_PROMPT,
        'reviewSystemPrompt':base.SYSTEM,'reviewTask':base.TASK,
        'budget':old['budget'],'maxFollowupCalls':2,'anchor':base.ANCHOR,
        'sourceSha256':manifest['sourceSha256'],'sourceFiles':len(sources),'dimensions':dimensions,
        'contextSelection':'First schema-valid extraction per drawing; score is never used to choose a context.',
        'hashes':frozen_hashes(),
        'limits':['Two image runs per variant, one downstream review per arm, no statistical significance claim.',
                  'ABBA order partly balances order; no cache flush or independent cold-start repeats.',
                  'Kind labels and endpoint repetition make existing graph semantics explicit; no source/evaluator answers added.',
                  'Frozen review runner has at most two follow-ups and no cross-batch memory. Raw follow-up needs are audited separately.',
                  'No code patches, privacy compliance verdict, production deployment, or real personal data.',
                  'Previous Ministral-only vision/full-code results are historical references, not a controlled Qwen model comparison.']})
    print(json.dumps({'prepared':str(target),'visionOrder':VISION_ORDER}))


def choose_first(contexts,name,context,sequence):
    """Do not replace a valid first result based on later evaluator scores."""
    if name not in contexts:
        contexts[name]={'sequence':sequence,'context':context}


def response_audit(result,arm,raw_dir,manifest_paths):
    needs=[]
    for call in result['calls']:
        if not call['followup']:
            continue
        raw=json.loads((raw_dir/f'{arm}-{call["batch"]}.json').read_text())
        try:
            data=json.loads(raw['message']['content'])
        except (ValueError,KeyError):
            continue
        if isinstance(data,dict) and isinstance(data.get('needs'),list):
            for need in data['needs']:
                if isinstance(need,str):
                    needs.append({'batch':call['batch'],'path':need,'inManifest':need in manifest_paths,
                                  'doneReason':raw.get('done_reason')})
    return {'followupResponseNeeds':needs,
            'invalidSupportEvidence':sum(not r['evidenceValid'] for f in result['findings'] for r in f['support']),
            'meaning':'Source-line matching and outstanding model requests, not a runtime security proof.'}


def run():
    protocol_path=PUBLIC/'protocol.json'
    protocol=json.loads(protocol_path.read_text())
    for path,digest in protocol['hashes'].items():
        if base.digest((ROOT/path).read_bytes())!=digest:
            raise ValueError('FROZEN_INPUT_CHANGED: '+path)
    if protocol['visionModel']!=VISION_MODEL or protocol['reviewModel']!=base.DEFAULT_MODEL:
        raise ValueError('MODEL_PROTOCOL_MISMATCH')
    logpath=PUBLIC/'measurements.jsonl'
    if logpath.exists():
        raise ValueError('MEASUREMENT_EXISTS')
    raw_dir=PUBLIC/'raw'
    raw_dir.mkdir(parents=True,exist_ok=True)
    if list(raw_dir.iterdir()):
        raise ValueError('RAW_DIRECTORY_NOT_EMPTY')
    def log(row):
        with logpath.open('a') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n')
        brief={k:v for k,v in row.items() if k in ('event','variant','sequence','arm','complete','quality','error')}
        if 'metrics' in row:
            brief['metrics']={k:row['metrics'].get(k) for k in ('prompt_eval_count','eval_count','wallDurationMs','doneReason')}
        print(json.dumps(brief,ensure_ascii=False),flush=True)
    manifest,sources=base.read_sources()
    graph=json.loads((base.DATA/'graph.json').read_text())
    truth=json.loads((base.DATA/'ground_truth.json').read_text())
    contexts={}
    with httpx.Client(base_url='http://127.0.0.1:11434',timeout=900,trust_env=False) as api:
        tags=api.get('/api/tags'); tags.raise_for_status()
        model_records={name:next(m for m in tags.json()['models'] if m['name']==name) for name in (VISION_MODEL,base.DEFAULT_MODEL)}
        show=api.post('/api/show',json={'model':VISION_MODEL}); show.raise_for_status()
        if 'vision' not in show.json().get('capabilities',[]):
            raise ValueError('VISION_CAPABILITY_MISSING')
        log({'event':'metadata','timestamp':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),
             'models':model_records,'ollamaVersion':api.get('/api/version').json(),
             'protocolSha256':base.digest(protocol_path.read_bytes()),'sourceSha256':manifest['sourceSha256']})
        _,warm_metrics=base.invoke(api,{'model':VISION_MODEL,'stream':False,'think':False,
            'messages':[{'role':'user','content':'Reply OK.'}],
            'options':{**VISION_OPTIONS,'num_predict':4},'keep_alive':'10m'},raw_dir/'warmup-vision.json')
        log({'event':'warmup','model':VISION_MODEL,'excluded':True,'metrics':warm_metrics})
        for sequence,variant in enumerate(VISION_ORDER,1):
            started=time.perf_counter()
            try:
                raw,metrics=base.invoke(api,{'model':VISION_MODEL,'stream':False,'think':False,'format':_schema(),
                    'options':VISION_OPTIONS,'keep_alive':'10m','messages':[
                    {'role':'system','content':SYSTEM_PROMPT},
                    {'role':'user','content':USER_PROMPT,'images':[base64.b64encode(IMAGES[variant].read_bytes()).decode()]}]},
                    raw_dir/f'vision-{sequence}-{variant}.json')
                log({'event':'vision_call','variant':variant,'sequence':sequence,'metrics':metrics})
                if raw.get('done_reason')!='stop':
                    raise ValueError('VISION_OUTPUT_INCOMPLETE')
                context=validate_context(json.loads(raw['message']['content']))
                base.write(PUBLIC/f'context-{sequence}-{variant}.json',context)
                choose_first(contexts,variant,context,sequence)
                log({'event':'vision_result','variant':variant,'sequence':sequence,'complete':True,
                     'quality':base.graph_score(context,graph),'phaseWallMs':(time.perf_counter()-started)*1000})
            except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
                log({'event':'vision_result','variant':variant,'sequence':sequence,'complete':False,
                     'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,
                     'phaseWallMs':(time.perf_counter()-started)*1000})
        # Release the model used by this experiment before loading the reviewer.
        unload=api.post('/api/generate',json={'model':VISION_MODEL,'keep_alive':0}); unload.raise_for_status()
        log({'event':'vision_model_unloaded','model':VISION_MODEL})
        _,warm_metrics=base.invoke(api,{'model':base.DEFAULT_MODEL,'stream':False,'think':False,
            'messages':[{'role':'user','content':'Reply OK.'}],
            'options':{**base.OPTIONS,'num_predict':4},'keep_alive':'10m'},raw_dir/'warmup-review.json')
        log({'event':'warmup','model':base.DEFAULT_MODEL,'excluded':True,'metrics':warm_metrics})
        for arm in REVIEW_ORDER:
            started=time.perf_counter()
            chosen=contexts.get(arm)
            context=None
            if chosen:
                context=json.loads((PUBLIC/f'context-{chosen["sequence"]}-{arm}.json').read_text())
            plan=plan_routed_context(sources,protocol['anchor'],architecture=context,
                                    use_vision_context=context is not None,**protocol['budget'])
            base.write(PUBLIC/f'{arm}-plan.json',plan)
            if plan['status']!='READY':
                log({'event':'trial','arm':arm,'complete':False,'error':plan['status'],'plan':plan})
                continue
            selected=plan['selectedPaths']
            review_context={key:context[key] for key in CONTEXT_KEYS} if plan['decision']['useVisionContext'] else None
            planning_ms=(time.perf_counter()-started)*1000
            result=base.review(api,sources,selected,review_context,raw_dir,arm,log)
            log({'event':'trial','arm':arm,**result,'plan':plan,'initialPaths':selected,
                 'chosenVisionSequence':None if chosen is None else chosen['sequence'],
                 'visionAvailable':context is not None,'planningWallMs':planning_ms,
                 'endToEndWallMs':(time.perf_counter()-started)*1000,
                 'quality':base.score(result['findings'],truth,result['effectivePaths']),
                 'responseAudit':response_audit(result,arm,raw_dir,set(sources))})
        raw_hashes={p.name:base.digest(p.read_bytes()) for p in sorted(raw_dir.glob('*.json'))}
        log({'event':'finished','rawHashes':raw_hashes})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    args=parser.parse_args()
    prepare() if args.prepare else run()


if __name__=='__main__':
    main()
