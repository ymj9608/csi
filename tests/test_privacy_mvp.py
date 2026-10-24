import json
from pathlib import Path

import pytest

from scripts import benchmark_privacy_mvp as run
from scripts.privacy_mvp_data import CONFIG, case


@pytest.mark.parametrize('name', CONFIG)
def test_models_get_complete_sources_but_not_tests_or_reference_solution(name):
    value=case(name)
    messages=run.planner_messages(value)
    packet=json.loads(messages[1]['content'])
    assert packet['sources']==value['sources']
    assert 'tests' not in packet and 'solution' not in packet and 'graph' not in packet
    coder,schema=run.common.coder_request(value,'Repair the privacy issue.',value['sources'])
    assert schema['properties']['files']['items']['properties']['path']['enum']==['adapter.py']
    assert all('images' not in m for m in coder)
    assert all(value['tests'] not in m['content'] for m in coder)


def test_previous_proposal_and_actual_failure_reach_both_models():
    value=case('fanout'); feedback={'passed':0,'error':'NameError: json'}
    planned=run.planner_messages(value,'previous proposal',feedback)
    assert json.loads(planned[-1]['content'])['verification']==feedback
    coder,_=run.common.coder_request(value,'fix missing import',value['sources'],'previous proposal',feedback)
    assert coder[2]['content']=='previous proposal'
    assert json.loads(coder[3]['content'])['previousAttemptFeedback']==feedback


def test_higher_partial_score_never_becomes_ready(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'frozen',lambda _: {})
    monkeypatch.setattr(run.common,'reset_models',lambda: None)
    value=case('fanout')
    def call(folder,name,model,messages,schema,**kwargs):
        if name.startswith('plan'):
            return {'status':'COMPLETED','answer':{'instruction':'repair','external_recipients':['r2','r3'],'normal_recipients':['r1','r2'],'failure_recipients':['r2','r3']}}
        answer={'files':[{'path':'adapter.py','source':value['solution']['adapter.py']}]}
        return {'status':'COMPLETED','answer':answer,'answerText':json.dumps(answer)}
    monkeypatch.setattr(run.common,'call',call)
    checks=iter([{'exitCode':1,'passed':3,'total':4}, {'exitCode':1,'passed':0,'total':4}])
    monkeypatch.setattr(run,'verify',lambda _: next(checks))
    row=run.run_condition(tmp_path,'fanout','code_only',42)
    assert row['bestPassed']==3 and row['status']=='FAILED'
    assert 'selectedCandidate' not in row
    assert len(row['attempts'])==2


def test_verified_first_candidate_stops_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'frozen',lambda _: {})
    monkeypatch.setattr(run.common,'reset_models',lambda: None)
    value=case('fanout')
    original_read=Path.read_text
    def windows_read(path,*args,**kwargs):
        if path.parent.name=='calls' and 'encoding' not in kwargs:
            return path.read_bytes().decode('cp949')
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',windows_read)
    def call(folder,name,model,messages,schema,**kwargs):
        run.common.write(folder/'calls'/f'{name}.json', {'model':model,'wallSeconds':1.0,
                         'answerText':'Preserve build_deliveries’ return value.', 'inputTokens':1,'outputTokens':1})
        if name.startswith('plan'):
            return {'status':'COMPLETED','answer':{'instruction':'repair','external_recipients':[],'normal_recipients':[],'failure_recipients':[]}}
        answer={'files':[{'path':'adapter.py','source':value['solution']['adapter.py']}]}
        return {'status':'COMPLETED','answer':answer,'answerText':json.dumps(answer)}
    monkeypatch.setattr(run.common,'call',call)
    monkeypatch.setattr(run,'verify',lambda _: {'exitCode':0,'passed':4,'total':4})
    row=run.run_condition(tmp_path,'fanout','code_only',42)
    assert row['status']=='PASSED' and row['selectedCandidate']=='candidate-1'
    assert len(row['attempts'])==1
