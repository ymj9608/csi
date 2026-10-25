import pytest
from coding_agent.scoped_handoff import build_handoff,replace_function,ScopeError
S='VALUE = 1\ndef forward(data):\n    return data\n\ndef keep():\n    return VALUE\n'
def packet():return build_handoff({'exporter.py':S,'topology.json':'{}'},'exporter.py','forward',{'exporter.py'},['topology.json'],'Remove phone from external copy',['keep original'])
def test_only_function_changes():
 out=replace_function(S,packet(),'def forward(data):\n    return dict(data)')
 assert out.startswith('VALUE = 1\n') and out.endswith('def keep():\n    return VALUE\n')
def test_stale_source_rejected():
 with pytest.raises(ScopeError,match='SOURCE_CHANGED'):replace_function(S+'\n',packet(),'def forward(data): return data')
@pytest.mark.parametrize('patch',['def forward(data): return data\nVALUE=2','def forward(other): return other','def other(data): return data'])
def test_scope_and_interface_changes_rejected(patch):
 with pytest.raises(ScopeError):replace_function(S,packet(),patch)
def test_guessed_paths_and_symbols_rejected():
 with pytest.raises(ScopeError,match='PATH_NOT_ALLOWED'):build_handoff({'exporter.py':S},'unknown.py','forward',{'exporter.py'},['exporter.py'],'x',[])
 with pytest.raises(ScopeError,match='FUNCTION_NOT_FOUND'):build_handoff({'exporter.py':S},'exporter.py','missing',{'exporter.py'},['exporter.py'],'x',[])

def test_full_module_response_accepts_only_unchanged_surroundings():
 proposed=S.replace('return data', 'return dict(data)')
 assert replace_function(S,packet(),proposed)==proposed
 with pytest.raises(ScopeError,match='OUTSIDE_FUNCTION_SCOPE'):
  replace_function(S,packet(),proposed.replace('VALUE = 1','VALUE = 2'))
 with pytest.raises(ScopeError,match='OUTSIDE_FUNCTION_SCOPE'):
  replace_function(S,packet(),proposed+'\nimport os\n')
