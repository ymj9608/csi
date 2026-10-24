import { test, expect, type Page } from "@playwright/test";

// 실제 DB와 무관하게 순서를 확인하도록 API를 가짜 응답으로 대신합니다.
// /api/projects는 서버처럼 최신 생성순(new → mid → old)으로 돌려줍니다.
async function mockApprovals(page: Page) {
  const projects = [
    { id: "p-new", repository: "team/newest" },
    { id: "p-mid", repository: "team/waiting" },
    { id: "p-old", repository: "team/oldest" },
  ];
  const approval = (id: string, repository: string, status: string, createdAt: string) => ({
    id, scanId: "scan-" + id, repository, status, action: "CREATE_SECURITY_REVIEW_ISSUE",
    commitSha: id.padEnd(40, "0"), policyVersion: "v1", createdAt,
  });
  const approvals = [
    approval("a1", "team/waiting", "APPROVED", "2026-10-22T05:00:00Z"),
    approval("a2", "team/waiting", "PENDING", "2026-10-22T04:00:00Z"),
    approval("a3", "team/waiting", "PENDING", "2026-10-22T03:00:00Z"),
    approval("a4", "team/oldest", "APPROVED", "2026-10-21T03:00:00Z"),
    approval("a5", "team/oldest", "REJECTED", "2026-10-21T02:00:00Z"),
  ];
  const requests: string[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/stream"))
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": none\n\n" });
    requests.push(url.pathname + url.search);
    let value: any = {};
    if (url.pathname === "/api/auth/me") value = { username: "test", role: "SECURITY_REVIEWER" };
    else if (url.pathname === "/api/projects") value = projects;
    else if (url.pathname === "/api/approvals") value = approvals;
    await route.fulfill({ json: value });
  });
  return requests;
}

test("approvals are grouped by project with waiting projects first", async ({ page }) => {
  const requests = await mockApprovals(page);
  // 다른 프로젝트를 보던 중이어도 메뉴의 승인 관리는 전체 내역을 보여 줍니다.
  await page.goto("/scans?project=p-new");
  await page.getByRole("link", { name: "승인 관리" }).click();
  await expect(page).toHaveURL(/\/approvals$/);
  expect(requests).toContain("/api/approvals");

  const folders = page.locator(".approval-folder");
  // 승인 대기가 있는 폴더가 맨 위, 나머지는 최신 생성순입니다.
  await expect(folders.locator(".approval-folder-bar strong")).toHaveText([
    "team/waiting",
    "team/newest",
    "team/oldest",
  ]);
  await expect(folders.first().locator(".approval-waiting")).toHaveText("승인 대기 2");
  await expect(folders.nth(1).locator(".approval-waiting")).toHaveCount(0);
  await expect(folders.nth(2)).toContainText("승인 요청 2건 · 승인 1 · 거절 1");

  // 폴더는 접혀 있고, 누르면 승인 대기부터 내역이 펼쳐집니다.
  await expect(page.locator(".approval-row")).toHaveCount(0);
  await folders.first().locator(".approval-folder-bar").click();
  const rows = folders.first().locator(".approval-row");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText("승인 대기");
  await expect(rows.nth(1)).toContainText("승인 대기");
  await page.waitForTimeout(300);
  await page.screenshot({ path: "test-results/approvals.png" });

  // 내역을 누르면 기존처럼 승인·거절 창이 열립니다.
  await rows.first().click();
  // 창 이름이 아니라 실제 내용(제목, 저장소, 승인·거절 버튼)이 보이는지 확인합니다.
  const dialog = page.getByRole("dialog", { name: "상세 정보" });
  await expect(dialog.getByRole("heading", { name: "승인 요청" })).toBeVisible();
  await expect(dialog).toContainText("team/waiting");
  await expect(dialog.getByRole("button", { name: "승인", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "거절", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "닫기" }).click();
  await expect(dialog).toHaveCount(0);

  // 요청이 없는 프로젝트도 폴더로 보이고, 펼치면 안내 문구가 나옵니다.
  await folders.nth(1).locator(".approval-folder-bar").click();
  await expect(folders.nth(1)).toContainText("승인 요청이 없습니다.");
});

test("projects waiting for approval are marked on the project list only", async ({ page }) => {
  await mockApprovals(page);
  await page.goto("/projects");
  const waiting = page.locator(".project-card", { hasText: "team/waiting" });
  await expect(waiting.locator(".approval-waiting")).toHaveText("승인 대기 2");
  await expect(page.locator(".project-card", { hasText: "team/oldest" }).locator(".approval-waiting")).toHaveCount(0);
  // 메뉴의 프로젝트 이름 옆에는 승인 대기 숫자를 표시하지 않습니다.
  await expect(page.locator(".nav-projects > li", { hasText: "team/waiting" })).toHaveText(/^team\/waiting$/);
  await page.waitForTimeout(300);
  await page.screenshot({ path: "test-results/projects-pending.png" });
});

test("approved coding notification does not offer another approval or Agent execution", async ({ page }) => {
  await mockApprovals(page);
  await page.route('**/api/approvals', route=>route.fulfill({json:[{
    id:'notification',scanId:'scan',repository:'team/waiting',status:'APPROVED',
    action:'CODING_PROPOSAL_APPROVED',proposalId:'proposal',commitSha:'a'.repeat(40),
    createdAt:'2026-10-24T01:00:00Z',decidedAt:'2026-10-24T01:00:00Z',decidedBy:'reviewer'
  }]}));
  await page.goto('/approvals');
  const folder=page.locator('.approval-folder',{hasText:'team/waiting'});
  await folder.locator('.approval-folder-bar').click();
  await folder.locator('.approval-row').click();
  const dialog=page.getByRole('dialog',{name:'상세 정보'});
  await expect(dialog.getByRole('heading',{name:'수정안 승인 알림'})).toBeVisible();
  await expect(dialog).toContainText('원본 코드 반영은 별도 작업');
  await expect(dialog.getByRole('button',{name:'승인',exact:true})).toHaveCount(0);
  await expect(dialog.getByRole('button',{name:'거절',exact:true})).toHaveCount(0);
});
