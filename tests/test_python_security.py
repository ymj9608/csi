from pathlib import Path
import os
import pytest
from scan import scan, mask, snapshot
from agent.csi_agent.analysis import base_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.scanner
def test_python_password_rules_and_safe_negative_cases(tmp_path, monkeypatch):
    monkeypatch.setenv('SEMGREP_BIN', str(ROOT / '.scanner-venv/bin/semgrep'))
    monkeypatch.setenv('SEMGREP_LOG_FILE', str(tmp_path / 'semgrep.log'))
    monkeypatch.setenv('SEMGREP_SETTINGS_FILE', str(tmp_path / 'semgrep.yml'))
    if Path('/etc/ssl/cert.pem').exists():monkeypatch.setenv('SSL_CERT_FILE','/etc/ssl/cert.pem')
    source = tmp_path / 'project';source.mkdir()
    file = source / 'signup.py'
    file.write_text('''import hashlib, bcrypt
class Signup(BaseModel):
    phone_number: str
def register(password, user):
    user.password_hash = password
    digest = hashlib.sha256(password.encode()).hexdigest()
    salt = "synthetic-fixed-salt"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10))
    log.info("password=%s", password)
''')
    findings = scan(source)
    assert {f['ruleId'] for f in findings} == {'SEC-01','SEC-02','SEC-03','SEC-04','SEC-05','POL-01'}
    assert all('synthetic-fixed-salt' not in f['maskedCodeEvidence'] for f in findings)
    file.write_text('''import hashlib, bcrypt
def register(password, user, file_bytes):
    user.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    checksum = hashlib.sha256(file_bytes).hexdigest()
    log.info("signup completed")
''')
    assert scan(source) == []


def test_python_literals_comments_and_triple_strings_are_masked():
    code = 'log.info("""private@example.com\nsecret second line""", password) # token=private\n'
    result = mask(code)
    assert all(value not in result for value in ('private@example.com', 'secret second line', 'token=private'))
    assert 'password' in result


def test_virtualenv_sources_are_not_analyzed(tmp_path):
    source = tmp_path / 'project';source.mkdir()
    (source / 'main.py').write_text('print("example")')
    (source / '.venv').mkdir();(source / '.venv' / 'private.py').write_text('private')
    dest = tmp_path / 'copy';dest.mkdir()
    snapshot(source,dest)
    assert list(dest.iterdir()) == [dest / 'main.py']


def test_python_findings_receive_python_remediation_example():
    report = base_report([{'id':'test','ruleId':'SEC-02','filePath':'backend/account.py'}], {}, {'version':'v1'})
    assert 'bcrypt.gensalt(rounds=12)' in report[0]['analysis']['example']
    assert 'PasswordEncoder' not in report[0]['analysis']['example']
