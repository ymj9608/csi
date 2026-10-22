"""Trusted test identities shared by the host and the isolated verifier."""
SUITE_VERSION = 2
SECURITY_TESTS = (
    'test_no_sensitive_logs',
    'test_password_hash_is_bcrypt_cost12',
    'test_per_password_random_salt',
    'test_new_hash_correct_and_wrong_password',
    'test_old_lab_accounts_still_login_only_in_lab_mode',
    'test_synthetic_input_guard_remains',
    'test_full_signup_storage_logs_login',
    'test_password_inputs_round_trip',
    'test_new_hash_login_outside_lab_mode',
    'test_password_length_limit',
    'test_sensitive_logs_for_varied_inputs',
    'test_legacy_hash_rejects_malformed_values',
    'test_legacy_login_keeps_existing_hash_before_migration',
)
BASELINE_FAILURES = {
    'test_no_sensitive_logs', 'test_password_hash_is_bcrypt_cost12',
    'test_per_password_random_salt', 'test_full_signup_storage_logs_login',
    'test_password_inputs_round_trip', 'test_new_hash_login_outside_lab_mode',
    'test_sensitive_logs_for_varied_inputs',
}


def complete_security_report(report):
    checks = report.get('securityChecks')
    if not isinstance(checks, list) or len(checks) != len(SECURITY_TESTS):
        return False
    if any(not isinstance(c, dict) or c.get('status') not in {'PASSED', 'FAILED', 'SKIPPED'} for c in checks):
        return False
    return (report.get('suiteVersion') == SUITE_VERSION
            and report.get('securityTotal') == len(SECURITY_TESTS)
            and {c.get('id') for c in checks} == set(SECURITY_TESTS)
            and report.get('securityPassed') == sum(c['status'] == 'PASSED' for c in checks))
