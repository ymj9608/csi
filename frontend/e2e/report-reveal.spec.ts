import { test, expect, type Page } from '@playwright/test';

// Every API request is intercepted: replaying stored reports must never run a scan,
// generate a proposal, change a review decision, or depend on local credentials.
async function mockReports(page: Page, options: { completed?: boolean } = {}) {
  const reads: string[] = [], writes: string[] = [];
  const state = { openFindings: 2 };
  const projects = ['a', 'b'].map(id => ({ id, repository: `team/Project-${id.toUpperCase()}`,
    defaultBranch: 'develop', policyVersion: 'policy-v1', completedScans: options.completed === false ? 0 : 1,
    openFindings: 2, openCriticalHigh: 1, latestStatus: options.completed === false ? 'RUNNING' : 'COMPLETED',
    lastScanAt: '2026-10-22T04:40:00Z' }));
  const finding = { id: 'finding-a', scanId: 'scan-a', repository: projects[0]!.repository,
    ruleId: 'SEC-02', title: '비밀번호 저장 보완', status: 'OPEN', severity: 'HIGH',
    evidenceStatus: 'SUSPECTED', confidence: 'MEDIUM', filePath: 'backend/app/core/csi_signup.py',
    startLine: 26, endLine: 26, commitSha: 'a'.repeat(40),
    maskedCodeEvidence: 'hashlib.sha256(password.encode()).hexdigest()',
    analysis: { mode: 'RULE_BASED', red: '빠른 해시를 저장하면 비밀번호 추측 비용이 낮아집니다.',
      blue: '저장된 정적 근거를 검토한 결과입니다.', remediation: '비밀번호 전용 해시를 사용하세요.',
      defenseAssessment: 'REVIEW_REQUIRED', unknowns: ['운영 환경의 저장 경로는 검증하지 않았습니다.'],
      facts: [{ id: 'F1', text: '빠른 해시 정적 패턴이 탐지되었습니다.', filePath: 'signup.py', line: 26 }],
      references: [{ chunkId: 'reference-a', sectionId: 'POL-04', sectionTitle: '비밀번호 저장 정책',
        documentId: 'POLICY', documentVersion: '1', documentType: 'INTERNAL_POLICY', pageNumber: 4,
        content: '승인된 비밀번호 전용 해시를 사용합니다.' }],
      orchestration: { selectionMode: 'RULE_BASED', turns: 3, trace: [
        { turn: 1, tool: 'get_privacy_policy', status: 'OK', mode: 'RULE_BASED' },
        { turn: 2, tool: 'get_guideline_details', ruleId: 'SEC-02', status: 'OK', mode: 'RULE_BASED' },
        { turn: 3, tool: 'finish_analysis', status: 'OK', mode: 'RULE_BASED' },
      ] } } };
  await page.addInitScript(() => {
    const sources: any[] = [];
    class StoredReportEvents extends EventTarget {
      readyState = 1;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      constructor(public url: string) {
        super(); sources.push(this);
        queueMicrotask(() => this.onopen?.(new Event('open')));
      }
      close() { this.readyState = 2; }
    }
    (window as any).EventSource = StoredReportEvents;
    (window as any).__reportUpdate = () => sources.filter(source => source.readyState === 1)
      .forEach(source => source.dispatchEvent(new MessageEvent('update', { data: '{}' })));
  });
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (request.method() !== 'GET') {
      writes.push(`${request.method()} ${path}`);
      return route.fulfill({ status: 405, json: { message: 'This test only permits reading saved results.' } });
    }
    reads.push(path + url.search);
    let value: any = {};
    if (path === '/api/auth/me') value = { username: 'mock-reviewer', role: 'SECURITY_REVIEWER' };
    else if (path === '/api/projects') value = projects;
    else if (path === '/api/dashboard/overview') {
      const project = projects.find(item => item.id === url.searchParams.get('projectId')) || projects[0];
      value = { project, projects: 2, scans: 1, completedScans: project!.completedScans,
        openFindings: state.openFindings, criticalHigh: 1, pendingApprovals: 1,
        trend: [], distribution: [], topFindings: [finding], recentLogs: [],
        failures: [{ id: 'failed-scan', repository: 'team/Project-A', status: 'FAILED' }] };
    } else if (path === '/api/findings/finding-a') value = finding;
    else if (path === '/api/scans/scan-a') value = { id: 'scan-a', status: 'COMPLETED' };
    else if (path === '/api/scans/scan-a/findings') value = [finding];
    else if (path === '/api/scans/scan-a/coding-proposals') value = { enabled: true, supported: true, items: [] };
    await route.fulfill({ json: value });
  });
  return { reads, writes, state };
}

const reveal = (page: Page) => page.getByRole('region', { name: '분석 결과 펼쳐보기', exact: true });

async function stopTime(page: Page) {
  await page.clock.install({ time: new Date('2026-10-22T04:00:00Z') });
  await page.clock.pauseAt(new Date('2026-10-22T04:00:01Z'));
}

