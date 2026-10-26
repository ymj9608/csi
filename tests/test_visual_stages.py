"""Stage boundaries, fail-closed behavior and checkpoint recovery contracts."""
import copy
import json

import httpx
import jsonschema
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent.csi_agent import visual_review as vr, visual_stages as vs
from test_unified_visual_review import IMAGE, SHA, FINDING, POLICY, answer, report


def state():
    items = report()
    return {'packet': json.loads(vr.prepare(items, [FINDING], POLICY, {}, IMAGE, SHA)),
            'image': IMAGE, 'commit': SHA, 'model': vs.MODEL, 'report': items}


def replies():
    value = answer()
    return [{'architecture': value['architecture'], 'flows': [], 'uncertainties': ['Unknown runtime']},
            {'findings': value['findings']}, {'instructions': value['instructions']}]


@pytest.mark.asyncio
async def test_detailed_flows_survive_finalization_without_prose_reconstruction():
    outputs = replies()
    flows = [
        {'source': 'API', 'target': 'Internal SMS', 'condition': 'normal', 'data': 'phone',
         'boundary': 'INTERNAL', 'state': 'OBSERVED'},
        {'source': 'API', 'target': 'Support', 'condition': 'retry exhausted', 'data': 'phone and error',
         'boundary': 'EXTERNAL', 'state': 'INFERRED'},
        {'source': 'API', 'target': 'Collector', 'condition': 'direct call', 'data': 'event',
         'boundary': 'UNKNOWN', 'state': 'UNKNOWN'},
    ]
    outputs[0]['flows'] = flows
    async def caller(spec):
        return {'answer': outputs[vs.STAGES.index(spec['stage'])], 'usage': {}}
    result = await vs.build_analysis_graph(caller=caller).ainvoke(state())
    assert result['visualReview']['flowContext'] == {
        'schemaVersion': 1, 'flows': flows, 'uncertainties': ['Unknown runtime']}
    assert result['visualReview']['instructions'] == answer()['instructions']
    result['structure']['flows'][0]['target'] = 'changed later'
    assert result['visualReview']['flowContext']['flows'][0]['target'] == 'Internal SMS'


def test_default_review_model_is_requested_instruct_tag(monkeypatch):
    monkeypatch.delenv('CSI_REVIEW_VLM_MODEL', raising=False)
    assert vs.specification(vs.STAGES[0], state())['model'] == 'qwen3-vl:8b-instruct'


@pytest.mark.parametrize('mode', ['full_code', 'structured_text', 'code_image'])
@pytest.mark.asyncio
async def test_shared_graph_preserves_modalities_sources_and_metrics(mode):
    initial = state()
    initial['packet'].update(sources={'service.py': 'original source'}, editable=['service.py'])
    if mode == 'structured_text':
        initial['packet']['architecture'] = {'nodes': ['api', 'log']}
    if mode != 'code_image':
        initial['image'] = {k: v for k, v in IMAGE.items() if k != 'imageBase64'}
    calls = []
    async def caller(spec):
        i = len(calls); calls.append(spec)
        packet = json.loads(spec['messages'][1]['content'])
        assert packet['responseSchema'] == spec['format']
        assert packet['sources'] == initial['packet']['sources']
        assert packet['editable'] == ['service.py']
        assert ('images' in spec['messages'][1]) == (i == 0 and mode == 'code_image')
        assert ('architecture' in packet) == (i == 0 and mode == 'structured_text')
        jsonschema.validate(replies()[i], spec['format'])
        return {'answer': replies()[i], 'usage': {'prompt_eval_count': 30, 'eval_count': 10}}
    result = await vs.build_analysis_graph(caller=caller).ainvoke(initial)
    assert len(calls) == 3
    assert result['visualReview']['instructions'] == answer()['instructions']
    assert result['visualReview']['architecture'] == answer()['architecture']
    assert result['visualReview']['usage']['eval_count'] == 30


