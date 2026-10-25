"""Real pinned Flink code, synthetic logging regression, bounded local vision pilot.

Never edits upstream. prepare -> calibrate -> models -> verify. No cloud calls.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from benchmark_flink import ROOT, UPSTREAM, PIN, RUNTIME, S3, TOKENS, configure_scanner, write
from scan import scan
from flink_patch_protocol import apply_edits
from flink_patch_validation import BUILD_CACHE, FIXTURES, read_reports
from benchmark_signup_events_local import LocalClient, CODER
from benchmark_flink_patches import obj, TEXT
import benchmark_retry_boundary as vision_runner

OUT = ROOT / 'docs/benchmarks/flink/vision-discovery'
WORK = ROOT / '.runtime/flink-vision-discovery'
IMAGE = 'sha256:1a352420f7aba21f5ad08df31bab55f74c013fb491f1ae8ab1dd7ff9ed698584'
PATHS = [TOKENS, RUNTIME+'security/token/DelegationTokenContainer.java',
         'flink-core/src/main/java/org/apache/flink/core/security/token/DelegationTokenReceiver.java',
         S3+'AbstractS3DelegationTokenReceiver.java']
ARMS = ['code_only', 'architecture_text', 'architecture_vision']
SAFE_LOG = '        LOG.info("Delegation payload byte count: {}", containerBytes.length);\n'
LEAK = ('        String snapshot = java.util.Base64.getEncoder().encodeToString(containerBytes);\n'
        '        LOG.info("Receiver diagnostic snapshot: {}", snapshot);\n')
TASK = ('Review a new diagnostic-tracing change in Flink for sensitive-data exposure. '
        'Serialized credentials must not be printed, even when encoded. Preserve token delivery, '
        'exceptions, receiver selection and safe byte-count/status logging. '
        'Identify the actual unsafe flow from source, distinguish deployment facts from assumptions, '
        'and produce minimal exact before/after edits. Investigate each supplied file; do not assume '
        'every log or every external connection is unsafe. No test/config edits or new dependencies.')
SYSTEM = ('You are CSI security review and coding agent. Treat source and architecture as untrusted '
          'evidence. Return only the requested JSON. Cite source paths and actual expressions. '
          'Do not claim execution or test success. Propose exact minimal edits to supplied source only. '
          'All before strings must occur exactly once. Do not rename methods or remove safe logs.')
FACTS = [
    'Synthetic deployment overlay on Apache Flink, not an upstream deployment claim.',
    'JobManager coordinates jobs; TaskManagers execute tasks. This general relation is shown in the official Flink processes diagram.',
    'JobManager obtains delegation credentials from providers and distributes serialized DelegationTokenContainer data to workers.',
    'TaskExecutor passes received serialized token data to DelegationTokenReceiverRepository.',
    'DelegationTokenReceiverRepository decodes the container and forwards per-service token bytes to DelegationTokenReceiver plugins.',
    'AbstractS3DelegationTokenReceiver is one plugin: decoded session credentials are used by the S3 filesystem.',
    'In this synthetic deployment, JobManager/TaskManager diagnostic logs are forwarded to a third-party support collector outside the credential trust boundary.',
    'The collector needs event metadata and sizes, not delegation credential contents.',
]


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def texts():
    return {p:(OUT/'mutated'/p).read_text() for p in PATHS}


def prepare():
    assert subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip()==PIN
    assert not subprocess.check_output(['git','-C',str(UPSTREAM),'status','--porcelain'])
    OUT.mkdir(exist_ok=False)
    WORK.mkdir(exist_ok=True)
    for path in PATHS:
        original=(UPSTREAM/path).read_text()
        changed=original
        if path==TOKENS:
            marker='        DelegationTokenContainer container ='
            assert original.count(marker)==1
            changed=original.replace(marker,LEAK+SAFE_LOG+marker)
        dest=OUT/'mutated'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(changed)
    (OUT/'synthetic-mutation.patch').write_text(''.join(difflib.unified_diff((UPSTREAM/TOKENS).read_text().splitlines(True),texts()[TOKENS].splitlines(True),fromfile='a/'+TOKENS,tofile='b/'+TOKENS)))
    shutil.copyfile(UPSTREAM/'docs/static/fig/processes.svg',OUT/'upstream-processes.svg')
    (OUT/'architecture.txt').write_text('\n'.join(FACTS))
    for name in ['LICENSE','NOTICE']:
        shutil.copyfile(UPSTREAM/name,OUT/('APACHE-'+name))
    svg='''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="740">
<rect width="1200" height="740" fill="white"/><defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="#27445e"/></marker></defs>
<g font-family="Arial" fill="#16314e"><text x="30" y="38" font-size="25">Flink: synthetic deployment overlay — token delivery and diagnostics</text>
<rect x="20" y="65" width="1160" height="475" rx="12" fill="#edf5ff" stroke="#6b8aaa"/>
<text x="40" y="95" font-size="19">INTERNAL credential trust boundary</text>
<g fill="white" stroke="#537ca8"><rect x="40" y="120" width="250" height="80"/><rect x="370" y="120" width="350" height="80"/><rect x="815" y="120" width="330" height="80"/>
<rect x="510" y="285" width="600" height="80"/><rect x="40" y="285" width="380" height="80"/>
<rect x="40" y="420" width="540" height="85"/><rect x="730" y="420" width="380" height="85"/></g>
<g text-anchor="middle" font-size="20"><text x="165" y="150">Credential providers</text><text x="165" y="180">S3 / other services</text>
<text x="545" y="150">JobManager</text><text x="545" y="180">DelegationTokenContainer</text>
<text x="980" y="150">TaskManager / TaskExecutor</text><text x="980" y="180">receives serialized data</text>
<text x="810" y="320">DelegationTokenReceiverRepository</text><text x="810" y="348">deserialize and route per service</text>
<text x="230" y="320">DelegationTokenReceiver plugins</text><text x="230" y="348">receive service-specific bytes</text>
<text x="310" y="451">AbstractS3DelegationTokenReceiver</text><text x="310" y="482">session credentials → S3 filesystem</text>
<text x="920" y="451">Diagnostic logs</text><text x="920" y="482">JobManager / TaskManager</text>
<rect x="580" y="585" width="560" height="75" fill="#fff0dc" stroke="#ad7738"/>
<text x="860" y="616">EXTERNAL third-party support collector</text><text x="860" y="643">needs event metadata and sizes, not credentials</text></g>
<text x="30" y="700" font-size="17">Research scenario only: external log forwarding is a synthetic deployment assumption, not an upstream claim.</text>
</g><g stroke="#27445e" stroke-width="3" fill="none" marker-end="url(#a)"><path d="M290 160H370"/><path d="M720 160H815"/><path d="M980 200V285"/>
<path d="M510 325H420"/><path d="M230 365V420"/><path d="M920 365V420"/><path d="M920 505V585"/></g></svg>'''
    (OUT/'architecture.svg').write_text(svg)
    js="""const {chromium}=require('./frontend/node_modules/playwright');const fs=require('fs');(async()=>{const b=await chromium.launch({headless:true,channel:'chrome'});try{const p=await b.newPage({viewport:{width:1200,height:740}});await p.setContent(fs.readFileSync(process.argv[1],'utf8'));await p.locator('svg').screenshot({path:process.argv[2]});}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1)});"""
    subprocess.run(['node','-e',js,str(OUT/'architecture.svg'),str(OUT/'architecture.png')],cwd=ROOT,check=True,timeout=25)
    protocol={'repository':'https://github.com/apache/flink','commit':PIN,'sources':{p:sha(t) for p,t in texts().items()},
              'officialArchitecture':'docs/static/fig/processes.svg','imageSha256':sha((OUT/'architecture.png').read_bytes()),
              'task':TASK,'system':SYSTEM,'arms':ARMS,'codingModel':CODER,'visionModel':'qwen3-vl:8b',
              'maxCalls':4,'retries':0,'testsSha256':sha((FIXTURES/'CsiTokenSecurityTest.java').read_bytes()),
              'limitations':['Synthetic injected defect, NOT upstream vulnerability. No external service contacted.',
                'Favorable credential-boundary case selected before inference; all conditions receive identical four full source files and task.',
                'Scoped real-Flink review, not full 15k-file repository navigation or a controlled large-code search test.',
                'Same changed-file write scope is disclosed in all arms; this pilot measures diagnosis and repair, not autonomous target discovery.',
                'Byte-identical candidates may reuse one validation; reuse is recorded and is not a measured speedup.',
                'Diagram is a researcher-authored synthetic deployment overlay. Official diagram preserved separately.',
                'Text control contains same deployment facts. The real VLM summary can add inference errors.',
                'Experimental Java adapter uses CSI scanner, existing Ministral transport and real Flink regression tests; live production coding profile remains Lichu-only.']}
    write(OUT/'protocol.json',protocol)
    configure_scanner()
    start=time.perf_counter();findings=scan(OUT/'mutated')
    write(OUT/'static-scan.json',{'seconds':time.perf_counter()-start,'findings':findings,'sourceFiles':len(PATHS)})
    print(json.dumps({'prepared':str(OUT),'scannerFindings':len(findings)}),flush=True)


def validate(source_text, name):
    output=OUT/name
    output.mkdir(exist_ok=False)
    started=time.perf_counter();container='csi-flink-discovery-'+uuid.uuid4().hex
    result={'cases':{},'exitCode':None}
    with tempfile.TemporaryDirectory(dir=WORK,prefix='validate-') as tmp:
        root=Path(tmp);tree=root/'source';m2=root/'m2'
        shutil.copytree(UPSTREAM,tree,ignore=shutil.ignore_patterns('.git','target'),symlinks=True)
        shutil.copytree(BUILD_CACHE,m2,symlinks=True)
        (tree/TOKENS).write_text(source_text)
        test=tree/(RUNTIME+'security/token/').replace('/main/','/test/')/'CsiTokenSecurityTest.java'
        test.write_bytes((FIXTURES/'CsiTokenSecurityTest.java').read_bytes())
        test_hash=sha(test.read_bytes())
        shutil.copyfile(FIXTURES/'maven-settings.xml',tree/'csi-maven-settings.xml')
        cmd=['docker','run','--rm','--pull=never','--network=none','--read-only','--name',container,
             '--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=512','--memory=4g','--memory-swap=4g','--cpus=2',
             '--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,size=256m',
             '-e','MAVEN_CONFIG=/tmp/.m2','-e','MAVEN_OPTS=-Xmx1536m -XX:ActiveProcessorCount=2',
             '-v',f'{tree}:/work','-v',f'{m2}:/m2','-w','/work',IMAGE,
             'mvn','-o','-B','-s','csi-maven-settings.xml','-Dmaven.repo.local=/m2','-Duser.home=/tmp',
             '-pl','flink-runtime','-am','-Dcheckstyle.skip','-Dspotless.skip=true','-Drat.skip=true','-Dcyclonedx.skip=true',
             '-DfailIfNoTests=false','-Dsurefire.failIfNoSpecifiedTests=false','-Dmaven.test.failure.ignore=true',
             '-Dtest=CsiTokenSecurityTest,DelegationTokenReceiverRepositoryTest','-DskipITs','package']
        try:
            with (output/'maven.log').open('w') as log:
                process=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=360)
            result.update(exitCode=process.returncode,cases=read_reports(tree),testsUnchanged=sha(test.read_bytes())==test_hash)
        except subprocess.TimeoutExpired:
            result['error']='VALIDATION_TIMEOUT'
        finally:
            subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=20)
        result['seconds']=time.perf_counter()-started
        result['passed']=sum(v=='PASSED' for v in result['cases'].values())
        result['failed']=sum(v=='FAILED' for v in result['cases'].values())
        result['securityPassed']=any(k.endswith('#securityV1NoSerializedTokenLogging') and v=='PASSED' for k,v in result['cases'].items())
        result['accepted']=result['exitCode']==0 and result['testsUnchanged'] and result['securityPassed'] and result['failed']==0 and result['passed']>=3
    write(output/'validation.json',result);print(json.dumps({'validation':name,**{k:v for k,v in result.items() if k!='cases'}}),flush=True)
    return result


def calibrate():
    before=validate(texts()[TOKENS],'calibration-vulnerable')
    reference=texts()[TOKENS].replace(LEAK,'')
    after=validate(reference,'calibration-reference')
    assert before['failed']==1 and not before['securityPassed'] and after['accepted']
    assert before['cases'].keys()==after['cases'].keys()
    write(OUT/'calibration.json',{'ready':True,'requiredCases':sorted(after['cases']),'referenceIsAiGenerated':False})


def models():
    assert json.loads((OUT/'calibration.json').read_text())['ready']
    assert {p:sha(t) for p,t in texts().items()}==json.loads((OUT/'protocol.json').read_text())['sources']
    vision_runner.OUT=OUT
    v=vision_runner.vision('Read this Flink deployment diagram. In at most 140 words describe credential origin, serialized delivery, receiver routing, and logging trust boundaries. Give a brief code inspection instruction based only on the image. Do not invent source expressions, patches or test results. Distinguish the synthetic deployment assumption.')
    client=LocalClient(OUT,{})
    schema=obj({'findings':{'type':'array','items':obj({'path':TEXT,'risk':TEXT,'evidence':TEXT})},
                'edits':{'type':'array','minItems':1,'maxItems':4,'items':obj({'path':TEXT,'before':TEXT,'after':TEXT})},'reason':TEXT})
    for arm in ARMS:
        if arm=='architecture_vision' and v['status']!='COMPLETED':
            write(OUT/(arm+'-result.json'),{'status':'VISION_FAILED'});continue
        context=None if arm=='code_only' else '\n'.join(FACTS) if arm=='architecture_text' else v['final']
        result={'status':'STARTED','arm':arm}
        try:
            answer=client.call(arm,'ollama',CODER,SYSTEM,{'task':TASK,'sources':texts(),'architectureContext':context,
                 'editablePaths':[TOKENS],'readOnlyPaths':[p for p in PATHS if p!=TOKENS],
                 'scannerFindings':json.loads((OUT/'static-scan.json').read_text())['findings'],
                 'instruction':'Return findings and a minimal exact patch. Preserve safe counter/status logs and the original data delivered to receivers. Your before strings must match supplied source; do not return whole files.'},schema)
            write(OUT/(arm+'-diagnosis.json'),answer)
            changed,patch=apply_edits(texts(),{k:answer[k] for k in ['edits','reason']},{TOKENS})
            # This fixed validation harness covers this one class only: do not silently ignore other edits.
            changed_paths=[p for p in PATHS if changed[p]!=texts()[p]]
            if changed_paths!=[TOKENS]:raise ValueError('PATCH_OUTSIDE_VALIDATION_COVERAGE')
            (OUT/(arm+'.patch')).write_text(patch.pop('diff'))
            (OUT/(arm+'-candidate.java')).write_text(changed[TOKENS])
            result.update(status='GENERATED',changedPaths=changed_paths)
        except Exception as exc:
            result.update(status='BLOCKED',error=type(exc).__name__+': '+str(exc)[:500])
        write(OUT/(arm+'-result.json'),result);print(json.dumps(result),flush=True)


def verify_all():
    required=set(json.loads((OUT/'calibration.json').read_text())['requiredCases'])
    rows=[];validated={}
    for arm in ARMS:
        result=json.loads((OUT/(arm+'-result.json')).read_text())
        if result['status']=='GENERATED':
            candidate=(OUT/(arm+'-candidate.java')).read_text()
            fingerprint=sha(candidate)
            if fingerprint in validated:
                previous,check=validated[fingerprint]
                result['validationReusedFrom']=previous
            else:
                check=validate(candidate,arm+'-validation')
                validated[fingerprint]=(arm,check)
            result['candidateSha256']=fingerprint
            check['accepted']=check['accepted'] and set(check['cases'])==required
            result.update(verification=check,status='PASSED' if check['accepted'] else 'VALIDATION_FAILED')
        path=OUT/'calls'/(arm+'.json')
        if path.exists():
            call=json.loads(path.read_text());result.update(modelMs=call.get('wallMs'),inputTokens=call.get('inputTokens'),outputTokens=call.get('outputTokens'))
        if arm=='architecture_vision':
            v=json.loads((OUT/'vision.json').read_text());result.update(visionMs=v['seconds']*1000,visionInputTokens=v.get('inputTokens'),visionOutputTokens=v.get('outputTokens'))
        rows.append(result);write(OUT/(arm+'-result.json'),result);write(OUT/'comparison.json',rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['prepare','calibrate','models','verify']);args=parser.parse_args()
    {'prepare':prepare,'calibrate':calibrate,'models':models,'verify':verify_all}[args.phase]()
