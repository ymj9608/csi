import { createApp } from "vue";
import { createPinia } from "pinia";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import Login from "./views/Login.vue";
import Console from "./views/Console.vue";
import { useSession } from "./stores/session";
import "./style.css";
const pinia = createPinia();
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: Login },
    { path: "/:pathMatch(.*)*", component: Console },
  ],
});
router.beforeEach(async (to) => {
  const s = useSession(pinia);
  if (!s.user) await s.load();
  if (!s.user && to.path != "/login") return "/login";
  if (s.user && to.path === "/login") return "/";
});
window.addEventListener("session-expired", () => {
  useSession(pinia).user = null;
  if (router.currentRoute.value.path != "/login") router.push("/login");
});
createApp(App).use(pinia).use(router).mount("#app");