@pytest.mark.asyncio
async def test_failed_security_resumes_only_failed_stage_with_checkpoint():
    calls = []; fail = True
    async def caller(spec):
        nonlocal fail
        stage = spec['stage']; calls.append(stage)
        if stage == vs.STAGES[1] and fail:
            fail = False
            raise ValueError('VISUAL_REPEATED_OUTPUT')
        return {'answer': replies()[vs.STAGES.index(stage)], 'usage': {}}
    graph = vs.build_analysis_graph(caller=caller, checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': 'resume'}}
    with pytest.raises(ValueError, match='REPEATED_OUTPUT'):
        await graph.ainvoke(state(), config)
    saved = await graph.aget_state(config)
    assert saved.next == (vs.STAGES[1],) and 'visualReview' not in saved.values
    result = await graph.ainvoke(None, config)
    assert calls == [vs.STAGES[0], vs.STAGES[1], vs.STAGES[1], vs.STAGES[2]]
    assert result['visualReview']['instructions'] == answer()['instructions']
    assert len(result['stageTrace']) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['citation', 'finding', 'blank', 'repeat'])
async def test_invalid_intermediate_security_never_reaches_instruction(bad):
    calls = []
    async def caller(spec):
        stage = spec['stage']; calls.append(stage)
        value = replies()[vs.STAGES.index(stage)]
        if stage == vs.STAGES[1]:
            item = value['findings'][0]
            if bad == 'citation': item['citationIds'] = ['not-from-rag']
            if bad == 'finding': item['id'] = 'other'
            if bad == 'blank': item['red'] = ' '
            if bad == 'repeat': item['red'] = ('Repeated diagnosis with no additional information. ' * 3) * 3
        return {'answer': value, 'usage': {}}
    with pytest.raises(ValueError):
        await vs.build_analysis_graph(caller=caller).ainvoke(state())
    assert calls == list(vs.STAGES[:2])


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['eof', 'length', 'repeat', 'oversize', 'context', 'json'])
async def test_stream_rejects_invalid_or_repeating_output(bad):
    raw = json.dumps(replies()[0])
    if bad == 'repeat': raw = 'This long instruction sentence should not occur over and over again in an instruction. ' * 9
    if bad == 'oversize': raw = 'x' * 120001
    if bad == 'json': raw = '{invalid'
    event = {'message': {'content': raw}, 'done': bad != 'eof',
             'done_reason': 'length' if bad == 'length' else 'stop',
             'prompt_eval_count': 32000 if bad == 'context' else 100,
             'eval_count': 1000 if bad == 'context' else 100}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=json.dumps(event)+'\n'))
    with pytest.raises(ValueError):
        await vs.call_model(vs.specification(vs.STAGES[0], state()), transport=transport)


def test_no_shortening_of_instruction_and_no_silent_input_slicing():
    assert vs.schema(vs.STAGES[2], report())['$defs']['Instruction']['properties']['text']['maxLength'] == 3000
    large = state(); large['packet']['sources'] = {'source.py': 'x' * 80001}
    with pytest.raises(ValueError, match='CONTEXT_LIMIT'):
        vs.specification(vs.STAGES[0], large)
    passage = 'A distinct long paragraph about preserving a behavior while changing a security-relevant data path. ' * 2
    assert not vs.repeated_output(passage)
    assert vs.repeated_output(passage * 3)


def test_stage_schema_grounding_does_not_leak_other_stage_definitions():
    assert set(vs.schema(vs.STAGES[1], report())['$defs']) == {'LLMItem'}
    assert set(vs.schema(vs.STAGES[2], report())['$defs']) == {'Instruction'}
    initial = state()
    initial['packet']['policy']['contract'] = 'Preserve the functional API.'
    initial['packet']['task'] = 'Preserve the functional API.'
    initial['structure'] = replies()[0]
    packet = vs.context(vs.STAGES[1], initial)
    assert packet['policy']['contract'] == 'Preserve the functional API.'
    assert 'functionalContract' not in packet


@pytest.mark.asyncio
async def test_remote_endpoint_is_rejected(monkeypatch):
    monkeypatch.setenv('CSI_REVIEW_OLLAMA_URL', 'https://example.com')
    with pytest.raises(ValueError, match='LOCAL_REVIEW_OLLAMA_REQUIRED'):
        await vs.call_model(vs.specification(vs.STAGES[0], state()))
