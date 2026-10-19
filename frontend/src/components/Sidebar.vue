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
  ChevronRight,
  LogOut,
  ShieldCheck,
} from "lucide-vue-next";
import { useSession } from "../stores/session";
defineProps<{ mobile: boolean; page: string }>();
const emit = defineEmits<{ logout: [] }>();
const logout = () => emit("logout");
const route = useRoute(),
  session = useSession();
const nav = [
  ["/", "Overview", "보안 현황", LayoutDashboard],
  ["/projects", "Projects", "프로젝트", FolderGit2],
  ["/scans", "Scan history", "검사 이력", ScanLine],
  ["/findings", "Findings", "위험 항목", ShieldAlert],
  ["/logs", "Execution logs", "실행 로그", ScrollText],
  ["/policies", "Security policies", "보안 정책", BookOpen],
  ["/approvals", "Approval queue", "승인 관리", ClipboardCheck],
] as const;
</script>
<template>
  <aside :class="{ expanded: mobile }">
    <RouterLink class="brand" to="/"
      ><img src="/csi.png" alt="CSI — Cyber Security Inspector"
    /></RouterLink>
    <div class="workspace">
      <span class="workspace-mark">C</span>
      <div>Security workspace<small>Enterprise console</small></div>
      <ChevronRight :size="14" />
    </div>
    <div class="nav-label">WORKSPACE</div>
    <nav>
      <RouterLink
        v-for="[path, name, label, icon] in nav"
        :key="path"
        :to="path"
        :class="{
          active:
            path === '/' ? page === 'overview' : route.path.startsWith(path),
        }"
        ><component :is="icon" :size="18" /><span
          >{{ name }}<small>{{ label }}</small></span
        ></RouterLink
      >
    </nav>
    <div class="sidebar-bottom">
      <div class="system-note">
        <ShieldCheck :size="18" />
        <div>
          Evidence-first security<small>정적 분석 · 정책 기반 검증</small>
        </div>
      </div>
      <button class="user" @click="logout">
        <span class="avatar">{{
          session.user?.username?.slice(0, 1).toUpperCase()
        }}</span
        ><span
          >{{ session.user?.username }}<small>Security reviewer</small></span
        ><LogOut :size="16" />
      </button>
    </div>
  </aside>
</template>
