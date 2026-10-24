"""Experiment integrity; these tests do not measure model intelligence."""
import json
from pathlib import Path

import pytest
from scripts import benchmark_windows_vlm as run
from scripts.vlm_experiment_data import make_case, materialize


def test_patch_scope_and_public_interface_are_enforced():
    case=make_case()
    path,source=next(iter(case['solution'].items()))
    answer={'files':[{'path':path,'source':source}]}
    assert run.validate_patch(answer,case,case['sources'])==case['solution']
    helper=source+'\ndef _helper(value):\n    return value\n'
    assert run.validate_patch({'files':[{'path':path,'source':helper}]},case,case['sources'])[path]==helper
    with pytest.raises(ValueError,match='PATCH_SCOPE'):
        run.validate_patch(answer,case,{'app.py':case['sources']['app.py']})
    with pytest.raises(ValueError,match='PATCH_SCOPE'):
        run.validate_patch({'files':[{'path':'../.env','source':source}]},case,case['sources'])
    with pytest.raises(ValueError,match='PUBLIC_SIGNATURE_CHANGED'):
        run.validate_patch({'files':[{'path':path,'source':source.replace('def emit(event)', 'def emit(event, extra)')}]},case,case['sources'])


def test_frozen_inputs_detect_image_and_test_changes(tmp_path,monkeypatch):
    out=tmp_path/'run'
    run.freeze(out)
    run.check_frozen(out)
    image=out/'cases/retry-small/architecture.png'
    image.write_bytes(image.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='FIXTURE_CHANGED'):
        run.check_frozen(out)
    with pytest.raises(FileExistsError):
        run.freeze(out)


def test_four_arms_use_same_tools_coder_and_no_evaluator_input(tmp_path,monkeypatch):
    out=tmp_path/'run'; run.freeze(out)
    run.write(out/'compatibility.json',[{'model':run.MODELS[0],'actionPassed':True}])
    run.write(out/'controls.json',[])
    requests=[]
    case=make_case()
    sequence=[('read','relay.py'),('delegate',''),('verify',''),('finish','')]
    def fake_call(folder,name,model,messages,schema,**kwargs):
        requests.append({'arm':folder.name,'name':name,'model':model,'messages':messages.copy()})
        if name.startswith('coder'):
            return {'status':'COMPLETED','answer':{'files':[{'path':p,'source':s} for p,s in case['solution'].items()]}}
        action,path=sequence[int(name.split('-')[-1])]
        return {'status':'COMPLETED','answer':{'action':action,'path':path,'query':'','instruction':'Preserve internal phone and redact external route.' if action=='delegate' else ''}}
    monkeypatch.setattr(run,'call',fake_call)
    monkeypatch.setattr(run,'reset_models',lambda:None)
    monkeypatch.setattr(run,'verify',lambda _: {'exitCode':0,'total':8,'passed':8,'cases':{}})
    run.pilot(out,'retry-small',run.MODELS[0])
    first={r['arm']:r['messages'][1] for r in requests if r['name']=='action-0'}
    code=json.loads(first['code_search']['content'])
    image=json.loads(first['image_search']['content'])
    assert code==image
    assert 'images' in first['image_search'] and 'images' not in first['code_search']
    text=json.loads(first['text_search']['content'])
    assert text.pop('architecture')==case['graph'] and text==code
    assert set(json.loads(first['full_code']['content'])['sources'])==set(case['sources'])
    for r in requests:
        content=json.dumps(r['messages'])
        assert 'test_contract' not in content and "class Contract" not in content
        if r['name'].startswith('coder'):
            assert r['model']==run.CODER
            packet=json.loads(r['messages'][1]['content'])
            assert set(packet['editable'])<=set(packet['sources'])
    assert 'relay.py' in code['sourceIndex']['recovery.py']['imports']
    assert 'recovery.py' in code['sources'] and 'relay.py' not in code['sources']
    assert all(json.loads(p.read_text())['status']=='PASSED' for p in (out/'pilot').rglob('result.json'))


def test_model_cannot_finish_without_verification(tmp_path,monkeypatch):
    out=tmp_path/'run'; run.freeze(out)
    run.write(out/'compatibility.json',[{'model':run.MODELS[0],'actionPassed':True}])
    run.write(out/'controls.json',[])
    monkeypatch.setattr(run,'call',lambda *a,**kw: {'status':'COMPLETED','answer':{
        'action':'finish','path':'','query':'','instruction':''}})
    monkeypatch.setattr(run,'reset_models',lambda:None)
    run.pilot(out,'retry-small',run.MODELS[0])
    rows=[json.loads(p.read_text()) for p in (out/'pilot').rglob('result.json')]
    assert len(rows)==4 and all(r['status']=='FAILED' and r['error']=='TURN_LIMIT' for r in rows)


