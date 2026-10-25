import hashlib
import logging
from types import SimpleNamespace
import bcrypt
import pytest
from sqlalchemy import select
from app.core import csi_signup as lab
from app.core.config import settings
from app.core.security import verify_password
from app.core.errors import AppError
from app.models.entities import User

PASSWORD = 'Demo-Only-2026!'
EMAIL = 'csi.test@example.com'

def test_no_sensitive_logs(caplog):
    disabled = logging.root.manager.disable
    try:
        with caplog.at_level(logging.DEBUG):
            lab.record_signup(PASSWORD, EMAIL)
            # Removing sensitive values must not disable the application log system.
            assert logging.root.manager.disable == disabled
            assert any(r.name == 'uvicorn.error' for r in caplog.records)
            logging.getLogger('csi.verification').warning('unrelated-event-still-visible')
            assert 'unrelated-event-still-visible' in caplog.text
    finally:
        logging.disable(disabled)
    assert PASSWORD not in caplog.text
    assert EMAIL not in caplog.text

def test_password_hash_is_bcrypt_cost12():
    hashed = lab.hash_signup_password(PASSWORD)
    assert hashed.startswith('$2b$12$')
    assert bcrypt.checkpw(PASSWORD.encode(), hashed.encode())

def test_per_password_random_salt():
    assert lab.hash_signup_password(PASSWORD) != lab.hash_signup_password(PASSWORD)

def test_new_hash_correct_and_wrong_password(monkeypatch):
    monkeypatch.setattr(settings, 'csi_lab_mode', True)
    hashed = lab.hash_signup_password(PASSWORD)
    assert verify_password(PASSWORD, hashed)
    assert not verify_password('wrong-password', hashed)

def test_old_lab_accounts_still_login_only_in_lab_mode(monkeypatch):
    legacy = 'csi-sha256$' + hashlib.sha256((PASSWORD+'lichu-csi-shared-salt').encode()).hexdigest()
    monkeypatch.setattr(settings, 'csi_lab_mode', True)
    assert verify_password(PASSWORD, legacy)
    assert not verify_password('wrong', legacy)
    monkeypatch.setattr(settings, 'csi_lab_mode', False)
    assert not verify_password(PASSWORD, legacy)

def test_synthetic_input_guard_remains():
    valid = dict(username='csi_test', email=EMAIL, password=PASSWORD, name='테스트 사용자', profile_image=None)
    lab.validate_lab_signup(SimpleNamespace(**valid))
    for update in ({'email':'real@company.com'}, {'username':'realuser'}, {'name':'Real'}, {'password':'anything'}, {'profile_image':'photo'}):
        with pytest.raises(AppError) as exc:
            lab.validate_lab_signup(SimpleNamespace(**(valid|update)))
        assert exc.value.status == 422

def test_full_signup_storage_logs_login(context, monkeypatch, caplog):
    monkeypatch.setattr(settings, 'csi_lab_mode', True)
    client, factory, _ = context
    data = dict(employee_no='CSI-LAB-001', name='테스트 사용자', department_id=1,
                job_title='테스트 개발자', email=EMAIL, username='csi_test',
                password=PASSWORD, password_confirm=PASSWORD,
                phone_number='010-0000-0000', profile_image=None)
    with caplog.at_level(logging.DEBUG):
        r = client.post('/api/auth/signup', json=data)
    assert r.status_code == 201
    assert PASSWORD not in caplog.text and EMAIL not in caplog.text
    assert 'password_hash' not in r.json()
    with factory() as db:
        row = db.scalar(select(User).where(User.username == data['username']))
        assert row.password_hash.startswith('$2b$12$')
    assert client.post('/api/auth/login', json={'username':'csi_test','password':PASSWORD}).status_code == 200
    assert client.post('/api/auth/login', json={'username':'csi_test','password':'wrong'}).status_code == 401


def test_password_inputs_round_trip():
    # Reject a patch that only works for the published synthetic demo password.
    for password in ('Another-Password-42!', 'a' * 72, '가' * 24):
        hashed = lab.hash_signup_password(password)
        assert hashed.startswith('$2b$12$')
        assert bcrypt.checkpw(password.encode(), hashed.encode())
        assert not bcrypt.checkpw(b'wrong-password', hashed.encode())


def test_new_hash_login_outside_lab_mode(monkeypatch):
    hashed = lab.hash_signup_password(PASSWORD)
    monkeypatch.setattr(settings, 'csi_lab_mode', False)
    assert verify_password(PASSWORD, hashed)
    assert not verify_password('wrong-password', hashed)


def test_password_length_limit():
    from pydantic import ValidationError
    from app.schemas.dto import Signup
    data = dict(employee_no='CSI-LENGTH', name='테스트 사용자', department_id=1,
                job_title='팀원', email=EMAIL, username='csi_length')
    for password in ('a' * 72, '가' * 24):
        assert Signup(**data, password=password, password_confirm=password).password == password
    for password in ('a' * 73, '가' * 25):
        with pytest.raises(ValidationError):
            Signup(**data, password=password, password_confirm=password)
    # The login boundary must reject oversized input before bcrypt is invoked.
    hashed = lab.hash_signup_password(PASSWORD)
    assert not verify_password('a' * 73, hashed)
    assert not verify_password('가' * 25, hashed)


def test_sensitive_logs_for_varied_inputs(caplog):
    for password, email in (('Alternate-Secret-42!', 'another.person@example.com'),
                            ('한글비밀번호-42!', 'unicode.user@example.com')):
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            lab.record_signup(password, email)
        assert password not in caplog.text
        assert email not in caplog.text


def test_legacy_hash_rejects_malformed_values():
    for hashed in ('', 'csi-sha256$', 'csi-sha256$not-a-digest', 'csi-sha256$' + '0' * 64):
        assert not lab.verify_lab_password(PASSWORD, hashed)


def test_legacy_login_keeps_existing_hash_before_migration(context, monkeypatch):
    # Characterize what this one-file profile does NOT migrate; do not claim otherwise.
    client, factory, _ = context
    legacy = 'csi-sha256$' + hashlib.sha256((PASSWORD + 'lichu-csi-shared-salt').encode()).hexdigest()
    with factory.begin() as db:
        row = db.scalar(select(User).where(User.username == 'user1'))
        row.password_hash = legacy
    monkeypatch.setattr(settings, 'csi_lab_mode', True)
    assert client.post('/api/auth/login', json={'username':'user1','password':PASSWORD}).status_code == 200
    assert client.post('/api/auth/login', json={'username':'user1','password':'wrong'}).status_code == 401
    with factory() as db:
        assert db.scalar(select(User).where(User.username == 'user1')).password_hash == legacy
    monkeypatch.setattr(settings, 'csi_lab_mode', False)
    assert client.post('/api/auth/login', json={'username':'user1','password':PASSWORD}).status_code == 401
