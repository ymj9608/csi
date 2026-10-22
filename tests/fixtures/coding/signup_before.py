"""Intentionally vulnerable signup baseline for an isolated CSI lab database.

Called only when CSI_LAB_MODE=true. This file is source evidence, not a mock finding.
Apply docs/csi/signup-remediation.patch to demonstrate code-based remediation.
"""
import hashlib
import hmac
import logging
from app.core.errors import AppError

log = logging.getLogger('uvicorn.error')


def validate_lab_signup(payload):
    if not (payload.username.startswith('csi_') and payload.email.endswith('@example.com')
            and payload.password == 'Demo-Only-2026!' and payload.name.startswith('테스트')):
        raise AppError(422, 'SYNTHETIC_ONLY', 'CSI 실습은 테스트 데이터 채우기로 생성한 합성 계정만 허용합니다.')
    if payload.profile_image:
        raise AppError(422, 'SYNTHETIC_ONLY', 'CSI 실습에서는 실제 프로필 사진을 수집하지 않습니다.')


def hash_signup_password(password: str) -> str:
    # BEFORE FIX: globally shared salt and a fast digest instead of a password KDF.
    salt = 'lichu-csi-shared-salt'
    password = password + salt
    return 'csi-sha256$' + hashlib.sha256(password.encode()).hexdigest()


def verify_lab_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_signup_password(password), hashed)


def record_signup(password: str, email: str):
    # BEFORE FIX: only server-validated synthetic data reaches these deliberate leaks.
    log.info('CSI lab signup password=%s', password)
    log.info('CSI lab signup email=%s', email)


def lab_version() -> str:
    return 'before-fix'
