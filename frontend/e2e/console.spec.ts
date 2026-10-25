import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const env = Object.fromEntries(
  readFileSync("../.env", "utf8")
    .trim()
    .split("\n")
    .map((s) => {
      const n = s.indexOf("=");
      return [s.slice(0, n), s.slice(n + 1)];
    }),
);
test("login, API-backed screens, findings, mobile and logout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page).toHaveURL(/login/);
  await page.getByLabel("계정", { exact: true }).fill(env.CSI_ADMIN_USERNAME);
  await page
    .getByLabel("비밀번호", { exact: true })
    .fill(env.CSI_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect(
    page.getByRole("heading", { name: "프로젝트", exact: true }),
  ).toBeVisible();
  const firstCard = page.locator(".project-card").first();
  const selectedRepository = (await firstCard.locator("h2, strong").first().textContent())!.trim();
  await firstCard.click();
  await expect(page).toHaveURL(/\/dashboard\?project=[0-9a-f-]+$/);
  // 보안 현황은 메뉴에 없고, 메뉴의 "프로젝트" 아래에서 지금 보는 프로젝트가 선택됩니다.
  await expect(page.locator("aside nav > a", { hasText: "보안 현황" })).toHaveCount(0);
  await expect(page.locator("aside nav a").first()).toHaveText("프로젝트");
  await expect(page.locator(".nav-project-link.active")).toHaveText(selectedRepository);
  await expect(page.getByRole("combobox", { name: "프로젝트 선택" })).toHaveCount(0);
  await expect(page.locator(".metrics")).toBeVisible();
  await expect(page.locator(".current-project")).toContainText(selectedRepository);
  // 검토 피드: 위험 항목과 Agent 이벤트를 한 패널에서 필터로 전환합니다.
  const feed = page.locator(".review-feed");
  await feed.getByRole("button", { name: /Agent 이벤트/ }).click();
  await expect(feed.getByRole("button", { name: /Agent 이벤트/ })).toHaveAttribute("aria-pressed", "true");
  await expect(feed.locator(".feed-icon").first()).toBeVisible();
  await feed.getByRole("button", { name: /검토 필요/ }).click();
  await expect(feed.locator(".feed-description")).toContainText("해결되지 않은 위험 항목");
  await expect(feed.locator(".feed-page .list-row")).toHaveCount(5);
  await feed.getByRole("button", { name: "다음 검토 피드" }).click();
  await expect(feed.getByRole("button", { name: "이전 검토 피드" })).toBeEnabled();
  await expect(feed.locator(".pager-dots i").nth(1)).toHaveClass(/on/);
  await expect(page.locator(".connection")).toHaveText("실시간 연결");
  await page.screenshot({
    path: "../.runtime/overview-desktop.png",
    fullPage: true,
  });
  for (const path of [
    "/projects",
    "/scans",
    "/findings",
    "/logs",
    "/approvals",
  ]) {
    await Promise.all([
      page.waitForResponse(
        (r) => new URL(r.url()).pathname === "/api" + path && r.status() === 200,
      ),
      page.goto(path),
    ]);
    await expect(page.locator(".skeleton")).toHaveCount(0);
    await expect(page.locator(".error")).toHaveCount(0);
  }
  // 선택한 프로젝트는 화면을 옮겨도 유지되고, 메뉴의 프로젝트를 눌러도 같은 목록 화면에 머뭅니다.
  await page.goto("/scans");
  await expect(page).toHaveURL(/\/scans\?project=[0-9a-f-]+$/);
  await page.locator(".nav-project-link", { hasText: selectedRepository }).click();
  await expect(page).toHaveURL(/\/scans\?project=[0-9a-f-]+$/);
  await expect(page.locator(".nav-project-link.active")).toHaveText(selectedRepository);
  await page.goto("/findings");
  const finding = page.locator(".finding-row").first();
  await expect(finding).toBeVisible();
  {
    await finding.click();
    await expect(
      page.getByRole("heading", { name: /스캐너가 찾은 사실/ }),
    ).toBeVisible();
    await page
      .getByRole("tab", { name: "보안 근거", exact: true })
      .click();
    await expect(page.locator(".reference").first()).toBeVisible();
  }
  // Verify the merged redesign still renders stored Agent evidence, not just a page shell.
  const response = await page.request.get("/api/findings");
  expect(response.ok()).toBeTruthy();
  const agentFinding = (await response.json()).find(
    (f: any) => f.analysis?.orchestration?.selectionMode === "LLM",
  );
  expect(agentFinding, "Run an LLM LOCAL_DEMO scan before the integration test").toBeTruthy();
  await page.goto("/findings/" + agentFinding.id);
  await page.getByRole("tab", { name: "AI 분석", exact: true }).click();
  const investigation = page.locator(".flow-panel").filter({
    has: page.getByRole("heading", { name: /Agent가 근거를 모은 과정/ }),
  });
  await expect(investigation).toBeVisible();
  await expect(investigation.locator("li")).toHaveCount(agentFinding.analysis.orchestration.trace.length);
  await expect(investigation).toContainText("finish_analysis");
  await expect(page.getByText(`모델 호출 ${agentFinding.analysis.contextBudget.calls}회`, { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "조치", exact: true }).click();
  await expect(page.getByRole("heading", { name: "개선 권고" })).toBeVisible();
  await expect(page.getByRole("group", { name: "검토 상태 변경" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "처리 기록" })).toBeVisible();
  await page.getByRole("tab", { name: "보안 근거", exact: true }).click();
  await expect(page.getByText("LLM이 인용한 근거", { exact: true }).first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "AI 분석", exact: true }).click();
  await expect(investigation).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "../.runtime/agent-detail-mobile.png", fullPage: true });
  await page.goto("/projects");
  await page.locator(".project-card").first().click();
  await expect(page.locator(".metrics")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: "../.runtime/overview-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page.locator(".user").click();
  await expect(page).toHaveURL(/login/);
  expect(errors).toEqual([]);
});
