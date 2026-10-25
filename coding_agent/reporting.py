"""Explain observed test results without treating model prose as proof."""
from .verification.contract import complete_security_report

# User-facing facts are owned by the verifier, never supplied by model output.
SCOPE = [
    'Lichu 회원가입 실습 경로와 그 로그인 호출 경로를 격리 환경에서 검증했습니다.',
    'SQLite 테스트 결과입니다. PostgreSQL 동시성·배포 환경은 검증하지 않았습니다.',
    '수정안 검증 결과이며 원본 코드 반영·배포 또는 전체 정책·법률 준수를 보증하지 않습니다.',
]
CHANGES = (
    ('password-storage', '신규 비밀번호 저장',
     ('test_password_hash_is_bcrypt_cost12', 'test_per_password_random_salt', 'test_password_inputs_round_trip'),
     'bcrypt 비용 계수 12·개별 Salt·다양한 입력 검증을 통과하지 못했습니다.',
     'bcrypt 비용 계수 12와 매번 다른 Salt를 확인했습니다. 영문·한글·72바이트 입력도 검증했습니다.'),
    ('sensitive-logs', '회원가입 민감정보 로그',
     ('test_no_sensitive_logs', 'test_sensitive_logs_for_varied_inputs'),
     '검증 입력의 원문 비밀번호와 이메일이 로그에 남았습니다.',
     '해당 로그 경로에서 여러 검증 입력의 원문 비밀번호와 이메일이 남지 않았습니다.'),
    ('new-login', '신규 계정 로그인',
     ('test_new_hash_correct_and_wrong_password', 'test_new_hash_login_outside_lab_mode', 'test_full_signup_storage_logs_login'),
     '실습 모드 밖에서 신규 해시 인증과 bcrypt 회원가입 통합 검증을 통과하지 못했습니다.',
     '회원가입 → DB 저장 → 로그인에 성공하고 잘못된 비밀번호는 거절됐습니다. 신규 bcrypt 해시는 실습 모드 밖에서도 검증됩니다.'),
    ('legacy-login', '기존 계정 호환성',
     ('test_old_lab_accounts_still_login_only_in_lab_mode', 'test_legacy_hash_rejects_malformed_values',
      'test_legacy_login_keeps_existing_hash_before_migration'),
     '기존 SHA-256 계정은 실습 모드에서 인증됩니다.',
     '기존 SHA-256 계정의 실습 모드 로그인은 유지됩니다. 로그인 후 DB 해시가 자동 전환되지 않는 것도 확인했습니다.'),
    ('input-guards', '입력 제한 유지',
     ('test_synthetic_input_guard_remains', 'test_password_length_limit'),
     '합성 계정 제한과 UTF-8 72바이트 입력 제한이 있습니다.',
     '기존 합성 데이터 제한과 72바이트 입력 제한을 유지했습니다.'),
)
REMAINING = [
    {'id':'legacy-hashes','title':'기존 계정의 약한 해시',
     'detail':'이 수정안은 기존 DB 해시를 bcrypt로 전환하지 않습니다.',
     'nextStep':'로그인 성공 후 재해시·저장 또는 비밀번호 재설정 절차가 별도로 필요합니다.'},
    {'id':'historical-logs','title':'이미 저장된 민감정보 로그',
     'detail':'새 로그 출력을 보완해도 과거 파일·로그 서비스·백업의 기록은 없어지지 않습니다.',
     'nextStep':'로그 보관 위치와 보존 정책을 확인하고 승인된 범위에서 마스킹·정리를 진행해야 합니다.'},
    {'id':'deployment','title':'실제 반영 및 운영 환경',
     'detail':'격리된 수정안만 테스트했습니다. 원본 반영 여부와 운영 DB 동작은 별도 확인 대상입니다.',
     'nextStep':'관리자 검토 후 코드 반영, 재검사 및 배포 환경 검증이 필요합니다.'},
]


def build_review(baseline, verification, findings=(), references=()):
    def statuses(report):
        if not complete_security_report(report or {}):
            return {}
        return {c['id']:c['status'] for c in report['securityChecks']}
    before, after = statuses(baseline), statuses(verification)
    changes = []
    for key, title, tests, old_text, new_text in CHANGES:
        verified = all(after.get(test) == 'PASSED' for test in tests)
        baseline_known = all(before.get(test) in {'PASSED','FAILED'} for test in tests)
        if key in {'password-storage','sensitive-logs','new-login'} and all(before.get(test) == 'PASSED' for test in tests):
            old_text = '수정 전에도 해당 항목의 검증을 통과했습니다.'
        rules, sections = ({'SEC-05'}, {'POL-05','REF-06'}) if key == 'sensitive-logs' else (
            (set(),set()) if key == 'input-guards' else ({'SEC-02','SEC-03'}, {'POL-04','REF-04','REF-05'}))
        evidence = {f['id'] for f in findings if f['ruleId'] in rules}
        evidence.update(r['chunkId'] for r in references if r['sectionId'].split('.')[0] in sections)
        changes.append({'id':key,'title':title,'tests':list(tests),'evidenceIds':sorted(evidence),
                        'status':'VERIFIED' if verified else 'NOT_VERIFIED',
                        'before':old_text if baseline_known else '해당 항목의 수정 전 검증 자료가 없습니다.',
                        'after':new_text if verified else '해당 항목의 모든 검증을 통과하지 못해 개선 완료로 판단할 수 없습니다.'})
    verified_count = sum(c['status'] == 'VERIFIED' for c in changes)
    return {'version':1,
            'summary':f'검증 항목 {len(changes)}개 중 {verified_count}개를 확인했습니다. 기존 해시 전환과 과거 로그 정리는 포함하지 않습니다.',
            'changes':changes,'remainingRisks':[dict(r) for r in REMAINING],'scope':list(SCOPE)}
