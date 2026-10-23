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
async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("계정", { exact: true }).fill(env.CSI_ADMIN_USERNAME);
  await page.getByLabel("비밀번호", { exact: true }).fill(env.CSI_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
}

test("sidebar folds into an icon rail and remembers it", async ({ page }) => {
  await login(page);
  const aside = page.locator("aside");
  await expect(aside).toHaveJSProperty("offsetWidth", 232);
  await page.getByRole("button", { name: "메뉴 접기" }).click();
  await expect.poll(() => aside.evaluate((el) => el.getBoundingClientRect().width)).toBe(72);
  // 글자는 숨겨도 메뉴 이름은 그대로 읽히고, 마우스를 올리면 이름이 보입니다.
  await expect(page.locator(".nav-label").first()).not.toBeInViewport({ ratio: 0.5 });
  await expect(page.getByRole("link", { name: "승인 관리" })).toHaveAttribute("title", "승인 관리");
  await expect(page.locator(".current-project")).toBeHidden();
  await expect(page.locator(".nav-projects")).toHaveCount(0);
  await page.waitForTimeout(300);
  await page.screenshot({ path: "test-results/sidebar-collapsed.png" });

  // 접은 상태는 새로고침 뒤에도 유지되고, 메뉴도 그대로 동작합니다.
  await page.reload();
  await expect.poll(() => aside.evaluate((el) => el.getBoundingClientRect().width)).toBe(72);
  await page.getByRole("link", { name: "승인 관리" }).click();
  await expect(page).toHaveURL(/\/approvals/);

  await page.getByRole("button", { name: "메뉴 펼치기" }).click();
  await expect.poll(() => aside.evaluate((el) => el.getBoundingClientRect().width)).toBe(232);
  await expect(page.locator(".current-project")).toBeVisible();
});

test("phones keep the slide-in drawer without the fold button", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(page.getByRole("button", { name: /^메뉴 (접기|펼치기)$/ })).toBeHidden();
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await expect(page.locator("aside.expanded")).toBeInViewport();
});

test("each project in the menu expands into its five screens", async ({ page }) => {
  await login(page);
  const item = page.locator(".nav-projects > li").first();
  const name = (await item.locator(".nav-project-link").textContent())!.trim();
  // 처음에는 접혀 있습니다.
  await expect(item.locator(".nav-project-sections")).toHaveCount(0);
  await item.getByRole("button", { name: `${name} 메뉴 펼치기` }).click();
  const sections = item.locator(".nav-project-sections a");
  await expect(sections).toHaveText(["보안 현황", "아키텍처", "검사 이력", "위험 항목", "실행 로그"]);

  // 항목을 누르면 그 프로젝트의 해당 화면으로 바로 가고, 메뉴에도 선택 표시가 됩니다.
  await sections.filter({ hasText: "위험 항목" }).click();
  await expect(page).toHaveURL(/\/findings\?project=[0-9a-f-]+$/);
  await expect(page.locator(".page-heading h1")).toHaveText(name);
  await expect(item.locator(".nav-project-sections a.active")).toHaveText("위험 항목");
  await sections.filter({ hasText: "아키텍처" }).click();
  await expect(page).toHaveURL(/\/dashboard\?project=[0-9a-f-]+&view=architecture$/);
  await expect(item.locator(".nav-project-sections a.active")).toHaveText("아키텍처");
  await page.locator("aside").screenshot({ path: "test-results/sidebar-sections.png" });

  // 다시 누르면 접힙니다.
  await item.getByRole("button", { name: `${name} 메뉴 접기` }).click();
  await expect(item.locator(".nav-project-sections")).toHaveCount(0);
});

test("selecting a project opens only its five screens in the menu", async ({ page }) => {
  await login(page);
  const items = page.locator(".nav-projects > li");
  test.skip((await items.count()) < 2, "needs two registered projects");
  const [first, second] = [items.nth(0), items.nth(1)];
  await expect(page.locator(".nav-project-sections")).toHaveCount(0);

  await first.locator(".nav-project-link").click();
  await expect(first.locator(".nav-project-sections")).toBeVisible();
  await expect(second.locator(".nav-project-sections")).toHaveCount(0);

  // 다른 프로젝트를 고르면 앞의 프로젝트는 접히고 새 프로젝트가 펼쳐집니다.
  await second.locator(".nav-project-link").click();
  await expect(second.locator(".nav-project-sections")).toBeVisible();
  await expect(first.locator(".nav-project-sections")).toHaveCount(0);

  // 화살표로 직접 여닫는 것도 그대로 됩니다.
  await first.locator(".nav-project-toggle").click();
  await expect(first.locator(".nav-project-sections")).toBeVisible();
  await second.locator(".nav-project-toggle").click();
  await expect(second.locator(".nav-project-sections")).toHaveCount(0);
});
