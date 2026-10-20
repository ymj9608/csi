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
  await expect(
    page.getByRole("heading", { name: "보안 현황" }),
  ).toBeVisible();
  await expect(page.locator(".metrics")).toBeVisible();
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
    "/policies",
    "/approvals",
  ]) {
    await Promise.all([
      page.waitForResponse(
        (r) => r.url().endsWith("/api" + path) && r.status() === 200,
      ),
      page.goto(path),
    ]);
    await expect(page.locator(".skeleton")).toHaveCount(0);
    await expect(page.locator(".error")).toHaveCount(0);
  }
  await page.goto("/findings");
  const finding = page.locator(".finding-row").first();
  await expect(finding).toBeVisible();
  {
    await finding.click();
    await expect(
      page.getByRole("heading", { name: "정적 분석 근거" }),
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
  const investigation = page.locator(".review-evidence").filter({
    has: page.getByRole("heading", { name: "Agent 도구 선택", exact: true }),
  });
  await expect(investigation).toBeVisible();
  await expect(investigation.locator("li")).toHaveCount(agentFinding.analysis.orchestration.trace.length);
  await expect(investigation).toContainText("finish_analysis");
  await expect(page.getByText(`모델 호출 ${agentFinding.analysis.contextBudget.calls}회`, { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "보안 근거", exact: true }).click();
  await expect(page.getByText("LLM이 인용한 근거", { exact: true }).first()).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "AI 분석", exact: true }).click();
  await expect(investigation).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "../.runtime/agent-detail-mobile.png", fullPage: true });
  await page.goto("/");
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
