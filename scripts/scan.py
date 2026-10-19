"""Read-only Java/Python scanning. Never execute a repository's build scripts or code."""
import argparse, hashlib, json, os, re, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def mask(code):
    code=re.sub(r'""".*?"""|\x27\x27\x27.*?\x27\x27\x27', '"[REDACTED]"',code,flags=re.S)
    code=re.sub(r'/\*.*?\*/','/* REDACTED */',code,flags=re.S)
    code=re.sub(r'//[^\r\n]*','// REDACTED',code)
    code=re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '"[REDACTED]"',code)
    return re.sub(r'#[^\r\n]*', '# REDACTED', code)
def snapshot(source,dest):
    total=0
    for p in source.rglob('*'):
        if p.suffix not in {'.java','.py'} or not p.is_file():continue
        rel=p.relative_to(source)
        if any(x in {'.git','node_modules','target','fixtures','.venv','venv','.scanner-venv','.runtime','__pycache__','dist'} for x in rel.parts):continue
        if p.is_symlink() or any(x.is_symlink() for x in p.parents if x!=source.parent): raise ValueError('Symlinks are prohibited')
        if not p.resolve().is_relative_to(source.resolve()):raise ValueError('Path escape')
        if p.stat().st_size>1_000_000:raise ValueError('File size limit')
        total+=p.stat().st_size
        if total>20_000_000:raise ValueError('Snapshot size limit')
        if not re.fullmatch(r'[A-Za-z0-9_./$-]+\.(java|py)',str(rel)):raise ValueError('Unsupported path')
        target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());target.chmod(0o444)
    if not total:raise ValueError('No Java/Python sources to analyze')
def scan(source):
    with tempfile.TemporaryDirectory(prefix='csi-readonly-') as tmp:
        base=Path(tmp);snapshot(Path(source).resolve(),base)
        env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR','SEMGREP_LOG_FILE','SEMGREP_SETTINGS_FILE') if k in os.environ}
        env.update(SEMGREP_SEND_METRICS='off',SEMGREP_ENABLE_VERSION_CHECK='0')
        run=subprocess.run([os.environ.get('SEMGREP_BIN','semgrep'),'scan','--config',str(ROOT/'rules/java-security.yml'),'--config',str(ROOT/'rules/python-security.yml'),'--json','--metrics=off','--disable-version-check','--timeout','10','--max-memory','512','--max-target-bytes','1000000','--no-git-ignore','.'],cwd=base,env=env,capture_output=True,text=True,timeout=90)
        if run.returncode:raise RuntimeError('Semgrep execution failed; result not submitted')
        data=json.loads(run.stdout)
        if data.get('errors'):raise RuntimeError('Semgrep reported incomplete analysis')
        findings=[];occurrences={}
        for item in data['results']:
            rule=item['check_id'].split('.')[-1];path=Path(item['path']);start=item['start']['line'];end=item['end']['line']
            if path.is_absolute() or '..' in path.parts:raise ValueError('Invalid result path')
            code=mask('\n'.join((base/path).read_text().splitlines()[start-1:end]))
            base_fp=rule+'|'+str(path)+'|'+re.sub(r'\s+','',code);number=occurrences.get(base_fp,0);occurrences[base_fp]=number+1
            fp=hashlib.sha256(f'{base_fp}|{number}'.encode()).hexdigest()
            findings.append(dict(findingId=fp[:24],ruleId=rule,category='POLICY_DRIFT' if rule=='POL-01' else 'SECURITY',severity={'SEC-01':'HIGH','SEC-02':'HIGH','SEC-03':'MEDIUM','SEC-04':'MEDIUM','SEC-05':'HIGH','POL-01':'LOW'}[rule],filePath=str(path),startLine=start,endLine=end,maskedCodeEvidence=code,fingerprint=fp,confidence='MEDIUM',evidenceStatus='INSUFFICIENT_EVIDENCE' if rule=='POL-01' else 'SUSPECTED'))
        return findings
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--output',required=True);args=p.parse_args()
    results=scan(args.source);Path(args.output).write_text(json.dumps(results,ensure_ascii=False));print(f'Semgrep completed: {len(results)} masked findings')