async function enterProject(page: Page) {
  await page.goto('/projects');
  await page.locator('.project-card').filter({ hasText: 'team/Project-A' }).click();
  await expect(page).toHaveURL(/\/dashboard\?project=a$/);
}

// 저장된 결과는 펼쳐보기 상자나 순차 연출 없이 처음부터 모두 보입니다. 시간을 멈춰도 그대로여야 합니다.
test('project screen shows the trimmed report at once', async ({ page }) => {
  const { writes } = await mockReports(page);
  await stopTime(page);
  await enterProject(page);
  await expect(reveal(page)).toHaveCount(0);
  await expect(page.locator('.report-narrative')).toContainText('미해결 위험 항목이 2건 있습니다.');
  // 지표는 전체·완료·미완료 검사 세 가지입니다. 미완료 = 전체 - 완료입니다.
  await expect(page.locator('.metrics .metric-label')).toHaveText(['전체 검사', '완료된 검사', '미완료 검사']);
  await expect(page.locator('.metric-pending strong')).toHaveText('0');
  await expect(page.locator('.metric-done small')).toHaveText('완료율 100%');
  // 위험도 분포가 왼쪽, 발견 추이가 오른쪽이고, 분포 맨 위에 전체 미해결 항목 합계가 있습니다.
  await expect(page.locator('.charts-grid .panel-title h2')).toHaveText(['위험도 분포', '위험 항목 발견 추이']);
  await expect(page.getByRole('heading', { name: '진단 범위', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '검토 피드', exact: true })).toBeVisible();
  // 검토 피드 필터는 '검토 필요'와 'Agent 이벤트' 두 가지만 있습니다.
  await expect(page.locator('.feed-filters button')).toHaveCount(2);
  await expect(page.locator('.feed-filters button').first()).toContainText('검토 필요');
  await expect(page.locator('.feed-filters button').last()).toContainText('Agent 이벤트');
  await expect(page.getByRole('heading', { name: '최근 실패한 검사', exact: true })).toBeVisible();
  await expect(page.locator('.evidence-note')).toBeVisible();
  await expect(page.locator('footer')).toBeVisible();
  await page.screenshot({ path: '../.runtime/report-reveal-desktop.png', fullPage: true, animations: 'disabled' });
  expect(writes).toEqual([]);
});

test('project switching and SSE refresh update the screen without a reveal', async ({ page }) => {
  const { reads, writes, state } = await mockReports(page);
  await stopTime(page);
  await enterProject(page);
  await page.locator('.nav-project-link', { hasText: 'team/Project-B' }).click();
  await expect(page.locator('.project-heading')).toContainText('team/Project-B');
  state.openFindings = 7;
  await page.evaluate(() => (window as any).__reportUpdate());
  await page.clock.runFor(400);
  await expect(page.locator('.report-narrative')).toContainText('미해결 위험 항목이 7건 있습니다.');
  await expect(reveal(page)).toHaveCount(0);
  expect(reads.filter(path => path.startsWith('/api/dashboard/overview'))).toHaveLength(3);
  expect(writes).toEqual([]);
});

test('a project without a completed scan does not show an invented analysis', async ({ page }) => {
  const { writes } = await mockReports(page, { completed: false });
  await stopTime(page);
  await page.goto('/projects');
  await page.locator('.project-card').filter({ hasText: 'team/Project-A' }).click();
  await expect(page.locator('.project-heading')).toContainText('team/Project-A');
  await expect(page.locator('.report-narrative')).toHaveCount(0);
  await expect(page.locator('.metrics')).toBeVisible();
  await expect(page.getByRole('heading', { name: '검토 피드', exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});

test('finding detail shows stored facts, analysis and limits at once without the reveal box', async ({ page }) => {
  const { writes } = await mockReports(page);
  await stopTime(page);
  await page.goto('/findings/finding-a');
  await expect(page.getByRole('tab', { name: 'AI 분석', exact: true })).toBeVisible();
  await expect(reveal(page)).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /AI가 찾은 사실/ })).toBeVisible();
  await expect(page.getByText('빠른 해시를 저장하면 비밀번호 추측 비용이 낮아집니다.', { exact: true })).toBeVisible();
  await expect(page.getByText('운영 환경의 저장 경로는 검증하지 않았습니다.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '수정안 생성·검토로 이동', exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});

test('mobile project report and finding detail fit the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { writes } = await mockReports(page);
  await stopTime(page);
  await enterProject(page);
  await expect(page.locator('.metrics')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../.runtime/report-reveal-mobile.png', fullPage: true, animations: 'disabled' });
  await page.goto('/findings/finding-a');
  await expect(page.getByRole('heading', { name: /AI가 찾은 사실/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../.runtime/report-reveal-finding-mobile.png', fullPage: true, animations: 'disabled' });
  expect(writes).toEqual([]);
});
