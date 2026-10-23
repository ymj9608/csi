from pathlib import Path

import pytest

from coding_agent.call_contract import collect_call_contract, contradictory_input_accesses, validate_call_contracts
from coding_agent.repository import Rejected
from coding_agent.scoped_handoff import build_handoff, replace_function, ScopeError


TARGET = 'def forward(envelope):\n    return envelope\n'


@pytest.mark.parametrize('caller', [
    "from exporter import forward\nforward({'event': item, 'error': err, 'attempts': n})",
    "from exporter import forward as send\nsend(envelope={'event': item, 'error': err, 'attempts': n})",
    "import exporter as out\nout.forward({'event': item, 'error': err, 'attempts': n})",
])
def test_real_call_argument_structure_not_output_wrapper(caller):
    contract = collect_call_contract({'exporter.py': TARGET, 'caller.py': caller}, 'exporter.py', 'forward')
    arg = contract['calls'][0]['arguments']['envelope']
    assert arg['closed'] and arg['keys'] == ['event', 'error', 'attempts']
    assert contradictory_input_accesses("def forward(envelope): return envelope['payload']['event']", contract)
    assert not contradictory_input_accesses("def forward(envelope): return envelope['event']", contract)


@pytest.mark.parametrize('argument', ['value', "{'event': item, **extra}"])
def test_unknown_inputs_do_not_invent_a_closed_schema(argument):
    contract = collect_call_contract({'exporter.py': TARGET,
                                     'caller.py': 'from exporter import forward\nforward(' + argument + ')'},
                                    'exporter.py', 'forward')
    assert not contradictory_input_accesses("def forward(envelope): return envelope['payload']", contract)


@pytest.mark.parametrize('caller', [
    "from other import forward\nforward({'wrong': 1})",
    "from exporter import forward\nforward = other\nforward({'wrong': 1})",
    "from exporter import forward\ndef run(forward):\n    forward({'wrong': 1})",
])
def test_unrelated_or_shadowed_symbols_not_used_as_evidence(caller):
    contract = collect_call_contract({'exporter.py': TARGET, 'caller.py': caller}, 'exporter.py', 'forward')
    assert contract['status'] == 'UNKNOWN' and not contract['calls']


def test_relative_import_and_budget_are_explicit():
    sources = {'app/exporter.py': TARGET,
               'app/caller.py': "from .exporter import forward\nforward({'event': 1})\nforward({'event': 2})"}
    contract = collect_call_contract(sources, 'app/exporter.py', 'forward', max_calls=1)
    assert len(contract['calls']) == 1 and contract['truncated']


def test_previous_failed_patch_is_rejected_before_execution():
    root = Path(__file__).parent / 'fixtures/retry_boundary'
    sources = {p.name: p.read_text() for p in root.iterdir() if p.is_file() and p.name != 'test_contract.py'}
    packet = build_handoff(sources, 'exporter.py', 'forward', {'exporter.py'},
                           ['deadletter.py', 'topology.json'], 'Follow the diagram', [])
    assert packet['inputContract']['calls'][0]['path'] == 'deadletter.py'
    with pytest.raises(ScopeError, match='INPUT_CONTRACT_MISMATCH'):
        replace_function(sources['exporter.py'], packet,
                         "def forward(envelope):\n    return envelope['payload']['event']")


def test_optional_lookup_not_confused_with_required_read():
    contract = collect_call_contract({'exporter.py': TARGET,
                                     'caller.py': "from exporter import forward\nforward({'event': 1})"},
                                    'exporter.py', 'forward')
    assert not contradictory_input_accesses("def forward(envelope): return envelope.get('payload')", contract)
    assert not contradictory_input_accesses("def forward(envelope): return envelope['payload'] if 'payload' in envelope else envelope", contract)
    assert contradictory_input_accesses("def forward(envelope): return envelope if 'payload' in envelope else envelope['payload']", contract)


def test_return_annotation_preserved():
    source = 'def forward(envelope) -> dict:\n    return envelope\n'
    packet = build_handoff({'exporter.py': source}, 'exporter.py', 'forward', {'exporter.py'},
                           ['exporter.py'], 'x', [])
    assert replace_function(source, packet, 'def forward(envelope) -> dict:\n    return dict(envelope)')
    with pytest.raises(ScopeError, match='RETURN_ANNOTATION_CHANGED'):
        replace_function(source, packet, 'def forward(envelope) -> str:\n    return str(envelope)')


def test_live_validator_returns_structured_caller_feedback():
    contract = collect_call_contract({'exporter.py': TARGET,
                                     'caller.py': "from exporter import forward\nforward({'event': 1})"},
                                    'exporter.py', 'forward')
    with pytest.raises(Rejected, match='INPUT_CONTRACT_MISMATCH') as error:
        validate_call_contracts("def forward(envelope): return envelope['payload']", [contract])
    conflict = error.value.details['conflicts'][0]
    assert conflict['caller'] == 'caller.py' and conflict['observedKeys'] == ['event']
    assert conflict['key'] == 'payload'
