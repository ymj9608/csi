export interface ReviewChange {
  id: string;
  title: string;
  before: string;
  after: string;
  status: 'VERIFIED' | 'NOT_VERIFIED';
  tests: string[];
  evidenceIds?: string[];
}

export interface CodingReview {
  version: 1;
  summary: string;
  changes: ReviewChange[];
  remainingRisks: { id: string; title: string; detail: string; nextStep: string }[];
  scope: string[];
}

const strings = (values: unknown): values is string[] => Array.isArray(values) && values.every(value => typeof value === 'string');
const legacySecurityTotal = 7;

export function readReview(value: any): CodingReview | undefined {
  if (value?.version !== 1 || typeof value.summary !== 'string' || !strings(value.scope)) return;
  if (!Array.isArray(value.changes) || !value.changes.every((change: any) =>
    ['id', 'title', 'before', 'after'].every(key => typeof change?.[key] === 'string') &&
    ['VERIFIED', 'NOT_VERIFIED'].includes(change.status) && strings(change.tests) &&
    (change.evidenceIds == null || strings(change.evidenceIds)))) return;
  if (!Array.isArray(value.remainingRisks) || !value.remainingRisks.every((risk: any) =>
    ['id', 'title', 'detail', 'nextStep'].every(key => typeof risk?.[key] === 'string'))) return;
  return value;
}

export function securityCount(verification: any): string {
  if (!Number.isInteger(verification?.securityPassed)) return '미실행';
  const total = Number.isInteger(verification.securityTotal) && verification.securityTotal > 0
    ? verification.securityTotal
    // Results saved before versioned verification used the seven-check lab suite.
    : verification.suiteVersion == null ? legacySecurityTotal : undefined;
  return total == null ? `${verification.securityPassed}개 통과 · 전체 수 미확인` : `${verification.securityPassed} / ${total}`;
}

export function previousVerificationPassed(result: any): boolean {
  const verification = result?.verification;
  return verification?.suiteVersion == null && verification?.securityTotal == null &&
    verification?.failed === 0 && verification?.securityPassed === legacySecurityTotal &&
    (verification?.exitCode == null || verification.exitCode === 0);
}

export function finalVerificationPassed(result: any, status: string): boolean {
  const verification = result?.verification;
  if (!['READY', 'APPROVED', 'REJECTED'].includes(status) || verification?.suiteVersion !== 2 ||
    verification.exitCode !== 0 || verification.failed !== 0 || !Number.isInteger(verification.securityTotal) ||
    verification.securityTotal <= 0 || verification.securityPassed !== verification.securityTotal) return false;
  const checks = verification.securityChecks;
  return Array.isArray(checks) && checks.length === verification.securityTotal &&
    new Set(checks.map((check: any) => check?.id)).size === checks.length &&
    checks.every((check: any) => typeof check?.id === 'string' && check.status === 'PASSED');
}

export function changeVerified(change: ReviewChange, result: any, status: string): boolean {
  if (!finalVerificationPassed(result, status) || change.status !== 'VERIFIED' || !change.tests.length) return false;
  return change.tests.every(id => result.verification.securityChecks.some((check: any) => check.id === id && check.status === 'PASSED'));
}
