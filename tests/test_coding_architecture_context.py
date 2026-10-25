import copy
from coding_agent.architecture_context import resolve


def fixture():
    return {'projectId': 'project-a', 'architectureDiagram': {
        'id': 'diagram-a', 'projectId': 'project-a', 'status': 'EXTRACTED', 'confirmed': False,
        'components': [
            {'name': 'Checkout gateway', 'role': 'Payment authorization', 'state': 'OBSERVED', 'isolationStatus': 'PRODUCTION'},
            {'name': 'Signup demo', 'role': 'Synthetic account creation', 'state': 'INFERRED', 'isolationStatus': 'ISOLATED'},
        ]}}


def test_matches_saved_components_for_different_projects_and_keeps_provenance():
    context = fixture()
    result = resolve(context, [{'id': 'f1', 'filePath': 'src/payment/CheckoutGateway.java'}])
    assert result['status'] == 'MATCHED'
    assert [c['name'] for c in result['components']] == ['Checkout gateway']
    assert result['components'][0]['matches'][0]['findingId'] == 'f1'
    assert result['diagramId'] == 'diagram-a' and result['confirmed'] is False
    assert result['matchMethod'] == 'LEXICAL_CANDIDATE'
    context['projectId'] = context['architectureDiagram']['projectId'] = 'project-b'
    result = resolve(context, [{'id': 'f2', 'filePath': 'backend/app/core/csi_signup.py'}])
    assert result['components'][0]['name'] == 'Signup demo'
    assert result['components'][0]['state'] == 'INFERRED'


def test_missing_unfinished_other_project_and_unmatched_never_invent_component():
    assert resolve({}, [])['status'] == 'UNAVAILABLE'
    for field, value in [('projectId', 'another-project'), ('status', 'ANALYZING')]:
        context = fixture()
        context['architectureDiagram'][field] = value
        assert resolve(context, [{'id': 'f', 'filePath': 'payment.py'}])['components'] == []
    result = resolve(fixture(), [{'id': 'f', 'filePath': 'unrelated.py'}])
    assert result['status'] == 'NO_MATCH' and not result['components']
    assert '후보를 찾지 못했' in result['note']


def test_unknown_components_and_generic_path_terms_do_not_match():
    context = fixture()
    context['architectureDiagram']['components'][0]['state'] = 'UNKNOWN'
    assert resolve(context, [{'id': 'f', 'filePath': 'app/payment.py'}])['status'] == 'NO_MATCH'
    context['architectureDiagram']['components'][0].update(name='Backend service', role='Application system', state='OBSERVED')
    assert resolve(context, [{'id': 'f', 'filePath': 'backend/app/core/unrelated.py'}])['status'] == 'NO_MATCH'


def test_untrusted_long_names_cannot_exceed_progress_limit_or_mutate_snapshot():
    context = fixture()
    context['architectureDiagram']['components'][0]['name'] = 'Checkout ' + '😀' * 300
    original = copy.deepcopy(context)
    result = resolve(context, [{'id': 'f', 'filePath': 'checkout.py'}])
    assert len(result['note'].encode('utf-16-le')) <= 400
    assert context == original
