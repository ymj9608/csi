import { test, expect, type Page } from "@playwright/test";

const png = { name: "architecture.png", mimeType: "image/png", buffer: Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64") };

// No real projects, model inference, or database writes during browser tests.
async function mockProjects(page: Page) {
  const state = { projects: [] as any[], posts: [] as any[], fail: false };
  await page.route("**/api/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith("/stream"))
      return route.fulfill({ contentType: "text/event-stream", body: ": none\n\n" });
    let value: any = {};
    if (path === "/api/auth/me") value = { username: "test", role: "SECURITY_REVIEWER" };
    else if (path === "/api/auth/csrf") value = { token: "mock-csrf" };
    else if (path === "/api/projects" && request.method() === "POST") {
      expect(request.headers()["content-type"]).toContain("multipart/form-data");
      expect(request.headers()["x-csrf-token"]).toBe("mock-csrf");
      const form = await new Response(request.postDataBuffer(), {
        headers: { "Content-Type": request.headers()["content-type"] },
      }).formData();
      const image = form.get("architecture") as File;
      const post = { repository: form.get("repository"), defaultBranch: form.get("defaultBranch"),
        name: image.name, type: image.type, bytes: Buffer.from(await image.arrayBuffer()) };
      state.posts.push(post);
      if (state.fail) return route.fulfill({ status: 400, json: { message: "이미지 등록에 실패했습니다." } });
      const id = `00000000-0000-4000-8000-00000000000${state.posts.length}`;
      state.projects.push({ id, repository: post.repository, defaultBranch: post.defaultBranch });
      value = { id, diagramId: "diagram", architectureStatus: "QUEUED" };
    } else if (path === "/api/projects") value = state.projects;
    await route.fulfill({ json: value });
  });
  return state;
}

async function openRegistration(page: Page) {
  await page.goto("/projects");
  await page.locator(".heading-actions").getByRole("button", { name: "프로젝트 등록" }).click();
  const modal = page.locator("form.modal");
  await modal.getByLabel("저장소").fill("ymj9608/Lichu");
  await modal.getByLabel("기본 브랜치").fill("develop");
  return modal;
}

test("registration requires a file even when submit is dispatched directly", async ({ page }) => {
  const state = await mockProjects(page), modal = await openRegistration(page);
  const submit = modal.getByRole("button", { name: "프로젝트 등록", exact: true });
  await expect(modal.getByText("필수 첨부", { exact: true })).toBeVisible();
  await expect(submit).toBeDisabled();
  await modal.dispatchEvent("submit");
  await expect(page.locator(".toast")).toHaveText("아키텍처 파일을 필수로 첨부하세요.");
  expect(state.posts).toHaveLength(0);
  await modal.getByLabel("아키텍처 파일", { exact: true }).setInputFiles(png);
  await expect(submit).toBeEnabled();
  await modal.getByRole("button", { name: "architecture.png 빼기" }).click();
  await expect(submit).toBeDisabled();
});

test("project and first image are submitted together and gallery is retained", async ({ page }) => {
  const state = await mockProjects(page), modal = await openRegistration(page);
  await modal.getByLabel("아키텍처 파일", { exact: true }).setInputFiles([png, { ...png, name: "second.png" }]);
  await modal.getByRole("button", { name: "프로젝트 등록", exact: true }).click();
  await expect(modal).toBeHidden();
  expect(state.posts).toHaveLength(1);
  expect(state.posts[0]).toMatchObject({ repository: "ymj9608/Lichu", defaultBranch: "develop",
    name: "architecture.png", type: "image/png", bytes: png.buffer });
  await expect(page.locator(".toast")).toHaveText("프로젝트와 아키텍처를 등록했습니다. 아키텍처 분석 대기 중입니다.");
  const folders = await page.evaluate(async project => {
    const { loadFolders } = await import("/src/lib/architecture.ts");
    return (await loadFolders(project, "")).map((f: any) => f.images.map((i: any) => i.name));
  }, state.projects[0].id);
  expect(folders).toEqual([["architecture.png", "second.png"]]);
  await page.locator(".heading-actions").getByRole("button", { name: "프로젝트 등록" }).click();
  await expect(modal.locator(".arch-files li")).toHaveCount(0);
  await expect(modal.getByRole("button", { name: "프로젝트 등록", exact: true })).toBeDisabled();
});

test("PDF first page is sent as an analysis-ready PNG", async ({ page }) => {
  const state = await mockProjects(page), modal = await openRegistration(page);
  await modal.getByLabel("아키텍처 파일", { exact: true }).setInputFiles("../docs/diagrams/CSI_MCP_Routing_Visual_v5.pdf");
  await modal.getByRole("button", { name: "프로젝트 등록", exact: true }).click();
  await expect(modal).toBeHidden({ timeout: 20000 });
  expect(state.posts).toHaveLength(1);
  expect(state.posts[0].type).toBe("image/png");
  expect(state.posts[0].bytes.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
});

test("failed image registration preserves the form and allows retry", async ({ page }) => {
  const state = await mockProjects(page), modal = await openRegistration(page);
  state.fail = true;
  await modal.getByLabel("아키텍처 파일", { exact: true }).setInputFiles(png);
  await modal.getByRole("button", { name: "프로젝트 등록", exact: true }).click();
  await expect(page.locator(".toast")).toHaveText("이미지 등록에 실패했습니다.");
  await expect(modal).toBeVisible();
  await expect(modal.locator(".arch-files li")).toHaveCount(1);
  expect(state.projects).toHaveLength(0);
  state.fail = false;
  await modal.getByRole("button", { name: "프로젝트 등록", exact: true }).click();
  await expect(modal).toBeHidden();
  expect(state.projects).toHaveLength(1);
});

test("unreadable PDF cannot create a project", async ({ page }) => {
  const state = await mockProjects(page), modal = await openRegistration(page);
  await modal.getByLabel("아키텍처 파일", { exact: true }).setInputFiles({
    name: "broken.pdf", mimeType: "application/pdf", buffer: Buffer.from("not a PDF"),
  });
  await modal.getByRole("button", { name: "프로젝트 등록", exact: true }).click();
  await expect(page.locator(".toast")).toContainText("PDF 첫 페이지를 읽을 수 없습니다.");
  expect(state.posts).toHaveLength(0);
  await expect(modal).toBeVisible();
});
