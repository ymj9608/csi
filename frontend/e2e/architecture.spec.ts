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
const DIAGRAMS = "../docs/diagrams/";
test("architecture folders: choose folder on upload, browse thumbnails, view and delete", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page.getByLabel("계정", { exact: true }).fill(env.CSI_ADMIN_USERNAME);
  await page.getByLabel("비밀번호", { exact: true }).fill(env.CSI_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await page.locator(".project-card").first().click();
  // 아키텍처는 사이드바 메뉴가 아니라 프로젝트 화면의 버튼입니다. 처음에는 보안 현황이 선택되어 있습니다.
  await expect(page.locator("aside nav > a", { hasText: "아키텍처" })).toHaveCount(0);
  const tabs = page.getByRole("tablist", { name: "프로젝트 화면" });
  await expect(tabs.getByRole("tab", { name: "보안 현황" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".metrics")).toBeVisible();
  await tabs.getByRole("tab", { name: "아키텍처" }).click();
  await expect(page).toHaveURL(/\/dashboard\?project=[0-9a-f-]+&view=architecture$/);
  await expect(tabs.getByRole("tab", { name: "아키텍처" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".metrics")).toHaveCount(0);
  const projectName = (await page.locator(".current-project span").textContent())!.trim();

  const file = page.locator('input[type="file"]');
  const modal = page.locator(".folder-modal");
  const folders = page.locator(".folder");
  await expect(folders).toHaveCount(0);

  // 폴더가 없으면 새 폴더만 고를 수 있고, 이름은 프로젝트 이름입니다.
  await file.setInputFiles([DIAGRAMS + "CSI.png", DIAGRAMS + "csi-system-architecture-paper.en.png"]);
  await expect(modal).toBeVisible();
  await expect(modal).toContainText("선택한 이미지 2장");
  await expect(modal.getByLabel("기존 폴더에 추가")).toBeDisabled();
  await expect(modal.getByLabel("새 폴더 이름")).toHaveValue(projectName);
  await modal.getByRole("button", { name: "업로드" }).click();
  await expect(modal).toBeHidden();
  await expect(folders).toHaveCount(1);
  await expect(folders.first()).toContainText(projectName);
  // 폴더는 접힌 채로 생기고, 화살표를 눌러야 사진이 보입니다.
  await expect(folders.first().locator(".thumb")).toHaveCount(0);
  await folders.first().locator(".folder-toggle").click();
  await expect(folders.first().locator(".thumb")).toHaveCount(2);

  // 새 폴더를 하나 더 만들면 최신 폴더가 위에 옵니다.
  await file.setInputFiles(DIAGRAMS + "csi-sequence-scan-analysis.en.color.png");
  await modal.getByLabel("새 폴더 만들기").check();
  await expect(modal.getByLabel("새 폴더 이름")).toHaveValue(`${projectName} (2)`);
  await modal.getByRole("button", { name: "업로드" }).click();
  await expect(folders).toHaveCount(2);
  await expect(folders.first().locator(".folder-name strong")).toHaveText(`${projectName} (2)`);
  await expect(folders.first().locator(".thumb")).toHaveCount(0);

  // 기존 폴더를 골라 추가합니다.
  await file.setInputFiles(DIAGRAMS + "csi-sequence-approval-resume.en.color.png");
  await expect(modal.getByLabel("기존 폴더에 추가")).toBeChecked();
  await modal.getByLabel("추가할 폴더").selectOption({ label: `${projectName} (2장)` });
  await modal.getByRole("button", { name: "업로드" }).click();
  const original = folders.nth(1);
  await expect(original.locator(".thumb")).toHaveCount(3);
  // 펼쳐 둔 폴더에 추가하면 배지 없이 새 사진에만 NEW가 붙습니다.
  await expect(original.locator(".folder-new")).toHaveCount(0);
  await expect(original.locator(".thumb").nth(2).locator(".thumb-new")).toHaveText("NEW");
  await expect(original.locator(".folder-name small")).toContainText("방금 전 1장 추가");

  // PDF도 올릴 수 있고, 첫 페이지가 썸네일로 보입니다.
  await file.setInputFiles(DIAGRAMS + "CSI_MCP_Routing_Visual_v5.pdf");
  await modal.getByLabel("추가할 폴더").selectOption({ label: `${projectName} (2) (1장)` });
  await modal.getByRole("button", { name: "업로드" }).click();
  const newest = folders.first();
  await expect(newest.locator(".folder-name small")).toContainText("이미지 2장");
  // 접힌 기존 폴더에 추가하면 폴더 줄에 변경 배지가 붙습니다.
  await expect(newest.locator(".folder-new")).toHaveText("+1 새 사진");
  await newest.locator(".folder-toggle").click();
  // 펼치면 배지는 사라지고, 새 사진에 NEW가 보입니다.
  await expect(newest.locator(".folder-new")).toHaveCount(0);
  const pdfThumb = newest.locator(".thumb").nth(1);
  await expect(pdfThumb.locator(".thumb-new")).toHaveText("NEW");
  await expect(newest.locator(".thumb").first().locator(".thumb-new")).toHaveCount(0);
  await expect(pdfThumb.locator(".thumb-type")).toHaveText("PDF");
  await expect
    .poll(() => pdfThumb.locator("img").evaluate((el: HTMLImageElement) => el.naturalWidth))
    .toBeGreaterThan(0);

  // 업로드 칸은 위에 긴 직사각형으로 있고, 폴더 목록은 그 아래에 같은 너비로 쌓입니다.
  const upload = await page.locator(".architecture-upload").boundingBox();
  const list = await page.locator(".architecture-folders").boundingBox();
  expect(upload!.y + upload!.height).toBeLessThanOrEqual(list!.y);
  expect(Math.abs(upload!.width - list!.width)).toBeLessThan(2);
  await page.screenshot({ path: "test-results/architecture.png", fullPage: true });

  // 새로고침해도 확인한 폴더의 배지는 다시 나타나지 않습니다.
  await page.reload();
  await expect(page.locator(".folder-new")).toHaveCount(0);
  await newest.locator(".folder-toggle").click();
  await expect(newest.locator(".thumb-new")).toHaveCount(0);
  await original.locator(".folder-toggle").click();

  // PDF를 누르면 크게 보기 창 안에 PDF가 열립니다.
  await pdfThumb.click();
  await expect(page.locator(".viewer iframe")).toBeVisible();
  await expect(page.locator(".viewer")).toContainText("2번째 사진 (전체 2장)");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "test-results/architecture-pdf.png" });
  await page.keyboard.press("Escape");

  // 썸네일을 누르면 큰 사진과 업로드 날짜, 순서가 보입니다.
  await original.locator(".thumb").first().click();
  const viewer = page.locator(".viewer");
  await expect(viewer).toBeVisible();
  const big = viewer.locator(".viewer-stage img");
  // CSP가 blob: 이미지를 막으면 요소는 보여도 실제 그림은 그려지지 않습니다.
  await expect.poll(() => big.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
  await expect(viewer).toContainText("업로드 날짜");
  await expect(viewer).toContainText("1번째 사진 (전체 3장)");
  await page.waitForTimeout(500);
  await page.screenshot({ path: "test-results/architecture-viewer.png" });
  await viewer.getByRole("button", { name: "다음 사진" }).click();
  await expect(viewer).toContainText("2번째 사진 (전체 3장)");
  await viewer.getByRole("button", { name: "삭제" }).click();
  await expect(viewer).toContainText("2번째 사진 (전체 2장)");
  await page.keyboard.press("Escape");
  await expect(viewer).toBeHidden();

  // 새로고침 후에도 폴더와 사진이 남아 있어야 합니다.
  await page.reload();
  await expect(folders).toHaveCount(2);
  await folders.nth(1).locator(".folder-toggle").click();
  await expect(folders.nth(1).locator(".thumb")).toHaveCount(2);
  await expect(folders.first().locator(".thumb")).toHaveCount(0);

  // 폴더 삭제는 한 번 더 눌러 확인합니다.
  for (const left of [1, 0]) {
    const remove = folders.first().locator(".folder-delete");
    await remove.click();
    await expect(remove).toHaveText("삭제 확인");
    await remove.click();
    await expect(folders).toHaveCount(left);
  }
  await expect(page.locator(".architecture-folders")).toBeHidden();
  expect(errors).toEqual([]);
});

test("old architecture address opens the project screen with the architecture button selected", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("계정", { exact: true }).fill(env.CSI_ADMIN_USERNAME);
  await page.getByLabel("비밀번호", { exact: true }).fill(env.CSI_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await page.goto("/architecture");
  await expect(page).toHaveURL(/\/dashboard\?.*view=architecture/);
  const tabs = page.getByRole("tablist", { name: "프로젝트 화면" });
  await expect(tabs.getByRole("tab", { name: "아키텍처" })).toHaveAttribute("aria-selected", "true");
  // 보안 현황으로 돌아오면 지표가 다시 보입니다.
  await tabs.getByRole("tab", { name: "보안 현황" }).click();
  await expect(page).not.toHaveURL(/view=/);
  await expect(page.locator(".metrics")).toBeVisible();
});
