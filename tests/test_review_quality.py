import json
import pytest
from evidence_context import collect_context
from mcp_servers.policy_review import compare_findings
from agent.csi_agent.analysis import base_report, llm_context, enrich

POLICY = {'version': 'test', 'approvedFields': ['email'], 'restrictedFields': ['phoneNumber'], 'inventorySection':'POL-02','inventoryPage':3}
REF = {'chunkId':'r1','sectionId':'POL-02','sectionTitle':'승인 목록','documentType':'INTERNAL_POLICY','pageNumber':3,'content':'가입 승인 목록은 email입니다.'}


def finding(field='name', context=None):
    return {'id':'a','ruleId':'POL-01','maskedCodeEvidence':f'{field}: str', 'codeContext':context or {},
            'filePath':'app.py','startLine':2,'evidenceStatus':'INSUFFICIENT_EVIDENCE'}


def test_policy_membership_not_approval_and_normalizes_alias():
    assert compare_findings([finding()],POLICY)['items'][0]['inventoryStatus']=='NOT_LISTED'
    policy=POLICY | {'approvedFields':['name']}
    item=compare_findings([finding()],policy)['items'][0]
    assert item['inventoryStatus']=='LISTED' and item['approvalRecord']=='NOT_CHECKED'
    assert compare_findings([finding('phone_number')],POLICY)['items'][0]['inventoryStatus']=='RESTRICTED'
    assert compare_findings([finding('uncertain')],POLICY)['items'][0]['inventoryStatus']=='UNKNOWN'
    assert compare_findings([finding()],{})['items'][0]['inventoryStatus']=='UNKNOWN'


def test_ast_tracks_explicit_path_and_lab_branch_but_not_unrelated_declaration(tmp_path):
    (tmp_path/'app.py').write_text('''
class Signup(Base):
    name: str
    phone_number: str
class ProfileUpdate(Base):
    name: str
class User(Base):
    name: str
class CsiSignupProfile(Base):
    phone_number: str

def signup(db, payload: Signup):
    user = User(**payload.model_dump(exclude={'phone_number'}))
    db.add(user)
    if settings.csi_lab_mode:
        db.add(CsiSignupProfile(phone_number=payload.phone_number))
''')
    contexts=list(collect_context(tmp_path).values())
    name=next(x for x in contexts if x['entity']=='User')
    phone=next(x for x in contexts if x['entity']=='CsiSignupProfile')
    assert len(name['signals'])==1 and not name['signals'][0]['labOnly']
    assert len(phone['signals'])==1 and phone['signals'][0]['labOnly']
    assert not next(x for x in contexts if x['entity']=='ProfileUpdate')['signals']
    report=base_report([finding('phone_number',phone)],{'POL-01':[REF]},POLICY)
    assert '실습' in report[0]['analysis']['remediation']
    ctx=llm_context(report,[finding('phone_number',phone)])[0]
    assert ctx['evidenceStatus']=='INSUFFICIENT_EVIDENCE'
    assert '제한 항목' in ctx['facts'][1]['text']
    assert 'app.py' not in json.dumps(ctx)  # local paths stay in CSI
    assert ctx['citations'][0]['excerpt']==REF['content']


def test_ast_does_not_invent_path_for_alias_overwrite_or_unknown_dump(tmp_path):
    (tmp_path/'app.py').write_text('''
class User(Base):
    name: str

def signup(db, payload: Signup):
    user = User(**payload.model_dump(include={'name'}))
    db.add(user)
    user = User(name=payload.name)
    user = something_else
    db.add(user)
''')
    assert all(not x['signals'] for x in collect_context(tmp_path).values())


@pytest.mark.asyncio
@pytest.mark.parametrize('fact_ids,citation_ids,expected',[(['F1','F2'],['r1'],'LLM'),(['fabricated'],['r1'],'LLM_FALLBACK'),(['F1'],[],'LLM_FALLBACK'),(['F1'],['fake'],'LLM_FALLBACK')])
async def test_llm_output_requires_real_facts_and_references(monkeypatch,fact_ids,citation_ids,expected):
    for k,v in {'LLM_MODE':'enabled','LLM_BASE_URL':'https://llm.invalid/v1','LLM_API_KEY':'test','LLM_MODEL':'test'}.items():monkeypatch.setenv(k,v)
    import agent.csi_agent.analysis as module
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':json.dumps({'findings':[{'id':'a','red':'r','blue':'b','remediation':'m','factIds':fact_ids,'citationIds':citation_ids}]})}}]}
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):return Response()
    monkeypatch.setattr(module.httpx,'AsyncClient',Client)
    f=finding();report,mode=await enrich(base_report([f],{'POL-01':[REF]},POLICY),[f])
    assert mode==expected
    assert report[0]['analysis']['evidenceStatus']=='INSUFFICIENT_EVIDENCE'
    if mode=='LLM':assert report[0]['analysis']['citedFactIds']==fact_ids
