"""Finish independent baseline after Qwen handoff failure; no substituted handoff."""
from benchmark_signup_events_local import OUT,LocalClient,CODER
from benchmark_signup_events import FIX,EDIT,TASK,SYSTEM,obj,TEXT
from benchmark_signup_micro import write,verify
import difflib
sources={p.name:p.read_text() for p in FIX.iterdir() if p.name!='test_contract.py'}
a=LocalClient(OUT,{}).call('code_only','ollama',CODER,SYSTEM,{'task':TASK,'sources':sources,'handoff':None},obj({**{n:TEXT for n in EDIT},'risk':TEXT}))
f=OUT/'code_only';f.mkdir()
for p in FIX.iterdir():(f/p.name).write_bytes(p.read_bytes())
for n in EDIT:(f/n).write_text(a[n])
(f/'risk.txt').write_text(a['risk'])
(f/'candidate.patch').write_text(''.join(''.join(difflib.unified_diff(sources[n].splitlines(True),a[n].splitlines(True),fromfile='a/'+n,tofile='b/'+n)) for n in EDIT))
v=verify(f);write(f/'validation.json',v);print(v)
