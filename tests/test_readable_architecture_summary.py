import json

import pytest

from scripts.summarize_readable_architecture import diagnostic, load_report


def test_diagnostic_keeps_invalid_graph_invalid_but_counts_literal_edge():
    graph={'nodes':[{'id':'source'},{'id':'target'}],'edges':[{'from':'source','to':'target'}]}
    value={'components':[{'id':'source'}],
           'flows':[{'from':'source','to':'target','protection':'ASYNC'}]}
    report=diagnostic({'message':{'content':'','thinking':json.dumps(value)}},graph)
    assert report['literalComponentIdsMatched']==1
    assert report['literalDirectedEndpointsMatched']==1
    assert report['undeclaredEndpointIds']==['target']
    assert report['modeMisclassifiedAsProtection']==1
    assert value['components']==[{'id':'source'}]


def test_diagnostic_does_not_extract_json_from_freeform_prose():
    assert diagnostic({'message':{'content':'Text before {"components":[],"flows":[]}'}},
                      {'nodes':[],'edges':[]}) is None


def test_incomplete_log_cannot_be_published_as_finished_report(tmp_path):
    (tmp_path/'protocol.json').write_text('{}')
    (tmp_path/'measurements.jsonl').write_text('{"event":"vision_call"}\n')
    with pytest.raises(ValueError,match='EXPERIMENT_NOT_FINISHED'):
        load_report(tmp_path)
