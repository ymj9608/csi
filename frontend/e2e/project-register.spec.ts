import { test, expect, type Page } from "@playwright/test";

// 실제 DB에 프로젝트를 만들지 않도록 API를 가짜 응답으로 대신합니다.
async function mockProjects(page: Page) {
  const state = { projects: [] as any[], posts: [] as any[] };
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (path.endsWith("/stream"))
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": none\n\n" });
    let value: any = {};
    if (path === "/api/auth/me") value = { username: "test", role: "SECURITY_REVIEWER" };
    else if (path === "/api/auth/csrf") value = { token: "mock-csrf" };
    else if (path === "/api/projects" && request.method() === "POST") {
      const body = request.postDataJSON();
      state.posts.push(body);
      const id = `00000000-0000-0000-0000-00000000000${state.posts.length}`;
      state.projects.push({ id, repository: body.repository, defaultBranch: body.defaultBranch });
      value = { id };
    } else if (path === "/api/projects") value = state.projects;
    await route.fulfill({ json: value });
  });
  return state;
}
const storedFolders = (page: Page, project: string) =>
  page.evaluate(
    (key) =>
      new Promise<any[]>((resolve, reject) => {
        const req = indexedDB.open("csi", 1);
        req.onupgradeneeded = () => req.result.createObjectStore("architecture");
        req.onsuccess = () => {
          const get = req.result.transaction("architecture").objectStore("architecture").get(key);
          get.onsuccess = () =>
            resolve((get.result || []).map((f: any) => ({ name: f.name, files: f.images.map((i: any) => i.name) })));
          get.onerror = () => reject(get.error);
        };
      }),
    project,
  );

test("architecture is optional when registering a project", async ({ page }) => {
  const state = await mockProjects(page);
  await page.goto("/projects");
  const modal = page.locator("form.modal");
  const openRegister = page.locator(".heading-actions").getByRole("button", { name: "프로젝트 등록" });

  // 아키텍처 없이 등록합니다.
  await openRegister.click();
  await expect(modal.getByText("선택 사항")).toBeVisible();
  await modal.getByLabel("저장소").fill("ymj9608/skala-vue");
  await modal.getByLabel("기본 브랜치").fill("main");
  await modal.getByRole("button", { name: "프로젝트 등록" }).click();
  await expect(modal).toBeHidden();
  await expect(page.locator(".toast")).toHaveText("프로젝트를 등록했습니다.");
  expect(state.posts).toEqual([{ repository: "ymj9608/skala-vue", defaultBranch: "main" }]);
  expect(await storedFolders(page, state.projects[0].id)).toEqual([]);

  // 아키텍처 파일을 넣어 등록하면 프로젝트 이름의 폴더가 생깁니다.
  await openRegister.click();
  await modal.getByLabel("저장소").fill("ymj9608/Lichu");
  await modal.getByLabel("아키텍처 파일").setInputFiles([
    "../docs/diagrams/CSI.png",
    "../docs/diagrams/CSI_MCP_Routing_Visual_v5.pdf",
    "../docs/diagrams/csi-system-architecture-paper.en.png",
  ]);
  await expect(modal.locator(".arch-files li")).toHaveCount(3);
  await modal.getByRole("button", { name: "csi-system-architecture-paper.en.png 빼기" }).click();
  await expect(modal.locator(".arch-files li")).toHaveCount(2);
  await page.waitForTimeout(400);
  await page.screenshot({ path: "test-results/project-register.png" });
  await modal.getByRole("button", { name: "프로젝트 등록" }).click();
  await expect(modal).toBeHidden();
  await expect(page.locator(".toast")).toHaveText("프로젝트와 아키텍처 파일 2개를 등록했습니다.");
  expect(await storedFolders(page, state.projects[1].id)).toEqual([
    { name: "ymj9608/Lichu", files: ["CSI.png", "CSI_MCP_Routing_Visual_v5.pdf"] },
  ]);

  // 다시 열면 이전에 고른 파일은 남아 있지 않습니다.
  await openRegister.click();
  await expect(modal.locator(".arch-files li")).toHaveCount(0);
});
