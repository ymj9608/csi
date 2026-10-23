"""Safety boundaries use isolated Git fixtures; no inference/network/container required."""
import copy
import json
import os
import subprocess
from pathlib import Path
import httpx
import pytest
from coding_agent import engine
from coding_agent.profile import CONTEXT_FILES, TARGET
from coding_agent.repository import Rejected, commit, digest, git, read, snapshot
from coding_agent.validation import validate_response
from coding_agent.verifier import passed
from coding_agent.verification.contract import SECURITY_TESTS, BASELINE_FAILURES
from coding_agent.reporting import build_review
from coding_agent.worker import apply_approved, backend_url

BEFORE=(Path(__file__).parent/'fixtures/coding/signup_before.py').read_text()
AFTER=BEFORE.replace("return 'before-fix'", "return 'after-fix'").replace(
    'hmac.compare_digest(hash_signup_password(password), hashed)',
    "hmac.compare_digest('csi-sha256$' + hashlib.sha256((password + 'lichu-csi-shared-salt').encode()).hexdigest(), hashed)")

@pytest.fixture
def repo(tmp_path):
    root=tmp_path/'repository';root.mkdir()
    git(root,'init','-q')
    for path in CONTEXT_FILES:
        dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(BEFORE if path==TARGET else '# caller contract fixture\n')
    (root/'.env').write_text('PRIVATE_FIXTURE=not-for-model\n')
    git(root,'add','.')
    git(root,'-c','user.name=CSI Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
    return root

def context(repo):
    return {'repository':'ymj9608/Lichu','commitSha':git(repo,'rev-parse','HEAD').decode().strip(),
            'policy':{'bcryptMinCost':12},'findings':[{'id':'finding-1','ruleId':'SEC-02','filePath':TARGET,
            'analysis':{'references':[{'chunkId':'ref-1','sectionId':'POL-04','documentType':'INTERNAL_POLICY','content':'cost 12'}]}}]}

def response(code=AFTER):
    return {'files':[{'path':TARGET,'content':code}],'reason':'보안 보완','evidence_ids':['finding-1','ref-1'],
            'limitations':['실습 검증'],'tests_to_run':['malicious arbitrary command must never execute']}

def report(ok):
    return {'exitCode':0 if ok else 1,'passed':40 if ok else 33,'failed':0 if ok else 7,'skipped':1,
            'securityPassed':13 if ok else 6,'failedTests':[] if ok else sorted(BASELINE_FAILURES),
            'isolation':'DOCKER_NETWORK_NONE','suiteVersion':2,'securityTotal':13,
            'securityChecks':[{'id':name,'status':'PASSED' if ok or name not in BASELINE_FAILURES else 'FAILED'}
                              for name in SECURITY_TESTS]}

def chat(value):
    return {'done_reason':'stop','message':{'content':json.dumps(value)}}

@pytest.mark.parametrize('change,error',[
    (lambda x:x['files'][0].update(path='../escape.py'),'EDIT_SCOPE'),
    (lambda x:x.update(evidence_ids=['finding-1','invented-law']),'EVIDENCE_IDS'),
    (lambda x:x['files'][0].update(content=AFTER.replace('def lab_version()', 'def removed_version()')),'FUNCTION_SET_CHANGED'),
    (lambda x:x['files'][0].update(content=AFTER.replace("payload.username.startswith('csi_')", 'True')),'SYNTHETIC_GUARD_CHANGED'),
    (lambda x:x['files'][0].update(content=AFTER+'\nimport os\n'),'IMPORT_NOT_ALLOWED'),
    (lambda x:x['files'][0].update(content=AFTER+'\nexec("x")\n'),'DYNAMIC_CODE_NOT_ALLOWED'),
    (lambda x:x['files'][0].update(content=AFTER+'\nlogging.disable(logging.CRITICAL)\n'),'LOGGING_CONFIG_NOT_ALLOWED'),
    (lambda x:x['files'][0].update(content=AFTER+'\nlog.disabled = True\n'),'LOGGING_CONFIG_NOT_ALLOWED'),
    (lambda x:x['files'][0].update(content=AFTER.replace('password: str, hashed: str','password: bytes, hashed: str')),'FUNCTION_SIGNATURE_CHANGED'),
])
def test_candidate_boundaries(change,error):
    value=response();change(value)
    with pytest.raises(Rejected,match=error):validate_response(value,BEFORE,{'finding-1'},{'ref-1'})

def test_snapshot_uses_commit_not_working_tree_and_excludes_env(repo,tmp_path):
    sha=context(repo)['commitSha'];(repo/TARGET).write_text('uncommitted private change')
    dest=tmp_path/'snapshot';dest.mkdir();snapshot(repo,sha,dest)
    assert (dest/TARGET).read_text()==BEFORE
    assert not (dest/'.env').exists() and not (dest/'.git').exists()
    with pytest.raises(Rejected):commit(repo,'HEAD')
    with pytest.raises(Rejected):read(repo,sha,'../.env')

def test_downloaded_patch_handles_missing_final_newline(repo):
    diff=engine.patch(BEFORE,AFTER.rstrip('\n'))
    result=subprocess.run(['git','-C',str(repo),'apply','--check','-'],input=diff,text=True,capture_output=True)
    assert result.returncode==0,result.stderr

def test_symlink_is_not_followed(repo,tmp_path):
    # Commit an actual Git symlink entry without requiring Windows symlink privileges.
    target=tmp_path/'link-target';target.write_text('/etc/passwd')
    blob=git(repo,'hash-object','-w',str(target)).decode().strip()
    git(repo,'update-index','--add','--cacheinfo',f'120000,{blob},backend/app/leak.py')
    git(repo,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','link')
    with pytest.raises(Rejected,match='REGULAR_SOURCE_FILE_REQUIRED'):
        snapshot(repo,context(repo)['commitSha'],tmp_path/'snapshot')

def test_ready_requires_fixed_verifier_and_preserves_repository(repo):
    checks=[];requests=[]
    def verify(tree):
        checks.append((tree/TARGET).read_text())
        assert not (tree/'.env').exists()
        return report(len(checks)>1)
    def model(payload):
        requests.append(copy.deepcopy(payload));return chat(response())
    result=engine.generate(repo,context(repo),verifier=verify,chat=model)
    assert result['status']=='READY' and len(checks)==2 and len(requests)==1
    assert result['files'][0]['afterSha256']==digest(AFTER)
    assert (repo/TARGET).read_text()==BEFORE and not git(repo,'status','--porcelain')
    assert 'PRIVATE_FIXTURE' not in json.dumps(requests)


def test_saved_architecture_reaches_prompt_result_and_progress_without_demo_sleep(repo,monkeypatch):
    from test_coding_architecture_context import fixture
    job=context(repo) | fixture()
    phases=[];requests=[];checks=[]
    def verify(_):checks.append(True);return report(len(checks)>1)
    def model(payload):requests.append(payload);return chat(response())
    monkeypatch.setattr(engine.time,'sleep',lambda _:pytest.fail('generation must not sleep for UI polling'))
    result=engine.generate(repo,job,verifier=verify,chat=model,progress=phases.append)
    assert result['status']=='READY'
    saved=result['architectureContext']
    assert saved['components'][0]['name']=='Signup demo'
    assert phases[0]['phase']=='ARCHITECTURE_CONTEXT' and phases[0]['note']==saved['note']
    assert json.loads(requests[0]['messages'][1]['content'])['architectureContext']==saved

def test_failed_verification_is_bounded_and_never_publishable(repo):
    result=engine.generate(repo,context(repo),verifier=lambda _:report(False),chat=lambda _:chat(response()))
    assert result['status']=='BLOCKED' and result['files']==[]
    assert len(result['attempts'])==2
    assert all(a['error']=='TESTS_FAILED' for a in result['attempts'])

def test_actual_caller_contract_reaches_coder_without_architecture(repo):
    caller = repo / 'backend/app/services/hub.py'
    caller.write_text('from app.core.csi_signup import record_signup as record\n'
                      'def signup(password, email):\n    record(password=password, email=email)\n')
    git(repo, 'add', str(caller))
    git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'caller')
    requests = []
    def model(payload):
        requests.append(payload)
        return chat(response())
    result = engine.generate(repo, context(repo), chat=model, verifier=lambda _: report(bool(requests)))
    assert result['status'] == 'READY'
    packet = json.loads(requests[0]['messages'][1]['content'])
    contract = next(c for c in packet['sourceCallContracts'] if c['function'] == 'record_signup')
    call = contract['calls'][0]
    assert call['path'] == 'backend/app/services/hub.py'
    assert call['arguments']['password']['expression'] == 'password'
    assert call['arguments']['password']['kind'] == 'unknown'

def test_invalid_first_response_repaired_once(repo):
    calls=[];checks=[]
    def model(payload):
        calls.append(copy.deepcopy(payload))
        bad=response();bad['evidence_ids']=['invented']
        return chat(bad if len(calls)==1 else response())
    def verify(_):
        checks.append(True);return report(len(checks)>1)
    result=engine.generate(repo,context(repo),verifier=verify,chat=model)
    assert result['status']=='READY' and result['attempts'][0]['error']=='EVIDENCE_IDS'
    assert len(checks)==2 and len(calls)==2

def test_no_inference_without_supported_baseline(repo):
    with pytest.raises(Rejected,match='BASELINE_NOT_SUPPORTED'):
        engine.generate(repo,context(repo),verifier=lambda _:report(True),chat=lambda _:pytest.fail('must not call model'))

@pytest.mark.parametrize('url',['https://example.com','http://192.168.1.10:11434','http://localhost:11434/api','http://user:secret@localhost'])
def test_inference_only_on_loopback(url):
    with pytest.raises(Rejected):engine.local_url(url)

def test_backend_requires_https_for_remote():
    assert backend_url('https://csi.example.test')=='https://csi.example.test'
    with pytest.raises(Rejected):backend_url('http://csi.example.test')

def test_approval_and_stale_guards_then_new_worktree(repo,tmp_path):
    sha=context(repo)['commitSha'];pid='11111111-1111-4111-8111-111111111111'
    job={'status':'READY','repository':'ymj9608/Lichu','commitSha':sha,'result':{'files':[{'path':TARGET,
         'content':AFTER,'beforeSha256':digest(BEFORE),'afterSha256':digest(AFTER)}]}}
    api=httpx.Client(base_url='http://localhost',transport=httpx.MockTransport(lambda _:httpx.Response(200,json=job)))
    dest=tmp_path/'review'
    with pytest.raises(Rejected,match='ADMIN_APPROVAL_REQUIRED'):apply_approved(api,repo,pid,dest)
    job['status']='APPROVED';(repo/'dirty.txt').write_text('pending')
    with pytest.raises(Rejected,match='STALE_OR_DIRTY_CHECKOUT'):apply_approved(api,repo,pid,dest)
    (repo/'dirty.txt').unlink()
    with pytest.raises(Rejected,match='REPOSITORY_MISMATCH'):apply_approved(api,repo,pid,dest,'other/repo')
    result=apply_approved(api,repo,pid,dest)
    assert result['status']=='PREPARED_FOR_REVIEW'
    assert (dest/TARGET).read_text()==AFTER and (repo/TARGET).read_text()==BEFORE
    assert git(dest,'rev-parse','HEAD').decode().strip()==sha
    assert git(repo,'rev-parse','HEAD').decode().strip()==sha

@pytest.mark.parametrize('field,value',[('securityPassed',12),('exitCode',1),('failed',1),('passed',39),
                                       ('suiteVersion',1),('securityTotal',12),('isolation','HOST')])
def test_partial_success_cannot_pass(field,value):
    check=report(True);check[field]=value;assert not passed(check)

def test_real_failure_import_feedback_does_not_remove_allowed_bcrypt(repo,tmp_path):
    bad=AFTER+'\nfrom app.core.security import verify_password\n'
    missing=AFTER.replace("return 'after-fix'","return bcrypt.hashpw(b'x', b'y')")
    with pytest.raises(Rejected,match='UNDEFINED_GLOBAL') as error:
        validate_response(response(missing),BEFORE,{'finding-1'},{'ref-1'})
    assert error.value.details=={'names':['bcrypt']}
    calls=[];checks=[];phases=[]
    def model(payload):
        calls.append(copy.deepcopy(payload))
        return chat(response(bad if len(calls)==1 else AFTER))
    def verify(_):checks.append(True);return report(len(checks)>1)
    result=engine.generate(repo,context(repo),verifier=verify,chat=model,progress=phases.append,diagnostics_dir=tmp_path/'private')
    assert result['status']=='READY'
    feedback=json.loads(calls[1]['messages'][-1]['content'])
    assert feedback['diagnostics']['module']=='app.core.security'
    assert 'import bcrypt' in feedback['repairGuidance'][0]
    assert [p['phase'] for p in phases]==['ARCHITECTURE_CONTEXT','BASELINE','GENERATING','VALIDATING','RETRYING','GENERATING','VALIDATING','VERIFYING']
    assert (tmp_path/'private/attempt-1.json').is_file()
    if os.name == 'posix':
        assert (tmp_path/'private/attempt-1.json').stat().st_mode & 0o777 == 0o600
    assert result['attempts'][0]['diagnostics']['module']=='app.core.security'
    assert 'modelResponse' not in json.dumps(result)

def test_legacy_verification_must_not_call_randomized_new_hash():
    bad=BEFORE.replace("return 'before-fix'","return 'after-fix'")
    with pytest.raises(Rejected,match='LEGACY_USES_NEW_HASH'):
        validate_response(response(bad),BEFORE,{'finding-1'},{'ref-1'})

def test_rag_selection_covers_password_logs_and_external_references():
    from coding_agent.profile import select_references
    refs={str(i):{'chunkId':str(i),'sectionId':'POL-04','content':'password policy'} for i in range(12)}
    refs['logs']={'chunkId':'logs','sectionId':'POL-05','content':'logging policy'}
    refs['external']={'chunkId':'external','sectionId':'REF-04','content':'password guidance'}
    chosen=select_references(refs)
    assert {r['sectionId'] for r in chosen}=={'POL-04','POL-05','REF-04'}
    assert chosen==select_references(dict(reversed(list(refs.items()))))


def test_test_counts_without_individual_proof_cannot_pass():
    check=report(True);check.pop('securityChecks')
    assert not passed(check)
    check=report(True);check['securityChecks'][-1]=check['securityChecks'][0]
    assert not passed(check)
    check=report(True);check['securityChecks'][0]['status']='SKIPPED'
    assert not passed(check)


def test_review_uses_actual_checks_and_names_unresolved_data_work():
    review=build_review(report(False),report(True))
    assert all(c['status']=='VERIFIED' for c in review['changes'])
    assert 'bcrypt' in review['changes'][0]['after']
    assert {r['id'] for r in review['remainingRisks']}=={'legacy-hashes','historical-logs','deployment'}
    assert '자동 전환되지 않는' in next(c for c in review['changes'] if c['id']=='legacy-login')['after']
    failed=build_review(report(False),report(False))
    assert next(c for c in failed['changes'] if c['id']=='sensitive-logs')['status']=='NOT_VERIFIED'
    missing=build_review({}, {'securityPassed':13})
    assert all(c['status']=='NOT_VERIFIED' for c in missing['changes'])
    assert all('자료가 없습니다' in c['before'] for c in missing['changes'])
    unchanged=build_review(report(True),report(True))
    assert '수정 전에도' in unchanged['changes'][1]['before']


def test_skipped_check_is_never_reported_as_verified():
    check=report(True)
    check['securityChecks'][0]['status']='SKIPPED';check['securityPassed']-=1
    review=build_review(report(False),check)
    assert next(c for c in review['changes'] if c['id']=='sensitive-logs')['status']=='NOT_VERIFIED'


def test_old_verifier_cannot_generate_new_review(repo):
    old=report(False);old.pop('suiteVersion')
    with pytest.raises(Rejected,match='BASELINE_NOT_SUPPORTED'):
        engine.generate(repo,context(repo),verifier=lambda _:old,chat=lambda _:pytest.fail('must not call model'))


def test_changes_link_their_actual_findings_and_retrieved_policy():
    findings=[{'id':'password','ruleId':'SEC-02'},{'id':'logs','ruleId':'SEC-05'}]
    refs=[{'chunkId':'pwd-policy','sectionId':'POL-04.1'},{'chunkId':'log-policy','sectionId':'POL-05'},
          {'chunkId':'salt-reference','sectionId':'REF-05'},{'chunkId':'log-reference','sectionId':'REF-06'}]
    review=build_review(report(False),report(True),findings,refs)
    assert next(c for c in review['changes'] if c['id']=='sensitive-logs')['evidenceIds']==['log-policy','log-reference','logs']
    assert next(c for c in review['changes'] if c['id']=='password-storage')['evidenceIds']==['password','pwd-policy','salt-reference']


def test_vlm_replans_across_repair_and_keeps_guardrails(repo):
    from test_coding_handoff import ARCH, TEXT
    from test_vlm_orchestrator import scripted, READ, EVIDENCE, DELEGATE, VERIFY, FINISH
    job=context(repo)
    job.update(architectureId=ARCH['id'],architecture={**ARCH,'sourceCommitSha':job['commitSha']})
    vlm=[];coder=[];checks=[];phases=[]
    planner=scripted([READ,EVIDENCE,DELEGATE,DELEGATE,VERIFY,FINISH],vlm)
    def model(payload):
        coder.append(copy.deepcopy(payload))
        return chat(response(AFTER+'\nimport os\n' if len(coder)==1 else AFTER))
    def verify(_):checks.append(True);return report(len(checks)>1)
    result=engine.generate(repo,job,verifier=verify,chat=model,vlm_chat=planner,progress=phases.append)
    assert result['status']=='READY' and len(vlm)==6 and len(coder)==2
    assert 'format' not in vlm[0] and 'format' in coder[0]
    assert vlm[0]['tools'] and vlm[0]['model']=='gpt-5.4-mini-2026-03-17'
    assert 'PRIVATE_FIXTURE' not in json.dumps(vlm+coder)
    assert coder[0]['messages'][-1]['content'].endswith(TEXT)
    assert result['handoff']['instruction']==TEXT
    assert [p['phase'] for p in phases][:4]==['ARCHITECTURE_CONTEXT','BASELINE','VLM_PLANNING','VLM_READING']
    assert (repo/TARGET).read_text()==BEFORE


def test_vlm_failure_does_not_silently_fall_back_to_coder(repo):
    from test_coding_handoff import ARCH
    job=context(repo);job.update(architectureId=ARCH['id'],architecture={**ARCH,'sourceCommitSha':job['commitSha']})
    result=engine.generate(repo,job,verifier=lambda _:report(False),vlm_chat=lambda _: {'status':'incomplete'},
                           chat=lambda _:pytest.fail('no coder call after failed VLM'))
    assert result['status']=='BLOCKED' and result['files']==[]


def test_pinned_architecture_cannot_be_omitted(repo):
    job=context(repo);job['architectureId']='11111111-1111-4111-8111-111111111111'
    with pytest.raises(Rejected,match='ARCHITECTURE_REQUIRED'):
        engine.generate(repo,job,verifier=lambda _:report(False),chat=lambda _:pytest.fail('no fallback'))
