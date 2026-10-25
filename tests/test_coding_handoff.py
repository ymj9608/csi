"""Direct delegation contract, with local model transport replaced by captured responses."""
import base64
import hashlib
import json
import struct
import httpx
import pytest
from coding_agent.handoff import create_handoff, prepare_image
from coding_agent.repository import Rejected

IMAGE=b'\x89PNG\r\n\x1a\n'+b'\0\0\0\rIHDR'+struct.pack('>II',20,20)+b'\x08\x02\0\0\0'+b'\0'*4
ARCH={'id':'11111111-1111-4111-8111-111111111111','imageBase64':base64.b64encode(IMAGE).decode(),
      'imageSha256':hashlib.sha256(IMAGE).hexdigest(),'sourceCommitSha':'a'*40}
PACKET={'commitSha':'a'*40,'findings':[{'id':'finding-1'}],'references':[{'id':'ref-1','excerpt':'cost 12'}],
        'sourceFiles':{'backend/app/core/csi_signup.py':'def hash_signup_password(): pass'}}
TEXT='코딩 Agent에게: finding-1 및 ref-1 근거에 따라 비밀번호 저장을 보완하세요. 기존 계정 호환성은 유지하고 테스트 및 관리자 승인을 받으세요.'

def reply(text=TEXT):
    return {'done':True,'done_reason':'stop','message':{'content':text},'prompt_eval_count':100,'eval_count':50,
            'total_duration':100,'load_duration':10,'prompt_eval_duration':20,'eval_duration':70}

def test_plain_text_single_call_with_original_image_and_evidence():
    calls=[]
    def chat(payload):calls.append(payload);return reply()
    result=create_handoff(ARCH,PACKET,chat=chat)
    assert len(calls)==1 and 'format' not in calls[0] and 'tools' not in calls[0]
    assert calls[0]['model']=='qwen3-vl:8b'
    assert calls[0]['messages'][1]['images']==[ARCH['imageBase64']]
    assert json.loads(calls[0]['messages'][1]['content'])['sourceFiles']==PACKET['sourceFiles']
    assert result['instruction']==TEXT and result['imageSha256']==ARCH['imageSha256']
    assert result['sourceCommitMatches'] is True
    assert 'imageBase64' not in result and result['metrics']['eval_count']==50

@pytest.mark.parametrize('changes,code',[
    ({'sourceCommitSha':'b'*40},'ARCHITECTURE_COMMIT_MISMATCH'),
    ({'imageSha256':'b'*64},'ARCHITECTURE_DIGEST_MISMATCH'),
    ({'imageBase64':'not valid base64'},'ARCHITECTURE_IMAGE_INVALID'),
    ({'id':'not-uuid'},'ARCHITECTURE_IMAGE_INVALID'),
])
def test_invalid_image_never_reaches_model(changes,code):
    with pytest.raises(Rejected,match=code):
        create_handoff({**ARCH,**changes},PACKET,chat=lambda _:pytest.fail('no inference'))

@pytest.mark.parametrize('text,code',[
    ('','VLM_INSTRUCTION_INVALID'),
    ('{"instruction":"finding-1 ref-1 do a change"}','VLM_TEXT_REQUIRED'),
    ('```json\n'+TEXT+'\n```','VLM_TEXT_REQUIRED'),
    ('코딩 Agent에게: 근거가 없는 일반 수정 지시문입니다.','VLM_EVIDENCE_MISSING'),
])
def test_invalid_work_order_is_not_forwarded(text,code):
    with pytest.raises(Rejected,match=code):create_handoff(ARCH,PACKET,chat=lambda _:reply(text))

def test_truncated_or_reasoning_only_output_is_not_a_work_order():
    raw=reply();raw['done_reason']='length'
    with pytest.raises(Rejected,match='VLM_OUTPUT_INCOMPLETE'):create_handoff(ARCH,PACKET,chat=lambda _:raw)
    raw=reply('');raw['message']['thinking']=TEXT
    with pytest.raises(Rejected,match='VLM_INSTRUCTION_INVALID'):create_handoff(ARCH,PACKET,chat=lambda _:raw)

def test_unknown_revision_is_recorded_not_claimed_matching():
    result=create_handoff({**ARCH,'sourceCommitSha':''},PACKET,chat=lambda _:reply())
    assert result['sourceCommitMatches'] is None

def test_timeout_and_missing_usage_are_explicit_failures():
    def timeout(_):raise httpx.ReadTimeout('private details')
    with pytest.raises(Rejected,match='^VLM_TIMEOUT$'):create_handoff(ARCH,PACKET,chat=timeout)
    raw=reply();raw.pop('prompt_eval_count')
    with pytest.raises(Rejected,match='VLM_USAGE_MISSING'):create_handoff(ARCH,PACKET,chat=lambda _:raw)


def test_only_explicit_final_block_can_be_read_from_thinking_field():
    raw=reply('');raw['message']['thinking']='PRIVATE_REASONING\n<coding_instruction>'+TEXT+'</coding_instruction>'
    result=create_handoff(ARCH,PACKET,chat=lambda _:raw)
    assert result['instruction']==TEXT and result['responseField']=='thinking_final_block'
    assert 'PRIVATE_REASONING' not in str(result)
    raw['message']['thinking']+='<coding_instruction>duplicate</coding_instruction>'
    with pytest.raises(Rejected,match='VLM_INSTRUCTION_INVALID'):create_handoff(ARCH,PACKET,chat=lambda _:raw)


def test_profile_context_excludes_unrelated_functions():
    from coding_agent.handoff import source_context
    sources={'backend/app/services/hub.py':'import auth\ndef signup():\n    return 1\ndef unrelated():\n    return "UNRELATED"\n',
             'backend/app/schemas/dto.py':'class Signup:\n    password: str\nclass Other:\n    ignored: str\n'}
    selected=source_context(sources)
    assert 'def signup' in selected['backend/app/services/hub.py']
    assert 'class Signup' in selected['backend/app/schemas/dto.py']
    assert 'UNRELATED' not in str(selected) and 'class Other' not in str(selected)


def test_prefilled_final_answer_without_echoing_opening_tag_is_accepted():
    calls=[]
    def model(payload):calls.append(payload);return reply(TEXT+'\n</coding_instruction>')
    result=create_handoff(ARCH,PACKET,chat=model)
    assert result['instruction']==TEXT
    assert calls[0]['messages'][-1]=={'role':'assistant','content':'</think>\n<coding_instruction>\n'}
    assert 'format' not in calls[0]