def test_size_variant_preserves_real_task_and_is_not_independent():
    small,large=make_case(),make_case(expanded=True)
    assert small['tests']==large['tests'] and small['graph']==large['graph']
    assert small['solution']==large['solution']
    assert all(large['sources'][p]==s for p,s in small['sources'].items())
    assert len(large['sources'])-len(small['sources'])==48


def test_retry_coder_receives_previous_proposal_and_actual_verifier_failure(tmp_path,monkeypatch):
    out=tmp_path/'run'; run.freeze(out)
    run.write(out/'compatibility.json',[{'model':run.MODELS[0],'actionPassed':True}])
    run.write(out/'controls.json',[])
    case=make_case(); requests=[]
    actions=[('read','relay.py'),('delegate',''),('verify',''),('delegate',''),('verify',''),('finish','')]
    proposal={'files':[{'path':p,'source':s} for p,s in case['solution'].items()]}
    def model(folder,name,model,messages,schema,**kwargs):
        if name.startswith('coder'):
            requests.append((name,messages))
            return {'status':'COMPLETED','answer':proposal}
        action,path=actions[int(name.split('-')[-1])]
        return {'status':'COMPLETED','answer':{'action':action,'path':path,'query':'','instruction':'Repair based on the supplied diagnostics.'}}
    def verifier(folder):
        first=folder.name=='candidate-1'
        return {'exitCode':1 if first else 0,'passed':7 if first else 8,'total':8,'cases':{},
                'log':'REAL_FAILURE_DIAGNOSTIC' if first else 'all passed'}
    monkeypatch.setattr(run,'call',model)
    monkeypatch.setattr(run,'verify',verifier)
    monkeypatch.setattr(run,'reset_models',lambda:None)
    run.pilot(out,'retry-small',run.MODELS[0])
    for name,messages in requests:
        if name=='coder-2':
            assert json.loads(next(m['content'] for m in messages if m['role']=='assistant'))==proposal
            assert 'REAL_FAILURE_DIAGNOSTIC' in json.dumps(messages)
        else:
            assert not any(m['role']=='assistant' for m in messages)


def test_failed_new_candidate_cannot_reuse_old_successful_verification(tmp_path,monkeypatch):
    out=tmp_path/'run'; run.freeze(out)
    run.write(out/'compatibility.json',[{'model':run.MODELS[0],'actionPassed':True}])
    run.write(out/'controls.json',[])
    actions=[('read','relay.py'),('delegate',''),('verify',''),('delegate',''),('finish',''),('block','')]
    case=make_case()
    def model(folder,name,model,messages,schema,**kwargs):
        if name=='coder-2': return {'status':'FAILED','error':'OUTPUT_INCOMPLETE'}
        if name=='coder-1': return {'status':'COMPLETED','answer':{'files':[{'path':p,'source':s} for p,s in case['solution'].items()]}}
        action,path=actions[int(name.split('-')[-1])]
        return {'status':'COMPLETED','answer':{'action':action,'path':path,'query':'','instruction':''}}
    monkeypatch.setattr(run,'call',model)
    monkeypatch.setattr(run,'verify',lambda _: {'exitCode':0,'passed':8,'total':8,'cases':{}})
    monkeypatch.setattr(run,'reset_models',lambda:None)
    run.pilot(out,'retry-small',run.MODELS[0])
    rows=[json.loads(p.read_text()) for p in (out/'pilot').rglob('result.json')]
    assert all(r['status']=='FAILED' and r['verification'] is None for r in rows)


def test_wasi_blocks_host_access_writes_and_network(tmp_path):
    pytest.importorskip('wasmtime')
    from scripts.experiment_wasi import RUNTIME, verify
    if not (RUNTIME/'bin/python-3.12.0.wasm').exists(): pytest.skip('WASI Python not installed')
    (tmp_path/'test_contract.py').write_text('''import os,socket,unittest
class Isolation(unittest.TestCase):
    def test_host(self):
        with self.assertRaises(OSError): open('/Windows/win.ini').read()
    def test_write(self):
        with self.assertRaises(OSError): open('/case/injected.txt','w')
    def test_network(self):
        with self.assertRaises(OSError): socket.socket()
    def test_environment(self):
        self.assertNotIn('OPENAI_API_KEY',os.environ)
''',encoding='utf-8')
    result=verify(tmp_path)
    assert result['exitCode']==0 and result['passed']==4, result
    assert not (tmp_path/'injected.txt').exists()
