import {test, expect} from '@playwright/test';

for (const errorCode of ['MODEL_TIMEOUT', 'WORKER_TIMEOUT']) {
  test(`${errorCode} stops polling and retries the saved image`, async ({page}) => {
    const project = '11111111-1111-4111-8111-111111111111';
    const oldId = '22222222-2222-4222-8222-222222222222';
    let reads = 0, retried = false, resumedReads = 0;
    await page.clock.install();
    await page.route('**/api/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      let value: any = {};
      if (path.endsWith('/stream')) return route.fulfill({contentType: 'text/event-stream', body: ': idle\n\n'});
      if (path === '/api/auth/me') value = {username: 'reviewer', role: 'SECURITY_REVIEWER'};
      if (path === '/api/auth/csrf') value = {token: 'mock-csrf'};
      if (path === '/api/projects') value = [{id: project, repository: 'org/test'}];
      if (path === '/api/dashboard/overview') value = {project: {id: project, repository: 'org/test'}, completedScans: 0};
      if (path.endsWith('/architecture/retry')) {
        expect(req.method()).toBe('POST');
        expect(req.headers()['x-csrf-token']).toBe('mock-csrf');
        expect(req.postDataJSON()).toEqual({diagramId: oldId});
        retried = true;
        value = {id: 'new-diagram', status: 'QUEUED'};
      } else if (path.endsWith('/architecture')) {
        reads++;
        value = {id: oldId, status: 'FAILED', errorCode, components: null, summary: null, confirmed: false};
        if (retried) {
          resumedReads++;
          value = {id: 'new-diagram', status: resumedReads === 1 ? 'QUEUED' : 'EXTRACTED',
            errorCode: null, summary: '재분석 완료', components: [], confirmed: false};
        }
      }
      await route.fulfill({json: value});
    });
    await page.goto(`/dashboard?project=${project}&view=architecture`);
    await expect(page.getByRole('alert')).toContainText('분석 실패');
    const failedReads = reads;
    await page.clock.runFor(6500);
    expect(reads).toBe(failedReads);
    await page.getByRole('button', {name: '분석 다시 시도', exact: true}).click();
    await expect(page.locator('.analysis-progress')).toContainText('대기 중');
    await page.clock.runFor(2100);
    await expect(page.getByText('재분석 완료', {exact: true})).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    const completeReads = reads;
    await page.clock.runFor(6500);
    expect(reads).toBe(completeReads);
  });
}
