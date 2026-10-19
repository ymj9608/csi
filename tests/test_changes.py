import json
import subprocess
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import scan_changes as module
from agent.csi_agent.changes import attach_change_facts, review_changes


def commit(repo):
    subprocess.run(['git','-C',str(repo),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
    return module.git(repo,'rev-parse','HEAD').decode().strip()


def test_git_diff_detects_literal_only_changes_and_preserves_line_numbers(tmp_path,monkeypatch):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    p=tmp_path/'models.py';p.write_text('class Signup:\n    name: str\n    label = "old-secret"\n')
    base=commit(tmp_path)
    p.write_text('class Signup:\n    name: str\n    phone_number: str\n    label = "new-secret"\n')
    (tmp_path/'ignored.md').write_text('not source')
    head=commit(tmp_path)
    calls=[]
    def scan(path):calls.append(path);return []
    monkeypatch.setattr(module,'scan',scan)
    result=module.collect(tmp_path,head,base)['changeSet']
    assert len(calls)==2 and result['baseSha']==base and result['headSha']==head
    f=result['files'][0];assert result['totalChangedFiles']==1
    assert f['facts']==[{'id':f['changeId']+':1','kind':'FIELD_ADDED','symbol':'Signup.phone_number','line':3}]
    assert all(secret not in json.dumps(result) for secret in ['old-secret','new-secret'])
    assert any(r['newLine']==4 and r['kind']!='CONTEXT' for r in f['rows'])


def test_missing_base_is_explicit_and_no_target_execution(tmp_path,monkeypatch):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    marker=tmp_path/'executed'
    (tmp_path/'danger.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    head=commit(tmp_path);monkeypatch.setattr(module,'scan',lambda _:[])
    assert module.collect(tmp_path,head,'f'*40)['changeSet']['status']=='BASE_UNAVAILABLE'
    assert module.collect(tmp_path,head,'0'*40)['changeSet']['status']=='NO_BASE'
    assert not marker.exists()
    with pytest.raises(ValueError):module.collect(tmp_path,'HEAD;echo unsafe',head)


def test_multiline_mask_and_limits():
    literal=module.changed_file('a.py','x = \"old\"\n','x = \"new\"\n')['rows'][0]
    assert literal['kind']=='MODIFIED' and literal['before']==literal['after']
    source='x = """sensitive\nvalue"""\n# private\nphone = 1012345678\n'
    rows=module.mask_lines(source,'.py')
    assert len(rows)==4 and 'sensitive' not in str(rows) and 'value' not in str(rows) and 'private' not in str(rows)
    assert '1012345678' not in str(rows)
    java='class A { /* secret\nmore */ String s = "password"; // token\n}'
    assert all(x not in str(module.mask_lines(java,'.java')) for x in ['secret','more','password','token'])
    changed=module.changed_file('a.py','','\n'.join(f'v{i} = 0' for i in range(150)))
    assert len(changed['rows'])==100 and changed['truncated'] and changed['addedLines']==150


def test_change_review_links_not_invents_findings():
    changes={'status':'AVAILABLE','baseSha':'a'*40,'headSha':'b'*40,'truncated':False,
             'files':[{'changeId':'1','filePath':'a.py','truncated':False,'rows':[{'kind':'ADDED','newLine':3}]}],
             'baselineFindings':[{'fingerprint':'old','filePath':'a.py','ruleId':'SEC-01'}]}
    findings=[{'id':'new-id','fingerprint':'new','filePath':'a.py','ruleId':'POL-01','startLine':3,'endLine':3}]
    report=[{'id':'new-id','analysis':{'facts':[],'unknowns':[]}}]
    attach_change_facts(report,findings,changes)
    a=report[0]['analysis'];assert a['changeContext']['status']=='NEW' and a['changeContext']['relation']=='CHANGED_LINES'
    assert a['facts'][0]['id']=='C1'
    reviewed=review_changes(changes,findings,{})['files'][0]
    assert reviewed['currentFindingIds']==['new-id'] and reviewed['removedFingerprints']==['old']
    assert reviewed['verdict']=='REVIEW_REQUIRED'
    findings[0]['startLine']=9;findings[0]['endLine']=9
    later=attach_change_facts([{'id':'new-id','analysis':{'facts':[],'unknowns':[]}}],findings,changes)
    assert later[0]['analysis']['changeContext']['relation']=='SAME_FILE'
    assert review_changes(changes,[],{})['files'][0]['verdict']=='NO_CURRENT_STATIC_CANDIDATES'


def test_model_input_omits_diff_and_review_requires_change_fact():
    from agent.csi_agent.analysis import base_report, review_messages, apply_review
    finding={'id':'id','ruleId':'POL-01','filePath':'sensitive_path.py','fingerprint':'x','startLine':1,'endLine':1,
             'maskedCodeEvidence':'DO_NOT_SEND_RAW_CODE'}
    report=base_report([finding],{}, {'version':'test'})
    changes={'status':'AVAILABLE','headSha':'b'*40,'baseSha':'a'*40,'truncated':False,'baselineFindings':[],
             'files':[{'filePath':finding['filePath'],'changeId':'c','truncated':False,
                       'rows':[{'kind':'ADDED','newLine':1,'after':'DO_NOT_SEND_DIFF'}]}]}
    attach_change_facts(report,[finding],changes)
    content=json.dumps(review_messages(report,[finding]))
    assert all(s not in content for s in ['DO_NOT_SEND_RAW_CODE','DO_NOT_SEND_DIFF','sensitive_path.py'])
    assert 'C1' in content
    output={'id':'id','red':'risk','blue':'limits','remediation':'review','citationIds':[],'factIds':['F1']}
    with pytest.raises(ValueError,match='Missing change evidence'):
        apply_review({'content':json.dumps({'findings':[output]})},report)
    output['factIds'].append('C1')
    apply_review({'content':json.dumps({'findings':[output]})},report)
    assert report[0]['analysis']['mode']=='LLM'
