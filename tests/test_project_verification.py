import json
from pathlib import Path
import subprocess
import pytest

from coding_agent.project_verification import (ROOT, ADAPTER, MODEL, PACK, fingerprint, validate_profile,
    report_gate, validate_candidate)
from coding_agent.project_engine import generate, apply_edits, compact_context
from coding_agent.repository import Rejected, digest

BEFORE = '''import logging
log = logging.getLogger('contact.audit')
def add_contact(records, email, phone):
    if not email or not phone:
        raise ValueError('Required')
    records.append({'email': email, 'phone': phone})
    log.info('CONTACT_STORED email=%s phone=%s', email, phone)
    return len(records)
'''
AFTER = BEFORE.replace("log.info('CONTACT_STORED email=%s phone=%s', email, phone)", "log.info('CONTACT_STORED')")
PACK_IDS = sorted('tests/test_csi_privacy_pack.py::'+name for name in (
    'test_no_sensitive_logs','test_useful_log_preserved','test_behavior_preserved','test_invalid_input_rejected'))


def profile():
    return {'schemaVersion':1,'profileId':'contacts-privacy-v1','repository':'fixtures/contacts',
            'runtime':{'adapter':ADAPTER,'imageId':'sha256:'+'a'*64,'workingDirectory':'service'},
            'snapshotPaths':['service/contacts','service/tests'],'editablePaths':['service/contacts/service.py'],
            'contextPaths':['service/contacts/service.py'],'testPaths':['tests'],
            'pack':{'id':PACK,'sha256':digest((ROOT/'verification/privacy_pack.py').read_text(encoding='utf-8'))},
            'driver':{'path':'project_profiles/contact_service/driver.py',
                      'sha256':digest((ROOT/'project_profiles/contact_service/driver.py').read_text(encoding='utf-8'))},
            'contracts':['Retain internal contact records, validation and CONTACT_STORED; omit sensitive log values.'],
            'ruleIds':['SEC-05'],'reproductionTests':['tests/test_csi_privacy_pack.py::test_no_sensitive_logs'],
            'relatedFailures':[],'allowedSkips':[],'model':MODEL,'generationTimeoutSeconds':300,'inventory':PACK_IDS}


def report(p, baseline=False):
    checks=[{'id':i,'status':'FAIL' if baseline and i in p['reproductionTests'] else 'PASS'} for i in p['inventory']]
    return {'inventory':p['inventory'], 'inventoryDigest':fingerprint(p['inventory']), 'checks':checks,
            'exitCode':int(baseline),'isolation':'DOCKER_NETWORK_NONE','imageId':p['runtime']['imageId'],
            'passed':sum(c['status']=='PASS' for c in checks),'failed':int(baseline),'skipped':0,
            'failedTests':[c['id'] for c in checks if c['status']=='FAIL']}


@pytest.fixture
def repository(tmp_path):
    repo=tmp_path/'repo'
    (repo/'service/contacts').mkdir(parents=True)
    (repo/'service/tests').mkdir()
    (repo/'service/contacts/__init__.py').write_text('')
    (repo/'service/contacts/service.py').write_text(BEFORE)
    (repo/'service/tests/test_contacts.py').write_text('from contacts.service import add_contact\ndef test_invalid():\n    import pytest\n    with pytest.raises(ValueError): add_contact([], "", "phone")\n')
    for args in [('init',),('add','.'),('-c','user.name=CSI Fixture','-c','user.email=fixture@example.com','commit','-m','fixture')]:
        subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
    return repo


def context(repo, p):
    sha=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
    plan={'config':p,'profileVersion':1,'commitSha':sha,'policy':{},'findingIds':['finding']}
    return {'executionPlan':plan,'planDigest':fingerprint(plan),'repository':p['repository'],'commitSha':sha,'policy':{},
            'findings':[{'id':'finding','filePath':p['editablePaths'][0],'ruleId':'SEC-05','title':'Sensitive log values',
                         'analysis':{'references':[{'chunkId':'ref','content':'Do not log contact values','sectionId':'SEC-05'}]}}]}


def coder(source):
    return lambda payload:{'done_reason':'stop','message':{'content':json.dumps({'edits':[{'path':'service/contacts/service.py','old':BEFORE,'new':source}],
        'reason':'Remove sensitive values while preserving the event and internal storage.','evidence_ids':['finding','ref']})}}


