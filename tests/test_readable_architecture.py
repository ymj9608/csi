import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from scripts.render_readable_architecture import render_svg

GRAPH = Path(__file__).resolve().parents[1] / 'tests/fixtures/complex_architecture/graph.json'


def test_drawing_preserves_every_directed_labeled_connection_and_component():
    graph = json.loads(GRAPH.read_text())
    svg, meta = render_svg(graph)
    root = ET.fromstring(svg)
    nodes = {el.attrib['data-node-id'] for el in root.iter() if 'data-node-id' in el.attrib}
    edges = [(el.attrib['data-edge-from'], el.attrib['data-edge-to'],
              el.attrib['data-edge-label'], el.attrib['data-edge-mode'])
             for el in root.iter() if 'data-edge-from' in el.attrib]
    assert nodes == {n['id'] for n in graph['nodes']}
    assert edges == [(e['from'],e['to'],e['label'],e['mode']) for e in graph['edges']]
    assert (meta['width'],meta['height']) == (3000,2320)
    assert len(edges) == 26 and len(nodes) == 28


def test_connection_rows_and_catalog_do_not_overlap_and_fit_the_canvas():
    _, meta = render_svg(json.loads(GRAPH.read_text()))
    boxes = [n['bbox'] for n in meta['nodes']] + [e['bbox'] for e in meta['edges']]
    for i,(x,y,w,h) in enumerate(boxes):
        assert 0 <= x < x+w <= meta['width'] and 0 <= y < y+h <= meta['height']
        for a,b,c,d in boxes[i+1:]:
            assert x+w <= a or a+c <= x or y+h <= b or b+d <= y


def test_unknown_endpoint_is_rejected_instead_of_silently_omitted():
    graph = json.loads(GRAPH.read_text())
    graph['edges'][0]['to'] = 'not_in_catalog'
    with pytest.raises(ValueError,match='Invalid connection'):
        render_svg(graph)


def test_layout_does_not_read_security_labels_or_code_hints():
    graph = json.loads(GRAPH.read_text())
    source = render_svg(graph)[0]
    augmented = copy.deepcopy(graph)
    augmented['ground_truth'] = 'SECRET_EVALUATION_ANSWER'
    augmented['nodes'][0]['filePath'] = 'secret/source.py'
    augmented['nodes'][0]['risk'] = 'SECURITY_ANSWER'
    assert render_svg(augmented)[0] == source


def test_downstream_uses_first_valid_context_not_later_better_result():
    from scripts.benchmark_readable_architecture import choose_first
    contexts={}
    first={'components':[],'flows':[]}
    later={'components':[{'id':'better'}],'flows':[]}
    choose_first(contexts,'readable',first,2)
    choose_first(contexts,'readable',later,3)
    assert contexts['readable']=={'context':first,'sequence':2}


def test_audit_preserves_followup_requests_missing_from_frozen_runner_queue(tmp_path):
    from scripts.benchmark_readable_architecture import response_audit
    raw={'done_reason':'stop','message':{'content':json.dumps({'needs':['module.py','invented.py']})}}
    (tmp_path/'readable-2.json').write_text(json.dumps(raw))
    result={'calls':[{'followup':True,'batch':2}],
            'findings':[{'support':[{'evidenceValid':False},{'evidenceValid':True}]}]}
    audit=response_audit(result,'readable',tmp_path,{'module.py'})
    assert [r['inManifest'] for r in audit['followupResponseNeeds']]==[True,False]
    assert audit['invalidSupportEvidence']==1


def test_empty_content_allows_only_entire_schema_valid_thinking_json():
    from scripts.benchmark_readable_architecture import structured_context
    from scripts.benchmark_complex_architecture import graph_context
    expected=graph_context(json.loads(GRAPH.read_text()))
    raw={'message':{'content':'','thinking':json.dumps(expected)}}
    assert structured_context(raw)==(expected,'message.thinking')
    raw['message']['thinking']='Reasoning before JSON: '+json.dumps(expected)
    with pytest.raises(ValueError):
        structured_context(raw)


def test_nonempty_invalid_content_does_not_fallback_to_other_field():
    from scripts.benchmark_readable_architecture import structured_context
    from scripts.benchmark_complex_architecture import graph_context
    expected=graph_context(json.loads(GRAPH.read_text()))
    with pytest.raises(ValueError):
        structured_context({'message':{'content':'invalid','thinking':json.dumps(expected)}})


def test_oracle_preserves_graph_without_security_answers():
    from scripts.benchmark_complex_architecture import graph_context
    graph=json.loads(GRAPH.read_text())
    oracle=graph_context(graph)
    assert {(e['from'],e['to'],e['data']) for e in oracle['flows']}=={(e['from'],e['to'],e['label']) for e in graph['edges']}
    assert not oracle['codeHints'] and all(e['protection']=='UNKNOWN' for e in oracle['flows'])
