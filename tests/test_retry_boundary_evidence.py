import pytest
from pathlib import Path
from scripts.retry_boundary_evidence import plan
ROOT=Path(__file__).resolve().parents[1]
def sources():return {p.name:p.read_text() for p in (ROOT/'tests/fixtures/retry_boundary').iterdir() if p.name!='test_contract.py'}
INITIAL=['service.py','analysis.py','notification.py']
def test_same_mandatory_evidence_for_both_arms():
 a=plan(sources(),INITIAL);b=plan(sources(),INITIAL,'notification.py -> exporter.py; nonexistent.py')
 assert a['selected']==b['selected']
 assert set(a['additional'])=={'retry.py','deadletter.py','exporter.py','topology.json'}
 assert b['unresolvedVisionFiles']==['nonexistent.py']
 assert 'exporter.py' not in b['importGraph']['notification.py']
def test_no_silent_truncation_of_required_sources():
 with pytest.raises(ValueError,match='MANDATORY_EVIDENCE_EXCEEDS_BUDGET'):plan(sources(),INITIAL,budget=3)
def test_missing_external_zone_blocks_instead_of_guessing():
 s=sources();s['topology.json']='{}'
 with pytest.raises(ValueError,match='EXTERNAL_EVIDENCE_MISSING'):plan(s,INITIAL)
