import json

import httpx

from scripts.benchmark_complex_architecture import graph_context, review, score, source_batches


def test_whole_source_batches_preserve_unicode_and_long_lines():
    sources = {
        'services/a/one.py': 'x = "' + '가나다' * 10000 + '"\nprint(x)\n',
        'services/a/two.py': 'value = 2\n',
        'services/b/two.py': 'value = 3\n',
    }
    actual = {}
    for batch in source_batches(sources):
        for row in batch.values():
            for numbered in row['source'].splitlines():
                line, value = numbered.split('|', 1)
                actual.setdefault((row['filePath'], int(line)), []).append(value)
    for path, source in sources.items():
        for line, expected in enumerate(source.splitlines(), 1):
            assert ''.join(actual[(path, line)]) == expected


def test_same_file_positive_does_not_flag_safe_function():
    case = {'positives': [{'id': 'P', 'path': 'a.py', 'category': 'sensitive_logging',
                          'line_start': 3, 'line_end': 3,
                          'required_evidence': [{'path': 'a.py', 'line_start': 3, 'line_end': 3}]}],
            'negatives': [{'id': 'N', 'path': 'a.py', 'line_start': 8, 'line_end': 9}],
            'required_context_paths': [{'path': 'a.py'}]}
    finding = {'filePath': 'a.py', 'line': 3, 'category': 'sensitive_logging', 'evidenceValid': True, 'support': []}
    result = score([finding], case, ['a.py'])
    assert result['verifiedMatches'] == ['P']
    assert result['negativeControlFlags'] == []
    assert score([{**finding, 'line': 8}], case, ['a.py'])['negativeControlFlags'] == ['N']
    assert score([{**finding, 'evidenceValid': False}], case, ['a.py'])['verifiedMatches'] == []


def test_structured_control_preserves_ids_and_has_no_code_hints():
    graph = {'nodes': [{'id': 'orders', 'label': 'Order work', 'kind': 'SERVICE'}], 'edges': [], 'groups': []}
    result = graph_context(graph)
    assert result['components'][0]['label'] == 'orders — Order work'
    assert result['codeHints'] == []


def test_followup_is_bounded_and_unknown_path_is_never_opened(tmp_path):
    calls = []
    def transport(request):
        payload = json.loads(request.content)
        supplied = json.loads(payload['messages'][1]['content'])['sources']
        calls.append({row['filePath'] for row in supplied})
        data = {'findings': [], 'needs': ['b.py', '../../.env'] if len(calls) == 1 else [], 'uncertainties': []}
        return httpx.Response(200, json={'done_reason': 'stop', 'message': {'content': json.dumps(data)},
            'prompt_eval_count': 50, 'eval_count': 20, 'total_duration': 1,
            'load_duration': 0, 'prompt_eval_duration': 1, 'eval_duration': 0})
    with httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(transport)) as api:
        result = review(api, {'a.py': 'x=1\n', 'b.py': 'y=2\n'}, ['a.py'], None, tmp_path, 'test', lambda r: None)
    assert calls == [{'a.py'}, {'b.py'}]
    assert result['effectivePaths'] == ['a.py', 'b.py']
    assert result['followupCalls'] == 1
    assert result['rejectedNeeds'] == [{'path': '../../.env', 'reason': 'NOT_IN_MANIFEST'}]


def test_truncated_response_cost_is_kept_and_not_scored(tmp_path):
    def transport(request):
        return httpx.Response(200, json={'done_reason': 'length', 'message': {'content': '{'},
            'prompt_eval_count': 300, 'eval_count': 1600, 'total_duration': 1,
            'load_duration': 0, 'prompt_eval_duration': 1, 'eval_duration': 0})
    with httpx.Client(base_url='http://localhost', transport=httpx.MockTransport(transport)) as api:
        result = review(api, {'a.py': 'x=1\n'}, ['a.py'], None, tmp_path, 'test', lambda r: None)
    assert not result['complete']
    assert result['totals']['eval_count'] == 1600
    assert result['errors'][0]['code'] == 'OUTPUT_INCOMPLETE'
    assert result['findings'] == []
