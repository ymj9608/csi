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
test("project screen buttons replace the scan, finding and log menu items", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page.getByLabel("계정", { exact: true }).fill(env.CSI_ADMIN_USERNAME);
  await page.getByLabel("비밀번호", { exact: true }).fill(env.CSI_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);

  // 왼쪽 메뉴는 프로젝트와 승인 관리이고, 등록된 프로젝트는 "프로젝트" 아래에 나열됩니다.
  await expect(page.locator("aside nav > a")).toHaveText(["프로젝트", "승인 관리"]);
  const listed = await page.locator(".nav-project-link").allTextContents();
  const cards = await page.locator(".project-card h2, .project-card strong").allTextContents();
  expect(listed.length).toBeGreaterThan(0);
  for (const name of listed) expect(cards.map((c) => c.trim())).toContain(name.trim());

  const card = page.locator(".project-card").first();
  const name = (await card.locator("h2, strong").first().textContent())!.trim();
  await card.click();
  await expect(page).toHaveURL(/\/dashboard\?project=([0-9a-f-]+)$/);
  const project = new URL(page.url()).searchParams.get("project");
  const tabs = page.getByRole("tablist", { name: "프로젝트 화면" });
  await expect(tabs.getByRole("tab")).toHaveText(["보안 현황", "아키텍처", "검사 이력", "위험 항목", "실행 로그"]);

  // 각 버튼은 같은 프로젝트의 목록 화면을 열고, 프로젝트 이름과 버튼 줄을 그대로 보여 줍니다.
  for (const [label, path] of [
    ["검사 이력", "/scans"],
    ["위험 항목", "/findings"],
    ["실행 로그", "/logs"],
  ] as const) {
    await tabs.getByRole("tab", { name: label }).click();
    await expect(page).toHaveURL(new RegExp(`${path}\\?project=${project}`));
    await expect(tabs.getByRole("tab", { name: label })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".page-heading h1")).toHaveText(name);
    await expect(page.locator(".nav-project-link.active")).toHaveText(name);
  }

  // 보안 현황과 아키텍처로도 돌아갈 수 있습니다.
  await tabs.getByRole("tab", { name: "아키텍처" }).click();
  await expect(page).toHaveURL(new RegExp(`/dashboard\\?project=${project}&view=architecture`));
  await tabs.getByRole("tab", { name: "보안 현황" }).click();
  await expect(page).toHaveURL(new RegExp(`/dashboard\\?project=${project}$`));

  // 보안 정책 화면은 없앴고, 예전 주소는 프로젝트 목록으로 보냅니다.
  await page.goto("/policies");
  await expect(page).toHaveURL(/\/projects$/);
  expect(errors).toEqual([]);
});
