"""Read two immutable Git trees. Never checkout or execute target code or Git filters."""
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from itertools import zip_longest
from scan import scan

SHA = re.compile(r'[0-9a-f]{40}')
PATH = re.compile(r'[A-Za-z0-9_./$-]+\.(java|py)')
EXCLUDED = {'.git', 'node_modules', 'target', 'fixtures', '.venv', 'venv', '.runtime', '__pycache__', 'dist', '.scanner-venv'}
MAX_FILES, MAX_ROWS = 20, 100


def git(repo, *args):
    return subprocess.run(['git', '--no-pager', '-C', str(repo), *args], check=True,
                          capture_output=True, timeout=30).stdout


def mask_lines(source, suffix):
    """Mask whole literals/comments before slicing hunks, preserving physical line numbers."""
    out=[];i=0
    while i < len(source):
        start=i;end=None
        if source.startswith(('"""', "'''"), i):
            quote=source[i:i+3];j=i+3
            while j<len(source):
                if source[j]=='\\':j+=2;continue
                if source.startswith(quote,j):j+=3;break
                j+=1
            end=min(j,len(source))
        elif source[i] in {'"', "'"}:
            quote=source[i];j=i+1
            while j<len(source):
                if source[j]=='\\':j+=2;continue
                if source[j]==quote:j+=1;break
                j+=1
            end=min(j,len(source))
        elif suffix=='.py' and source[i]=='#' or suffix=='.java' and source.startswith('//',i):
            j=source.find('\n',i);end=len(source) if j<0 else j
        elif suffix=='.java' and source.startswith('/*',i):
            j=source.find('*/',i+2);end=len(source) if j<0 else j+2
        if end is not None:
            out.append('\n'.join('[REDACTED]' for _ in source[start:end].split('\n')));i=end
        else:out.append(source[i]);i+=1
    # Long numeric literals can be personal identifiers; preserve only short code constants.
    return re.sub(r'\b\d{7,}\b','[REDACTED_NUMBER]',''.join(out)).splitlines()


def tree(repo, sha, dest):
    if not SHA.fullmatch(sha):raise ValueError('Full commit SHA required')
    git(repo,'cat-file','-e',sha+'^{commit}')
    files={};total=0
    for entry in git(repo,'ls-tree','-rz','--full-tree',sha).split(b'\0'):
        if not entry:continue
        meta, rawpath=entry.split(b'\t',1);mode,kind,oid=meta.split()
        path=rawpath.decode('utf-8',errors='replace')
        p=Path(path)
        if not PATH.fullmatch(path) or '..' in path or EXCLUDED.intersection(p.parts):continue
        if mode not in {b'100644',b'100755'} or kind!=b'blob':continue
        size=int(git(repo,'cat-file','-s',oid.decode()).strip())
        total+=size
        if size>1_000_000 or total>20_000_000 or len(files)>=2000:raise ValueError('Snapshot limit exceeded')
        content=git(repo,'cat-file','blob',oid.decode()).decode('utf-8')
        if '\x00' in content:raise ValueError('Binary source not supported')
        target=dest/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
        files[path]=content
    return files


def symbols(source, suffix):
    if suffix!='.py':return {}
    try:root=ast.parse(source)
    except SyntaxError:return {}
    found={}
    for node in ast.walk(root):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}',node.name):
            found[('FUNCTION',node.name)]=node.lineno
        if isinstance(node,ast.ClassDef) and node.name in {'Signup','ProfileUpdate','User','CsiSignupProfile'}:
            for child in node.body:
                if isinstance(child,ast.AnnAssign) and isinstance(child.target,ast.Name) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}',child.target.id):
                    found[('FIELD',node.name+'.'+child.target.id)]=child.lineno
    return found


