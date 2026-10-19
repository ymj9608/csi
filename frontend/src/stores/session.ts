import { defineStore } from "pinia";
import { ref } from "vue";
import { api, clearCsrf } from "../lib/api";
export const useSession = defineStore("session", () => {
  const user = ref<any>(null);
  const toast = ref("");
  let timer: ReturnType<typeof setTimeout>;
  function notify(s: string) {
    toast.value = s;
    clearTimeout(timer);
    timer = setTimeout(() => (toast.value = ""), 4000);
  }
  async function load() {
    try {
      user.value = await api("/auth/me");
    } catch {
      user.value = null;
    }
  }
  async function login(username: string, password: string) {
    await api("/auth/login", "POST", { username, password });
    clearCsrf();
    await load();
  }
  async function logout() {
    await api("/auth/logout", "POST");
    user.value = null;
    clearCsrf();
  }
  return { user, toast, notify, load, login, logout };
});
