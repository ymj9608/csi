"""Local service runner: inject secrets from ignored .env without printing or shell expansion."""
import os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for line in (root/'.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1);os.environ.setdefault(k,v)
os.environ['MCP_HOST']='127.0.0.1'
os.environ['DEBUG']='false'
os.chdir(root)
cmd=sys.argv[1:]
if not cmd:raise SystemExit('Usage: service.py executable arguments...')
os.execvp(cmd[0],cmd)