def changed_file(path, before, after):
    suffix=Path(path).suffix;old=before.splitlines();new=after.splitlines()
    old_mask=mask_lines(before,suffix);new_mask=mask_lines(after,suffix)
    change_id=hashlib.sha256(path.encode()).hexdigest()[:24]
    rows=[];added=removed=0
    matcher=difflib.SequenceMatcher(None,old,new,autojunk=False)
    for group in matcher.get_grouped_opcodes(2):
        for tag,a,b,c,d in group:
            if tag!='equal':removed+=b-a;added+=d-c
            for i,j in zip_longest(range(a,b),range(c,d)):
                rows.append({'oldLine':None if i is None else i+1,'newLine':None if j is None else j+1,
                    'before':None if i is None else old_mask[i][:400], 'after':None if j is None else new_mask[j][:400],
                    'kind':'CONTEXT' if tag=='equal' else 'ADDED' if i is None else 'DELETED' if j is None else 'MODIFIED'})
    left=symbols(before,suffix);right=symbols(after,suffix);facts=[]
    for state,original,other in [('ADDED',right,left),('REMOVED',left,right)]:
        for key in sorted(original.keys()-other.keys()):
            facts.append({'id':f'{change_id}:{len(facts)+1}','kind':key[0]+'_'+state,'symbol':key[1],'line':original[key]})
    return {'changeId':change_id,'filePath':path,'changeType':'MODIFIED', 'addedLines':added,'removedLines':removed,
            'rows':rows[:MAX_ROWS], 'facts':facts[:20],
            'truncated':len(rows)>MAX_ROWS or len(facts)>20 or any(len(s)>400 for s in old_mask+new_mask)}


def collect(repo, head, base=None):
    if not SHA.fullmatch(head):raise ValueError('Full head SHA required')
    with tempfile.TemporaryDirectory(prefix='csi-git-head-') as head_dir, tempfile.TemporaryDirectory(prefix='csi-git-base-') as base_dir:
        after=tree(repo,head,Path(head_dir));current=scan(Path(head_dir)) if after else []
        result={'findings':current,'changeSet':{'schemaVersion':1,'headSha':head,'baseSha':None,
                'status':'NO_BASE','files':[],'baselineFindings':[], 'totalChangedFiles':0,'truncated':False}}
        changes=result['changeSet']
        if not base or base=='0'*40:return result
        if not SHA.fullmatch(base):raise ValueError('Full base SHA required')
        changes['baseSha']=base
        try:git(repo,'cat-file','-e',base+'^{commit}')
        except subprocess.CalledProcessError:
            changes['status']='BASE_UNAVAILABLE';return result
        before=tree(repo,base,Path(base_dir));baseline=scan(Path(base_dir)) if before else []
        if max(len(current),len(baseline))>300:raise ValueError('Finding limit exceeded')
        paths=sorted(p for p in before.keys()|after.keys() if before.get(p)!=after.get(p))
        files=[]
        for path in paths[:MAX_FILES]:
            f=changed_file(path,before.get(path,''),after.get(path,''))
            f['changeType']='ADDED' if path not in before else 'DELETED' if path not in after else 'MODIFIED'
            files.append(f)
        changes.update(status='AVAILABLE',files=files,totalChangedFiles=len(paths),
                       baselineFindings=[{k:f[k] for k in ['ruleId','filePath','startLine','endLine','fingerprint']} for f in baseline],
                       truncated=len(paths)>MAX_FILES or any(f['truncated'] for f in files))
        if len(json.dumps(result,ensure_ascii=False).encode())>950_000:raise ValueError('Payload limit exceeded')
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('repository',type=Path);p.add_argument('--head',default=os.environ.get('GITHUB_SHA'))
    p.add_argument('--base',default=os.environ.get('CSI_BASE_SHA'));p.add_argument('--output',required=True);args=p.parse_args()
    if not args.head:p.error('--head or GITHUB_SHA is required')
    # For manual runs only, use the head parent. Never silently replace a missing Push base.
    base=args.base
    if not base and os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch':
        try:base=git(args.repository,'rev-parse',args.head+'^').decode().strip()
        except subprocess.CalledProcessError:pass
    payload=collect(args.repository,args.head,base)
    Path(args.output).write_text(json.dumps(payload,ensure_ascii=False))
    print(json.dumps({'findings':len(payload['findings']),'changeStatus':payload['changeSet']['status'],'changedFiles':payload['changeSet']['totalChangedFiles']}))