def test_exact_edit_preimages_and_overlap():
    assert apply_edits(BEFORE,[{'path':'source.py','old':"log.info('CONTACT_STORED email=%s phone=%s', email, phone)",'new':"log.info('CONTACT_STORED')"}],'source.py')==AFTER
    for edits in ([{'path':'wrong.py','old':BEFORE,'new':AFTER}],
                  [{'path':'source.py','old':'missing','new':'x'}],
                  [{'path':'source.py','old':BEFORE,'new':AFTER},{'path':'source.py','old':'import logging','new':''}]):
        with pytest.raises(Rejected):apply_edits(BEFORE,edits,'source.py')


def test_compact_context_keeps_callers_and_referenced_types():
    sources={'core.py':'def store(value):\n    return value\n','api.py':'class Input:\n    pass\ndef endpoint(value: Input):\n    return store(value)\ndef unrelated():\n    return 5\n'}
    compact=compact_context(sources,'core.py')
    assert compact['core.py']==sources['core.py']
    text=json.dumps(compact)
    assert 'class Input' in text and 'def endpoint' in text and 'def unrelated' not in text


@pytest.mark.parametrize('mutation', ['duplicate','missing','skip','error','timeout','image','inventoryDigest'])
def test_gate_rejects_incomplete_or_wrong_execution(mutation):
    p=profile(); r=report(p)
    if mutation=='duplicate':r['checks'][-1]=r['checks'][0]
    elif mutation=='missing':r['checks'].pop()
    elif mutation=='skip':r['checks'][0]['status']='SKIP'
    elif mutation=='error':r['checks'][0]['status']='ERROR'
    elif mutation=='timeout':r['exitCode']=124
    elif mutation=='image':r['imageId']='sha256:'+'b'*64
    else:r['inventoryDigest']='b'*64
    with pytest.raises(Rejected):report_gate(p,r)


def test_baseline_requires_selected_reproduction_and_blocks_other_failures():
    p=profile()
    assert report_gate(p,report(p,True),baseline=True)
    with pytest.raises(Rejected,match='NOT_REPRODUCED'):report_gate(p,report(p),baseline=True)
    r=report(p,True);r['checks'][0]['status']='FAIL'
    with pytest.raises(Rejected,match='REGRESSION'):report_gate(p,r,baseline=True)


def test_timeout_and_collection_errors_are_not_security_failures():
    with pytest.raises(Rejected,match='VERIFICATION_TIMEOUT'):report_gate(profile(),{'error':'TIMEOUT'})
    with pytest.raises(Rejected,match='HARNESS_ERROR'):report_gate(profile(),{'collectionErrors':['tests/broken.py']})


def test_behavior_can_be_fixed_without_freezing_function_ast():
    validate_candidate(BEFORE,AFTER)
    with pytest.raises(Rejected,match='LOGGING_CONFIG'):validate_candidate(BEFORE,AFTER+'\nlog.disabled = True\n')
    with pytest.raises(Rejected,match='CALL_CONTRACT'):validate_candidate(BEFORE,AFTER.replace('records, email, phone','records, email'))
    with pytest.raises(Rejected,match='IMPORT'):validate_candidate(BEFORE,AFTER+'\nimport subprocess\n')


def test_plan_rejects_path_escape_and_driver_tampering():
    p=profile();assert validate_profile(p)
    p['editablePaths']=['../secret.py']
    with pytest.raises(Rejected):validate_profile(p)
    p=profile();p['driver']['sha256']='b'*64
    with pytest.raises(Rejected,match='DRIVER'):validate_profile(p)


def test_generic_engine_independent_layout_passes(repository):
    p=profile(); calls=[]
    def verifier(tree,p):
        calls.append((tree/p['editablePaths'][0]).read_text())
        return report(p,len(calls)==1)
    value=generate(repository,context(repository,p),chat=coder(AFTER),verifier=verifier)
    assert value['status']=='READY' and len(value['attempts'])==1
    assert calls==[BEFORE,AFTER] and value['verification']['candidateSha256']==digest(AFTER)
    assert (repository/p['editablePaths'][0]).read_text()==BEFORE


@pytest.mark.parametrize('succeeds',[True,False])
def test_saved_unified_instruction_is_reused_without_second_vlm(repository,monkeypatch,succeeds):
    p=profile();c=context(repository,p);calls=[];requests=[]
    saved={'mode':'unified-vlm-review-v1','commitSha':c['commitSha'],'imageSha256':'b'*64,'model':'qwen3-vl:8b',
           'instructions':[{'findingId':'finding','text':'Remove sensitive log values, preserve the contact event and stored records.','referenceIds':['ref']}]}
    c['executionPlan']['unifiedReview']=saved;c['planDigest']=fingerprint(c['executionPlan'])
    monkeypatch.setattr('coding_agent.project_engine.orchestrate',lambda *a,**kw:pytest.fail('Unexpected second VLM analysis'))
    def verifier(tree,profile):
        calls.append(True);return report(profile,len(calls)==1 or not succeeds)
    def chat(payload):requests.append(payload);return coder(AFTER)(payload)
    value=generate(repository,c,chat=chat,verifier=verifier)
    assert value['handoff']['reusedScanAnalysis'] and value['handoff']['reviewDigest']==fingerprint(saved)
    assert saved['instructions'][0]['text'] in json.dumps(requests,ensure_ascii=False)
    assert len(requests)==(1 if succeeds else 2)
    assert value['status']==('READY' if succeeds else 'BLOCKED')
    if not succeeds:assert not value['files']


