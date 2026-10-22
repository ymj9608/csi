<script setup lang="ts">
import { ref } from "vue";
import { useRoute } from "vue-router";
import {
  FolderGit2,
  ScanLine,
  ShieldAlert,
  ScrollText,
  BookOpen,
  ClipboardCheck,
  LogOut,
} from "lucide-vue-next";
import { useSession } from "../stores/session";
import { scopedLink } from "../lib/project";
defineProps<{
  mobile: boolean;
  page: string;
  project: string;
  projectName: string;
}>();
const emit = defineEmits<{ logout: [] }>();
const logout = () => emit("logout");
const route = useRoute(),
  session = useSession();
// public/brand/ 로고 파일이 없으면 기존 SVG 방패와 텍스트로 대신 보여 줍니다.
const BRAND = "/brand/";
const shieldOk = ref(true),
  wordOk = ref(true);
const nav = [
  ["/projects", "프로젝트", FolderGit2],
  ["/scans", "검사 이력", ScanLine],
  ["/findings", "위험 항목", ShieldAlert],
  ["/logs", "실행 로그", ScrollText],
  ["/policies", "보안 정책", BookOpen],
  ["/approvals", "승인 관리", ClipboardCheck],
] as const;
// 보안 현황은 프로젝트 카드에서 들어가는 화면이라 메뉴에 따로 두지 않고 "프로젝트"를 선택된 상태로 둡니다.
const isActive = (path: string) =>
  route.path.startsWith(path) ||
  (path === "/projects" && route.path.startsWith("/dashboard"));
</script>
<template>
  <aside :class="{ expanded: mobile }">
    <RouterLink class="brand" to="/projects" aria-label="CSI 프로젝트 목록으로 이동">
      <img
        v-if="shieldOk"
        class="brand-symbol"
        :src="BRAND + 'csi-shield.png'"
        alt=""
        @error="shieldOk = false"
      />
      <svg v-else viewBox="0 0 40 44" aria-hidden="true">
        <defs>
          <linearGradient id="brand-face" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#9db3ff" />
            <stop offset="1" stop-color="#3f5ee8" />
          </linearGradient>
        </defs>
        <path
          d="M22 4c5 3 10 4 14 4v14c0 9-6 15-14 19-8-4-14-10-14-19V8c4 0 9-1 14-4Z"
          fill="#2e44b8"
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
      <span
        ><img
          v-if="wordOk"
          class="brand-wordmark"
          :src="BRAND + 'csi-wordmark.png'"
          alt="CSI"
          @error="wordOk = false" /><template v-else>CSI</template
        ><small>Cyber Security Inspector</small></span
      >
    </RouterLink>
    <RouterLink
      class="current-project"
      :to="scopedLink('/dashboard', project)"
      :title="projectName || '전체 프로젝트'"
      ><small>현재 프로젝트</small
      ><span>{{ projectName || "전체 프로젝트" }}</span></RouterLink
    >
    <nav aria-label="주요 메뉴">
      <RouterLink
        v-for="[path, name, icon] in nav"
        :key="path"
        :to="scopedLink(path, project)"
        :class="{ active: isActive(path) }"
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
