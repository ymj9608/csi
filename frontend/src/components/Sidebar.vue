<script setup lang="ts">
import { useRoute } from "vue-router";
import {
  LayoutDashboard,
  FolderGit2,
  ScanLine,
  ShieldAlert,
  ScrollText,
  BookOpen,
  ClipboardCheck,
  LogOut,
} from "lucide-vue-next";
import { useSession } from "../stores/session";
defineProps<{ mobile: boolean; page: string }>();
const emit = defineEmits<{ logout: [] }>();
const logout = () => emit("logout");
const route = useRoute(),
  session = useSession();
const nav = [
  ["/", "보안 현황", LayoutDashboard],
  ["/projects", "프로젝트", FolderGit2],
  ["/scans", "검사 이력", ScanLine],
  ["/findings", "위험 항목", ShieldAlert],
  ["/logs", "실행 로그", ScrollText],
  ["/policies", "보안 정책", BookOpen],
  ["/approvals", "승인 관리", ClipboardCheck],
] as const;
</script>
<template>
  <aside :class="{ expanded: mobile }">
    <RouterLink class="brand" to="/" aria-label="CSI 보안 현황으로 이동">
      <svg viewBox="0 0 40 44" aria-hidden="true">
        <defs>
          <linearGradient id="brand-face" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#9DB3FF" />
            <stop offset="1" stop-color="#3F5EE8" />
          </linearGradient>
        </defs>
        <path
          d="M22 4c5 3 10 4 14 4v14c0 9-6 15-14 19-8-4-14-10-14-19V8c4 0 9-1 14-4Z"
          fill="#2E44B8"
        />
        <path
          d="M19 2c5 3 10 4 14 4v14c0 9-6 15-14 19C11 35 5 29 5 20V6c4 0 9-1 14-4Z"
          fill="url(#brand-face)"
        />
        <path
          d="M15 18v-3a4 4 0 0 1 8 0v3"
          fill="none"
          stroke="#fff"
          stroke-width="2.4"
        />
        <rect x="12.5" y="17" width="13" height="11" rx="3" fill="#fff" />
      </svg>
      <span>CSI<small>Cyber Security Inspector</small></span>
    </RouterLink>
    <nav aria-label="주요 메뉴">
      <RouterLink
        v-for="[path, name, icon] in nav"
        :key="path"
        :to="path"
        :class="{
          active:
            path === '/' ? page === 'overview' : route.path.startsWith(path),
        }"
        ><component :is="icon" :size="18" />{{ name }}</RouterLink
      >
    </nav>
    <button class="user" @click="logout" aria-label="로그아웃">
      <span class="avatar">{{
        session.user?.username?.slice(0, 1).toUpperCase()
      }}</span
      ><span
        >{{ session.user?.username }}<small>로그아웃</small></span
      ><LogOut :size="16" />
    </button>
  </aside>
</template>