def test_crlf_git_blobs_keep_byte_accurate_manifest(repository):
    p=profile();target=p['editablePaths'][0];crlf=BEFORE.replace('\n','\r\n')
    (repository/target).write_bytes(crlf.encode())
    subprocess.run(['git','-C',str(repository),'config','core.autocrlf','false'],check=True)
    subprocess.run(['git','-C',str(repository),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repository),'-c','user.name=CSI Fixture','-c','user.email=fixture@example.com','commit','-m','CRLF'],check=True,capture_output=True)
    calls=[]
    def verifier(tree,p):
        calls.append(True);return report(p,len(calls)==1)
    def model(payload):
        return {'done_reason':'stop','message':{'content':json.dumps({'edits':[{'path':target,
            'old':"log.info('CONTACT_STORED email=%s phone=%s', email, phone)",'new':"log.info('CONTACT_STORED')"}],
            'reason':'Preserve event only.','evidence_ids':['finding','ref']})}}
    result=generate(repository,context(repository,p),chat=model,verifier=verifier)
    assert result['status']=='READY'
    assert result['files'][0]['beforeSha256']==result['sourceHashes'][target]==digest(crlf)
    assert '\r\n' in result['files'][0]['content']


def test_two_partial_candidates_never_publish(repository):
    p=profile()
    value=generate(repository,context(repository,p),chat=coder(AFTER),verifier=lambda tree,p:report(p,True))
    assert value['status']=='BLOCKED' and value['files']==[] and len(value['attempts'])==2


def test_stale_plan_rejected_before_model(repository):
    job=context(repository,profile());job['executionPlan']['profileVersion']=2
    with pytest.raises(Rejected,match='PLAN_DIGEST'):generate(repository,job,chat=lambda _:pytest.fail('model called'))


def test_vlm_delegates_and_verifies_an_independent_project(repository):
    from test_coding_handoff import ARCH
    from test_vlm_orchestrator import scripted
    p=profile();job=context(repository,p)
    job.update(architectureId=ARCH['id'],architecture={**ARCH,'sourceCommitSha':job['commitSha']})
    calls=[];verified=[]
    instruction='For finding and ref, remove sensitive contact values from log output. Preserve the operational event, internal records and input validation.'
    sequence=[('read_code',{'path':p['editablePaths'][0],'start_line':1,'end_line':100}),
              ('get_policy_evidence',{'reference_ids':['ref']}),
              ('delegate_coding',{'instruction':instruction,'evidence_ids':['finding','ref']}),
              ('run_verification',{}),
              ('finish_review',{'summary':'The current candidate passed the fixed project tests and is ready for human review.','evidence_ids':['finding','ref']})]
    def verifier(tree,p):
        verified.append(True);return report(p,len(verified)==1)
    result=generate(repository,job,chat=coder(AFTER),verifier=verifier,vlm_chat=scripted(sequence,calls))
    assert result['status']=='READY' and result['handoff']['status']=='READY'
    assert result['handoff']['readPaths']==p['editablePaths'] and len(calls)==5


@pytest.mark.skipif(__import__('os').environ.get('CSI_PROJECT_DOCKER_TEST')!='1',reason='Explicit local Docker integration')
def test_real_docker_second_project(repository,tmp_path):
    from coding_agent.project_setup import prepare
    draft=profile();draft.pop('inventory')
    prepared=prepare(repository,context(repository,profile())['commitSha'],draft)
    p=prepared['config']
    result=generate(repository,context(repository,p),chat=coder(AFTER))
    (tmp_path/'result.json').write_text(json.dumps(result))
    assert len(p['inventory'])==5
    assert result['status']=='READY' and result['verification']['passed']==5
    # Removing stored PII defeats the business contract, even if logs are now clean.
    deleted=AFTER.replace("records.append({'email': email, 'phone': phone})", "records.append({})")
    failed=generate(repository,context(repository,p),chat=coder(deleted))
    assert failed['status']=='BLOCKED' and failed['files']==[]
