import { test, expect } from '@playwright/test';

for (const scenario of [
  { status: 'QUEUED', title: '분석 대기', red: '', blue: '' },
  { status: 'RUNNING', title: '분석 진행 중', red: '', blue: '' },
  { status: 'FAILED', title: '분석 실패 · 작업 종료', red: '', blue: '' },
  { status: 'FAILED', title: '분석 실패 · 작업 종료', red: '저장된 일부 위험 분석', blue: '' },
  { status: 'COMPLETED', title: '검사 완료 · 분석 결과 누락', red: '  ', blue: '' },
  { status: 'COMPLETED', title: '분석 완료', red: '저장된 위험 분석', blue: '저장된 근거 검토' },
  { status: 'UNKNOWN', title: '분석 상태 확인 필요', red: '', blue: '' },
]) {
  test(`${scenario.status} / ${scenario.red || 'empty'} explains analysis and generation availability`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    let status = scenario.status;
    let requests = 0;
    const finding = { id: 'finding', scanId: 'scan', repository: 'ymj9608/Lichu', ruleId: 'SEC-02', status: 'OPEN', severity: 'HIGH', filePath: 'backend/app/core/csi_signup.py', analysis: { red: scenario.red, blue: scenario.blue } };
    await page.route('**/api/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      if (path.endsWith('/stream')) return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' });
      let value: any = {};
      if (path === '/api/auth/me') value = { username: 'test', role: 'SECURITY_REVIEWER' };
      else if (path === '/api/auth/csrf') value = { token: 'mock' };
      else if (path === '/api/findings/finding') value = finding;
      else if (path === '/api/scans/scan') value = { id: 'scan', status };
      else if (path === '/api/scans/scan/findings') value = [finding];
      else if (path === '/api/scans/scan/coding-proposals') {
        if (request.method() === 'POST') requests++;
        value = { enabled: true, supported: true, items: [] };
      }
      await route.fulfill({ json: value });
    });
    await page.goto('/findings/finding');
    const notice = page.getByRole('status', { name: '분석 상태' });
    await expect(notice).toContainText(scenario.title);
    await expect(page.getByText('분석 결과 대기 중', { exact: true })).toHaveCount(0);
    if (scenario.red.trim()) await expect(page.locator('.verdict.red .report-text > [aria-hidden="true"]')).toHaveText(scenario.red);
    else await expect(page.locator('.verdict.red')).toHaveCount(0);
    if (scenario.status === 'FAILED') await expect(notice).toContainText('기다려도 결과가 추가되지 않습니다');
    await expect(notice.getByRole('link')).toHaveAttribute('href', '/scans/scan');
    await page.getByRole('tab', { name: '수정안 생성·검토', exact: true }).click();
    const region = page.getByRole('region', { name: '코딩 Agent 수정안' });
    const button = region.getByRole('button', { name: '수정안 생성 요청', exact: true });
    await expect(button).toBeVisible();
    if (status === 'COMPLETED') await expect(button).toBeEnabled();
    else {
      await expect(button).toBeDisabled();
      await expect(region.getByRole('link', { name: '검사 상세·실행 기록 확인' })).toHaveAttribute('href', '/scans/scan');
      if (status === 'FAILED') await expect(region).toContainText('이 검사에서는 수정안을 생성할 수 없습니다');
    }
    expect(requests).toBe(0);
    if (status === 'RUNNING') {
      status = 'COMPLETED';
      finding.analysis = { red: '완료된 위험 분석', blue: '완료된 근거 검토' };
      await page.getByRole('button', { name: '새로고침', exact: true }).click();
      await expect(button).toBeEnabled();
      await page.getByRole('tab', { name: 'AI 분석', exact: true }).click();
      await expect(notice).toContainText('분석 완료');
      await expect(page.locator('.verdict.red .report-text > [aria-hidden="true"]')).toHaveText('완료된 위험 분석');
    }
  });
}
