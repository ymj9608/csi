<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRoute } from "vue-router";
import {
  FolderGit2,
  ClipboardCheck,
  LogOut,
  ChevronsLeft,
  ChevronsRight,
  ChevronRight,
  LayoutDashboard,
  Network,
  ScanLine,
  ShieldAlert,
  ScrollText,
} from "lucide-vue-next";
import { useSession } from "../stores/session";
import { scopedLink } from "../lib/project";
const props = defineProps<{
  mobile: boolean;
  page: string;
  project: string;
  projectName: string;
  // 등록된 프로젝트. 메뉴의 "프로젝트" 아래에 하위 항목으로 나열합니다.
  projects: { id: string; repository: string }[];
  // 접으면 아이콘만 보이는 좁은 막대가 됩니다. 이름은 마우스를 올리면 보입니다.
  collapsed: boolean;
}>();
const emit = defineEmits<{ logout: []; toggle: [] }>();
const logout = () => emit("logout");
const route = useRoute(),
  session = useSession();
// public/brand/ 로고 파일이 없으면 기존 SVG 방패와 텍스트로 대신 보여 줍니다.
const BRAND = "/brand/";
const shieldOk = ref(true),
  wordOk = ref(true);
// 보안 현황·검사 이력·위험 항목·실행 로그는 프로젝트 화면의 버튼으로 들어가는 프로젝트 화면입니다.
const PROJECT_PAGES = ["/dashboard", "/scans", "/findings", "/logs"];
const onProjectPage = computed(() => PROJECT_PAGES.some((p) => route.path.startsWith(p)));
// 프로젝트 이름 옆 화살표를 누르면 그 프로젝트의 5개 화면이 아래에 펼쳐집니다. 처음에는 접혀 있습니다.
const PROJECT_SECTIONS = [
  ["status", "보안 현황", LayoutDashboard],
  ["architecture", "아키텍처", Network],
  ["scans", "검사 이력", ScanLine],
  ["findings", "위험 항목", ShieldAlert],
  ["logs", "실행 로그", ScrollText],
] as const;
type Section = (typeof PROJECT_SECTIONS)[number][0];
const expanded = ref<string[]>([]);
const toggleProject = (id: string) =>
  (expanded.value = expanded.value.includes(id)
    ? expanded.value.filter((p) => p !== id)
    : [...expanded.value, id]);
// 프로젝트를 선택하면 그 프로젝트의 5개 화면만 자동으로 펼치고, 다른 프로젝트는 접습니다.
// 화살표로 직접 펼치고 접는 것은 그대로 됩니다.
watch(
  () => (onProjectPage.value ? props.project : ""),
  (id) => {
    if (id) expanded.value = [id];
  },
  { immediate: true },
);
function sectionLink(id: string, section: Section) {
  if (section === "status") return { path: "/dashboard", query: { project: id } };
  if (section === "architecture") return { path: "/dashboard", query: { project: id, view: "architecture" } };
  return { path: "/" + section, query: { project: id } };
}
// 지금 보고 있는 화면(상세 화면은 그 목록)을 해당 항목으로 표시합니다.
const currentSection = computed<Section | "">(() => {
  const page = route.path.split("/")[1];
  if (page === "dashboard") return route.query.view === "architecture" ? "architecture" : "status";
  return ["scans", "findings", "logs"].includes(page) ? (page as Section) : "";
});
// 하위 프로젝트를 누르면 지금 보던 버튼 화면(목록)을 유지한 채 프로젝트만 바꿉니다.
function projectLink(id: string) {
  const [, page, detail] = route.path.split("/");
  if (!detail && ["scans", "findings", "logs"].includes(page))
    return { path: "/" + page, query: { project: id } };
  const view = page === "dashboard" && route.query.view === "architecture" ? { view: "architecture" } : {};
  return { path: "/dashboard", query: { project: id, ...view } };
}
</script>
<template>
  <aside :class="{ expanded: mobile, collapsed }">
    <button
      class="sidebar-toggle"
      :aria-label="collapsed ? '메뉴 펼치기' : '메뉴 접기'"
      :title="collapsed ? '메뉴 펼치기' : '메뉴 접기'"
      :aria-expanded="!collapsed"
      @click="emit('toggle')"
    >
      <component :is="collapsed ? ChevronsRight : ChevronsLeft" :size="16" />
    </button>
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
          @error="wordOk = false" /><template v-else>CSI</template></span
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
        to="/projects"
        :class="{ active: route.path.startsWith('/projects'), open: onProjectPage }"
        :title="collapsed ? '프로젝트' : undefined"
        ><FolderGit2 :size="18" /><span class="nav-label">프로젝트</span></RouterLink
      >
      <ul v-if="!collapsed" class="nav-projects" aria-label="등록된 프로젝트">
        <li v-for="p in projects" :key="p.id" :class="{ expanded: expanded.includes(p.id) }">
          <div class="nav-project-row">
            <RouterLink
              class="nav-project-link"
              :to="projectLink(p.id)"
              :class="{ active: onProjectPage && p.id === project }"
              :aria-current="onProjectPage && p.id === project ? 'page' : undefined"
              :title="p.repository"
              >{{ p.repository }}</RouterLink
            ><button
              class="nav-project-toggle"
              :aria-expanded="expanded.includes(p.id)"
              :aria-label="p.repository + (expanded.includes(p.id) ? ' 메뉴 접기' : ' 메뉴 펼치기')"
              @click="toggleProject(p.id)"
            >
              <ChevronRight :size="14" />
            </button>
          </div>
          <ul v-if="expanded.includes(p.id)" class="nav-project-sections" :aria-label="p.repository + ' 화면'">
            <li v-for="[key, name, icon] in PROJECT_SECTIONS" :key="key">
              <RouterLink
                :to="sectionLink(p.id, key)"
                :class="{ active: p.id === project && currentSection === key }"
                ><component :is="icon" :size="14" />{{ name }}</RouterLink
              >
            </li>
          </ul>
        </li>
        <li v-if="!projects.length" class="nav-projects-empty">등록된 프로젝트가 없습니다</li>
      </ul>
      <RouterLink
        :to="scopedLink('/approvals', project)"
        :class="{ active: route.path.startsWith('/approvals') }"
        :title="collapsed ? '승인 관리' : undefined"
        ><ClipboardCheck :size="18" /><span class="nav-label">승인 관리</span></RouterLink
      >
    </nav>
    <button class="user" @click="logout" aria-label="로그아웃" :title="collapsed ? '로그아웃' : undefined">
      <span class="avatar">{{
        session.user?.username?.slice(0, 1).toUpperCase()
      }}</span
      ><span
        >{{ session.user?.username }}<small>로그아웃</small></span
      ><LogOut :size="16" />
    </button>
  </aside>
</template>
