import { createApp } from "vue";
import { createPinia } from "pinia";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import Login from "./views/Login.vue";
import Console from "./views/Console.vue";
import { useSession } from "./stores/session";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./style.css";
const pinia = createPinia();
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: Login },
    // 보안 현황은 프로젝트별로만 보여주므로 첫 화면은 프로젝트 목록입니다.
    { path: "/", redirect: "/projects" },
    // 예전 프로젝트 상세 주소는 그 프로젝트를 선택한 보안 현황으로 보냅니다.
    {
      path: "/projects/:id",
      redirect: (to) => ({ path: "/dashboard", query: { project: String(to.params.id) } }),
    },
    // 아키텍처는 프로젝트 화면의 버튼으로 옮겼습니다. 예전 주소는 그 버튼이 선택된 화면으로 보냅니다.
    {
      path: "/architecture",
      redirect: (to) => ({ path: "/dashboard", query: { ...to.query, view: "architecture" } }),
    },
    { path: "/:pathMatch(.*)*", component: Console },
  ],
});
router.beforeEach(async (to) => {
  const s = useSession(pinia);
  if (!s.user) await s.load();
  if (!s.user && to.path != "/login") return "/login";
  if (s.user && to.path === "/login") return "/projects";
});
window.addEventListener("session-expired", () => {
  useSession(pinia).user = null;
  if (router.currentRoute.value.path != "/login") router.push("/login");
});
createApp(App).use(pinia).use(router).mount("#app");
