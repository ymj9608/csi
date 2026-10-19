<script setup lang="ts">
import Sidebar from "../components/Sidebar.vue";
import HeaderBar from "../components/HeaderBar.vue";
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  LayoutDashboard,
  FolderGit2,
  ScanLine,
  ShieldAlert,
  ScrollText,
  BookOpen,
  ClipboardCheck,
  Search,
  ArrowUpRight,
  RefreshCw,
  ChevronRight,
  LogOut,
  Menu,
  X,
  Plus,
  GitBranch,
  Activity,
  ShieldCheck,
} from "lucide-vue-next";
import { api, date } from "../lib/api";
import { useSession } from "../stores/session";
import Badge from "../components/Badge.vue";
import Chart from "../components/Chart.vue";
import ChangeReview from "../components/ChangeReview.vue";
import ShieldScene from "../components/ShieldScene.vue";
import { label } from "../components/labels";
const route = useRoute(),
  router = useRouter(),
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
const page = computed(() => route.path.split("/")[1] || "overview"),
  id = computed(() => route.path.split("/")[2]);
const heading = computed(
  () => nav.find((n) => n[0] === "/" + page.value)?.[1] || "보안 현황",
);
const intro: Record<string, string> = {
  projects: "검사 대상 저장소와 마지막 검사 결과입니다.",
  scans: "커밋별 검사 진행 상황과 진단 근거를 추적합니다.",
  findings: "검사에서 발견된 위험 항목을 위험도와 상태로 걸러 봅니다.",
  logs: "Agent와 검사 파이프라인의 실행 기록입니다.",
  policies: "진단 근거로 쓰이는 사내 보안 정책 조항입니다.",
  approvals: "Agent가 요청한 조치를 검토하고 승인하거나 거절합니다.",
};
const tabs: Record<string, string> = {
  Overview: "개요",
  "Code Evidence": "코드 근거",
  "AI Analysis": "AI 분석",
  Remediation: "개선 권고",
  "Security References": "보안 근거",
  Activity: "활동",
};
const data = ref<any>({}),
  items = ref<any[]>([]),
  loading = ref(false),
  error = ref(""),
  search = ref(""),
  status = ref(""),
  severity = ref(""),
  branch = ref(""),
  since = ref(""),
  until = ref(""),
  current = ref(1),
  mobile = ref(false),
  tab = ref("Overview"),
  streamState = ref("연결 대기"),
  drawer = ref<any>(null),
  projectModal = ref(false),
  repo = ref(""),
  defaultBranch = ref("develop");
const reviewGroups = computed(() => {
  const groups: Record<string, number> = {};
  for (const f of data.value.findings || []) {
    if (f.ruleId !== 'POL-01' || !f.analysis?.policyComparison?.field) continue;
    const key = f.analysis.policyComparison.field;
    groups[key] = (groups[key] || 0) + 1;
  }
  return Object.entries(groups);
});
const policyLabels: Record<string, string> = {LISTED: '승인 목록에 포함', NOT_LISTED: '승인 목록에 없음', RESTRICTED: '제한 항목', UNKNOWN: '판단 보류'};
let es: EventSource | undefined;
let refreshTimer: ReturnType<typeof setTimeout>;
let request = 0;
const logLevel = ref(""),
  oldestFirst = ref(false);
const filtered = computed(() =>
  items.value
    .filter(
      (i) =>
        JSON.stringify(i).toLowerCase().includes(search.value.toLowerCase()) &&
        (!status.value || i.status === status.value) &&
        (!logLevel.value || i.level === logLevel.value) &&
        (!severity.value ||
          i.severity === severity.value ||
          i.severities?.includes(severity.value)) &&
        (!branch.value || i.branch?.includes(branch.value)) &&
        (!since.value || (i.createdAt || i.timestamp || "") >= since.value) &&
        (!until.value ||
          (i.createdAt || i.timestamp || "") <= until.value + "T23:59:59.999Z"),
    )
    .sort((a, b) =>
      page.value === "logs" && oldestFirst.value
        ? String(a.timestamp).localeCompare(String(b.timestamp))
        : 0,
    ),
);
const pages = computed(() =>
  Math.max(1, Math.ceil(filtered.value.length / 10)),
);
const visible = computed(() =>
  filtered.value.slice((current.value - 1) * 10, current.value * 10),
);
const scanRows = computed(() =>
  page.value === "overview" ? data.value.recentScans || [] : visible.value,
);
const metrics = computed(() => [
  ["등록 프로젝트", data.value.projects, FolderGit2],
  ["완료된 검사", data.value.completedScans, ScanLine],
  ["미해결 위험 항목", data.value.openFindings, ShieldAlert],
  ["치명 / 높음", data.value.criticalHigh, Activity],
  ["검토 대기", data.value.pendingApprovals, ClipboardCheck],
]);
const profiles = [
  {
    id: "T1",
    name: "오프라인 비밀번호 추측",
    rules: ["SEC-01", "SEC-02", "SEC-04"],
    detail: "평문 저장, 빠른 해시, 낮은 bcrypt 비용",
  },
  {
    id: "T2",
    name: "사전 계산 결과 재사용",
    rules: ["SEC-03"],
    detail: "고정 Salt, 사용자별 고유성 부족",
  },
  {
    id: "T3",
    name: "로그를 통한 비밀정보 유출",
    rules: ["SEC-05"],
    detail: "비밀번호, 인증 토큰, 개인정보의 로그 출력",
  },
  {
    id: "T4",
    name: "미승인 개인정보 처리",
    rules: ["POL-01"],
    detail: "승인되지 않은 항목, 신규 필드, 처리 경로",
  },
];
const palette = ["#C8264F", "#E0701F", "#D9A400", "#7F99FA"];
const chartFont = {
  fontFamily: "'Pretendard Variable', Pretendard, sans-serif",
};
const donut = computed(() => ({
  animation: false,
  textStyle: chartFont,
  color: palette,
  tooltip: { trigger: "item" },
  series: [
    {
      type: "pie",
      radius: ["62%", "80%"],
      center: ["50%", "46%"],
      label: { show: false },
      itemStyle: { borderColor: "#fff", borderWidth: 3, borderRadius: 4 },
      data: (data.value.distribution || []).map((x: any) => ({
        name: label(x.severity),
        value: x.count,
        itemStyle: {
          color: (
            {
              CRITICAL: "#C8264F",
              HIGH: "#E0701F",
              MEDIUM: "#D9A400",
              LOW: "#7F99FA",
            } as Record<string, string>
          )[x.severity],
        },
      })),
    },
  ],
  legend: {
    bottom: 0,
    icon: "circle",
    textStyle: { color: "#545B80", ...chartFont },
    itemWidth: 8,
    itemHeight: 8,
  },
}));
const trend = computed(() => ({
  animation: false,
  textStyle: chartFont,
  color: ["#3F5EE8"],
  tooltip: { trigger: "axis" },
  grid: { left: 40, right: 20, top: 25, bottom: 30 },
  xAxis: {
    type: "category",
    data: (data.value.trend || []).map((x: any) => x.day),
    axisLine: { lineStyle: { color: "#CBD4EE" } },
    axisTick: { show: false },
    axisLabel: { color: "#6B7296" },
  },
  yAxis: {
    type: "value",
    minInterval: 1,
    splitLine: { lineStyle: { color: "#E6EAF6" } },
    axisLabel: { color: "#6B7296" },
  },
  series: [
    {
      type: "line",
      smooth: false,
      data: (data.value.trend || []).map((x: any) => x.count),
      lineStyle: { width: 2.5 },
      areaStyle: {
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(63,94,232,.22)" },
            { offset: 1, color: "rgba(63,94,232,0)" },
          ],
        },
      },
      symbolSize: 7,
    },
  ],
}));
async function load(quiet = false) {
  const key = ++request;
  if (!quiet) loading.value = true;
  error.value = "";
  try {
    let path =
      page.value === "overview"
        ? "/dashboard/overview"
        : "/" + page.value + (id.value ? "/" + id.value : "");
    const result = await api(path);
    if (key !== request) return;
    data.value = Array.isArray(result) ? {} : result;
    items.value = Array.isArray(result) ? result : result.items || [];
    if (id.value && page.value === "scans") {
      const [findings, logs, comparison, changes] = await Promise.all([
        api(path + "/findings"),
        api(path + "/logs"),
        api(path + "/comparison"),
        api(path + "/changes"),
      ]);
      if (key === request)
        data.value = { ...result, findings, logs, comparison, changes };
    }
    if (id.value && page.value === "projects") {
      items.value = await api("/scans?projectId=" + id.value);
    }
  } catch (e: any) {
    if (key === request) error.value = e.message;
  } finally {
    if (key === request) loading.value = false;
  }
}
function connect() {
  es?.close();
  es = new EventSource(
    id.value && page.value === "scans"
      ? `/api/scans/${id.value}/stream`
      : "/api/events/stream",
  );
  es.onopen = () => (streamState.value = "실시간 연결");
  es.onerror = async () => {
    streamState.value = "재연결 중";
    try {
      await api("/auth/me");
    } catch (e: any) {
      if (e.status === 401) {
        session.user = null;
        router.replace("/login");
      }
    }
  };
  es.addEventListener("update", () => {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => load(true), 400);
  });
}
watch(
  () => route.fullPath,
  () => {
    mobile.value = false;
    search.value = "";
    status.value = "";
    severity.value = "";
    branch.value = "";
    since.value = "";
    until.value = "";
    logLevel.value = "";
    oldestFirst.value = false;
    current.value = 1;
    tab.value = "Overview";
    load();
    connect();
  },
  { immediate: true },
);
watch(
  [search, status, severity, branch, since, until, logLevel],
  () => (current.value = 1),
);
onBeforeUnmount(() => {
  es?.close();
  clearTimeout(refreshTimer);
});
async function review(value: string) {
  try {
    await api("/findings/" + id.value + "/review", "POST", { status: value });
    session.notify("검토 상태를 저장했습니다.");
    load();
  } catch (e: any) {
    session.notify(e.message);
  }
}
async function decide(a: any, decision: string) {
  try {
    await api("/approvals/" + a.id + "/decision", "POST", { decision });
    drawer.value = null;
    session.notify("승인 결정을 저장했습니다.");
    load();
  } catch (e: any) {
    session.notify(e.message);
  }
}
async function addProject() {
  try {
    await api("/projects", "POST", {
      repository: repo.value,
      defaultBranch: defaultBranch.value,
    });
    projectModal.value = false;
    repo.value = "";
    session.notify("프로젝트를 등록했습니다.");
    load();
  } catch (e: any) {
    session.notify(e.message);
  }
}
async function logout() {
  try {
    await session.logout();
    router.push("/login");
  } catch (e: any) {
    session.notify(e.message);
  }
}
</script>
<template>
  <div class="console">
    <Sidebar :mobile="mobile" :page="page" @logout="logout" />
    <div v-if="mobile" class="scrim" @click="mobile = false" />
    <main class="main">
      <HeaderBar
        :heading="heading"
        :stream-state="streamState"
        @toggle="mobile = !mobile"
      />
      <div class="content">
        <div class="page-heading" :class="{ 'with-shield': page === 'overview' }">
          <ShieldScene
            v-if="page === 'overview'"
            compact
            class="heading-shield"
            :progress="loading ? 0 : 1"
            :state="
              loading || error ? 'idle' : data.criticalHigh > 0 ? 'alert' : 'locked'
            "
          />
          <div>
            <h1>{{ id ? data.repository || data.title || heading : heading }}</h1>
            <p v-if="page === 'overview'">
              <template v-if="loading">최신 검사 결과를 불러오는 중입니다.</template>
              <template v-else-if="data.criticalHigh > 0"
                >미해결 위험 항목 {{ data.openFindings ?? 0 }}건 중
                <strong class="hot">치명·높음 {{ data.criticalHigh }}건</strong>을
                먼저 검토하세요.</template
              >
              <template v-else-if="data.openFindings > 0"
                >미해결 위험 항목 {{ data.openFindings }}건이 있습니다. 치명·높음
                등급은 없습니다.</template
              >
              <template v-else
                >미해결 위험 항목이 없습니다. 검사 범위 밖의 안전까지 보증하지는
                않습니다.</template
              >
            </p>
            <p v-else-if="page === 'findings' && id">
              정적 분석 근거와 정책 대조 결과를 함께 검토합니다.
            </p>
            <p v-else-if="page === 'projects' && id">이 저장소의 검사 이력입니다.</p>
            <p v-else>{{ intro[page] }}</p>
          </div>
          <div class="heading-actions">
            <button @click="load()" :disabled="loading">
              <RefreshCw :size="15" />새로고침</button
            ><button
              v-if="page === 'projects' && !id"
              class="primary"
              @click="projectModal = true"
            >
              <Plus :size="16" />프로젝트 등록
            </button>
          </div>
        </div>
        <div v-if="error" class="error" role="alert">
          {{ error }} <button @click="load()">다시 시도</button>
        </div>
        <div v-if="loading" class="skeleton-grid" aria-label="불러오는 중">
          <div v-for="n in 6" :key="n" class="skeleton" />
        </div>
        <template v-else-if="!error"
          ><template v-if="page === 'overview'"
            ><div class="metrics">
              <article
                v-for="([name, value, icon], i) in metrics"
                :key="String(name)"
                :class="{ hot: (i === 2 || i === 3) && Number(value) > 0 }"
              >
                <span><component :is="icon" :size="16" />{{ name }}</span>
                <strong>{{ value ?? 0 }}</strong>
              </article>
            </div>
            <section class="panel threat-section">
              <div class="panel-title">
                <h2>진단 범위</h2>
                <span>4개 위협 유형을 정적 근거와 MCP 정책 검증으로 확인합니다</span>
              </div>
              <div class="threat-grid">
                <article v-for="p in profiles" :key="p.id">
                  <h3>{{ p.name }}</h3>
                  <p>{{ p.detail }}</p>
                  <div class="chips">
                    <code v-for="r in p.rules" :key="r">{{ r }}</code>
                  </div>
                </article>
              </div>
            </section>
            <div class="charts-grid">
              <section class="panel">
                <div class="panel-title">
                  <h2>위험 항목 발견 추이</h2>
                  <span>최근 14일, KST</span>
                </div>
                <Chart v-if="data.trend?.length" :option="trend" />
                <div v-else class="empty chart-empty">
                  <Activity :size="26" /><strong
                    >아직 검사 이력이 없습니다</strong
                  ><span>첫 검사가 완료되면 일별 추이가 표시됩니다.</span>
                </div>
              </section>
              <section class="panel">
                <div class="panel-title">
                  <h2>위험도 분포</h2>
                  <span>미해결 항목</span>
                </div>
                <Chart v-if="data.distribution?.length" :option="donut" />
                <div v-else class="empty chart-empty">
                  <ShieldCheck :size="26" /><strong
                    >집계할 위험 항목이 없습니다</strong
                  ><span>미해결 항목이 생기면 위험도별로 나눠 보여줍니다.</span>
                </div>
              </section>
            </div></template
          >
          <template
            v-if="
              (page === 'scans' && !id) ||
              page === 'overview' ||
              (page === 'projects' && id)
            "
            ><section class="panel">
              <div class="panel-title">
                <h2>
                  {{ page === "overview" ? "최근 검사" : "검사 이력" }}
                </h2>
                <RouterLink v-if="page === 'overview'" to="/scans"
                  >전체 이력 <ArrowUpRight :size="14" /></RouterLink
                ><span v-else>{{ filtered.length }}건</span>
              </div>
              <div v-if="page !== 'overview'" class="filters">
                <label class="search"
                  ><Search :size="16" /><input
                    v-model="search"
                    aria-label="검색"
                    placeholder="저장소 또는 커밋 검색" /></label
                ><select v-model="status" aria-label="검사 상태">
                  <option value="">모든 상태</option>
                  <option
                    v-for="s in ['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED']"
                    :value="s"
                  >
                    {{ label(s) }}
                  </option></select
                ><input
                  v-model="branch"
                  placeholder="브랜치"
                  aria-label="브랜치"
                /><input
                  v-model="since"
                  type="date"
                  aria-label="시작 날짜"
                /><input
                  v-model="until"
                  type="date"
                  aria-label="종료 날짜"
                /><select v-model="severity" aria-label="위험도">
                  <option value="">모든 위험도</option>
                  <option
                    v-for="s in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']"
                    :value="s"
                  >
                    {{ label(s) }}
                  </option>
                </select>
              </div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>저장소</th>
                      <th>브랜치와 커밋</th>
                      <th>상태</th>
                      <th class="num">위험 항목</th>
                      <th>요청 / 완료</th>
                      <th>실행 방식</th>
                      <th><span class="sr-only">상세</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="s in scanRows" :key="s.id">
                      <td>
                        <RouterLink :to="'/scans/' + s.id"
                          ><strong>{{ s.repository }}</strong
                          ><small class="mono">{{ s.id.slice(0, 8) }}</small></RouterLink
                        >
                      </td>
                      <td>
                        <span class="branch"
                          ><GitBranch :size="13" />{{ s.branch }}</span
                        ><small class="mono">{{
                          s.commitSha?.slice(0, 8)
                        }}</small>
                      </td>
                      <td><Badge :value="s.status" /></td>
                      <td class="num">{{ s.findingCount }}</td>
                      <td>
                        {{ date(s.createdAt)
                        }}<small>{{ date(s.finishedAt) }}</small>
                      </td>
                      <td>
                        <span class="tag">{{ s.triggerType }}</span>
                      </td>
                      <td>
                        <RouterLink
                          class="row-link"
                          :to="'/scans/' + s.id"
                          aria-label="검사 상세"
                          ><ChevronRight :size="16"
                        /></RouterLink>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div v-if="!scanRows.length" class="empty">
                  <ScanLine :size="28" /><strong>표시할 검사가 없습니다</strong
                  ><span
                    >프로젝트를 등록하고 서명된 검사 결과를 전송해
                    시작하세요.</span
                  ><RouterLink to="/projects"
                    >프로젝트 확인 <ArrowUpRight :size="14"
                  /></RouterLink>
                </div>
              </div></section
          ></template>
          <template v-if="page === 'overview'"
            ><section v-if="data.topFindings?.length" class="panel priority">
              <div class="panel-title">
                <h2>먼저 검토할 항목</h2>
                <RouterLink to="/findings"
                  >전체 위험 항목 <ArrowUpRight :size="14"
                /></RouterLink>
              </div>
              <RouterLink
                v-for="f in data.topFindings"
                :to="'/findings/' + f.id"
                class="list-row"
                ><Badge :value="f.severity" /><span class="grow"
                  >{{ f.title
                  }}<small class="mono">{{ f.filePath }}:{{ f.startLine }}</small></span
                ><ChevronRight :size="16"
              /></RouterLink>
            </section>
            <div class="bottom-grid">
              <section class="panel">
                <div class="panel-title">
                  <h2>저장소별 위험 항목</h2>
                </div>
                <RouterLink
                  v-for="p in data.repositoryRisk"
                  :to="'/projects/' + p.id"
                  class="list-row"
                  ><span class="grow"
                    ><FolderGit2 :size="15" /> {{ p.repository }}</span
                  ><strong class="count">{{ p.count }}</strong>
                </RouterLink>
                <p v-if="!data.repositoryRisk?.length" class="empty">
                  등록된 프로젝트가 없습니다.
                </p>
              </section>
              <section class="panel">
                <div class="panel-title">
                  <h2>최근 Agent 이벤트</h2>
                  <RouterLink to="/logs"
                    >로그 보기 <ArrowUpRight :size="14"
                  /></RouterLink>
                </div>
                <div v-for="l in data.recentLogs" class="list-row">
                  <span class="grow"
                    ><strong>{{ l.eventType }}</strong
                    ><small>{{ l.message }}</small></span
                  ><small class="time">{{ date(l.timestamp) }}</small>
                </div>
                <p v-if="!data.recentLogs?.length" class="empty">
                  아직 실행 이벤트가 없습니다.
                </p>
              </section>
            </div>
            <section class="panel" v-if="data.failures?.length">
              <div class="panel-title"><h2>최근 실패한 검사</h2></div>
              <RouterLink
                v-for="s in data.failures"
                :to="'/scans/' + s.id"
                class="list-row"
                ><span class="grow">{{ s.repository }}</span
                ><Badge :value="s.status"
              /></RouterLink>
            </section>
            <div class="evidence-note">
              <ShieldCheck :size="16" />모든 지표는 저장된 검사 결과를 기준으로
              합니다. 탐지 결과가 없더라도 전체 시스템의 안전을 보증하지
              않습니다.
            </div></template
          >
          <template v-if="page === 'projects' && !id"
            ><div class="filters bare">
              <label class="search"
                ><Search :size="16" /><input
                  v-model="search"
                  aria-label="저장소 검색"
                  placeholder="저장소 검색"
              /></label>
            </div>
            <div class="project-grid">
              <RouterLink
                v-for="p in visible"
                :key="p.id"
                :to="'/projects/' + p.id"
                class="panel project-card"
                ><div class="project-top">
                  <FolderGit2 :size="20" /><Badge
                    :value="p.latestStatus || 'NOT_SCANNED'"
                  />
                </div>
                <h2>{{ p.repository }}</h2>
                <p class="mono">github.com/{{ p.repository }}</p>
                <dl class="project-meta">
                  <div>
                    <dt>기본 브랜치</dt>
                    <dd><GitBranch :size="13" /> {{ p.defaultBranch }}</dd>
                  </div>
                  <div>
                    <dt>위험 항목</dt>
                    <dd class="num">{{ p.findingCount || 0 }}</dd>
                  </div>
                  <div>
                    <dt>마지막 검사</dt>
                    <dd>{{ date(p.lastScanAt) }}</dd>
                  </div>
                  <div>
                    <dt>정책 버전</dt>
                    <dd>{{ p.policyVersion }}</dd>
                  </div>
                </dl></RouterLink
              >
            </div>
            <div v-if="!visible.length" class="panel empty">
              <FolderGit2 :size="30" /><strong
                >첫 번째 프로젝트를 연결하세요</strong
              ><span
                >서버의 저장소 허용 목록(Allowlist)에 포함된 저장소를
                등록합니다.</span
              ><button class="primary" @click="projectModal = true">
                프로젝트 등록
              </button>
            </div></template
          >
          <template v-if="page === 'scans' && id"
            ><section class="panel scan-summary">
              <div class="scan-id">
                <Badge :value="data.status" /><span class="branch"
                  ><GitBranch :size="14" /> {{ data.branch }}</span
                ><code>{{ data.commitSha }}</code
                ><a
                  v-if="data.runUrl"
                  :href="data.runUrl"
                  target="_blank"
                  rel="noopener noreferrer"
                  >GitHub Actions 실행 보기 <ArrowUpRight :size="14"
                /></a>
              </div>
              <dl class="summary-grid">
                <div>
                  <dt>요청 시각</dt>
                  <dd>{{ date(data.createdAt) }}</dd>
                </div>
                <div>
                  <dt>완료 시각</dt>
                  <dd>{{ date(data.finishedAt) }}</dd>
                </div>
                <div>
                  <dt>정적 분석</dt>
                  <dd>Semgrep 완료</dd>
                </div>
                <div>
                  <dt>Agent 분석</dt>
                  <dd>{{ label(data.status) }}</dd>
                </div>
                <div>
                  <dt>정책 버전</dt>
                  <dd>{{ data.policyVersion }}</dd>
                </div>
                <div>
                  <dt>분석 모드</dt>
                  <dd>{{ data.analysisMode || "대기 중" }}</dd>
                </div>
              </dl>
            </section>
            <div v-if="data.comparison" class="comparison">
              <span>같은 브랜치의 이전 검사와 비교</span
              ><strong class="added">신규 {{ data.comparison.added }}</strong
              ><strong>미탐지 {{ data.comparison.removed }}</strong
              ><span>유지 {{ data.comparison.unchanged }}</span
              ><small
                >미탐지는 수정 완료를 자동으로 확정하지 않습니다.</small
              >
            </div>
            <ChangeReview :changes="data.changes" :findings="data.findings || []" :scan-status="data.status" />
            <section class="panel">
              <div class="panel-title">
                <h2>탐지 결과</h2>
                <span>코드 위치별 후보 {{ data.findings?.length || 0 }}건</span>
              </div>
              <div v-if="reviewGroups.length" class="review-groups">
                <strong
                  >정책 필드 {{ reviewGroups.length }}종이 탐지되었습니다. 관련
                  위치는 아래에서 각각 확인하세요.</strong
                >
                <span v-for="[field, count] in reviewGroups" :key="field"
                  ><code>{{ field }}</code> {{ count }}곳</span
                >
              </div>
              <RouterLink
                class="finding-row"
                v-for="f in data.findings"
                :to="'/findings/' + f.id"
                ><Badge :value="f.severity" />
                <div>
                  <strong>{{ f.title }}</strong
                  ><small class="mono"
                    ><code>{{ f.ruleId }}</code>{{ f.filePath }}:{{
                      f.startLine
                    }}</small
                  >
                </div>
                <Badge :value="f.evidenceStatus" /><ChevronRight :size="16"
              /></RouterLink>
              <div v-if="!data.findings?.length" class="empty">
                탐지된 항목이 없습니다. 검사 완료 상태를 함께 확인하세요.
              </div>
            </section>
            <section class="panel">
              <div class="panel-title"><h2>실행 타임라인</h2></div>
              <ol class="timeline">
                <li v-for="l in data.logs">
                  <span class="grow"
                    ><strong>{{ l.eventType }}</strong
                    ><small>{{ l.message }}</small></span
                  ><small class="time">{{ date(l.timestamp) }}</small>
                </li>
              </ol>
            </section></template
          >
          <template v-if="page === 'findings' && id"
            ><div class="detail-header">
              <Badge :value="data.severity" /><Badge
                :value="data.evidenceStatus"
              /><Badge :value="data.status" /><code>{{ data.ruleId }}</code
              ><label class="inline-select"
                >검토 상태<select
                  :value="data.status"
                  @change="review(($event.target as HTMLSelectElement).value)"
                  aria-label="검토 상태 변경"
                >
                  <option v-for="s in ['OPEN', 'REVIEWING', 'RESOLVED']" :value="s">
                    {{ label(s) }}
                  </option>
                </select></label
              >
            </div>
            <div class="tabs" role="tablist">
              <button
                v-for="(name, t) in tabs"
                role="tab"
                :aria-selected="tab === t"
                @click="tab = t"
                :class="{ selected: tab === t }"
              >
                {{ name }}
              </button>
            </div>
            <div class="detail-grid">
              <section class="panel detail-panel">
                <h2>정적 분석 근거</h2>
                <p class="mono file-path">
                  {{ data.filePath }}:{{ data.startLine }}–{{ data.endLine }}
                </p>
                <pre>{{ data.maskedCodeEvidence || "코드 원문 미제공" }}</pre>
                <dl>
                  <dt>증거 수준</dt>
                  <dd>{{ label(data.evidenceStatus) }}</dd>
                  <dt>신뢰 수준</dt>
                  <dd>{{ data.confidence }}<small v-if="data.analysis?.confidenceBasis">{{ data.analysis.confidenceBasis }}</small></dd>
                  <dt>정책</dt>
                  <dd>{{ data.policyVersion }}</dd>
                  <dt>커밋</dt>
                  <dd class="mono">{{ data.commitSha }}</dd>
                </dl>
                <section v-if="data.analysis?.facts?.length" class="review-evidence">
                  <h3>확인된 정적 근거</h3>
                  <article v-for="fact in data.analysis.facts" :key="fact.id">
                    <strong>{{ fact.id }} <span v-if="data.analysis.citedFactIds?.includes(fact.id)" class="tag">리뷰에 인용됨</span></strong>
                    <p>{{ fact.text }}</p>
                    <small v-if="fact.filePath" class="mono">{{ fact.filePath }}:{{ fact.line }}</small>
                    <small v-if="fact.section">{{ fact.section }}, {{ fact.page }}쪽</small>
                  </article>
                </section>
                <RouterLink class="text-link" :to="'/scans/' + data.scanId"
                  >검사 상세로 이동 <ArrowUpRight :size="14"
                /></RouterLink>
              </section>
              <section class="panel detail-panel">
                <template v-if="tab === 'Overview' || tab === 'AI Analysis'"
                  ><div v-if="data.analysis?.policyComparison" class="review-policy">
                    <strong class="mono">{{ data.analysis.policyComparison.entity }}.{{ data.analysis.policyComparison.field }}</strong>
                    <p>정책 대조: {{ policyLabels[data.analysis.policyComparison.inventoryStatus] }}</p>
                    <small>별도 승인 기록 미확인, 런타임 검증 미수행</small>
                  </div>
                  <div class="verdict red">
                    <h2><ShieldAlert :size="18" />잠재 위험</h2>
                    <p class="threat-name">{{ data.analysis?.threatProfile }}</p>
                    <p>{{ data.analysis?.red || "분석 결과 대기 중" }}</p>
                  </div>
                  <div class="verdict blue">
                    <h2><ShieldCheck :size="18" />근거 검토와 불확실성</h2>
                    <p>{{ data.analysis?.blue || "분석 결과 대기 중" }}</p>
                  </div>
                  <section v-if="data.analysis?.orchestration" class="review-evidence">
                    <h3>Agent 도구 선택</h3>
                    <p>{{ data.analysis.orchestration.selectionMode }} · {{ data.analysis.orchestration.turns }}턴</p>
                    <ol><li v-for="step in data.analysis.orchestration.trace" :key="step.turn">{{ step.turn }} · {{ step.tool }} · {{ step.ruleId || '' }} · {{ step.status }} · {{ step.mode }}</li></ol>
                    <small>LLM은 모델 선택, RULE_BASED와 LLM_FALLBACK은 코드 기반 선택입니다.</small>
                  </section>
                  <p v-if="data.analysis?.fallbackReason">LLM 대체 사유: {{ data.analysis.fallbackReason }}</p>
                  <small v-if="data.analysis?.contextBudget">모델 호출 {{ data.analysis.contextBudget.calls }}회 · 입력 예산 상한 사용 {{ data.analysis.contextBudget.maxInputBound }} · 누적 예약 {{ data.analysis.contextBudget.reservedTokens }}</small>
                  <section v-if="data.analysis?.unknowns?.length" class="review-evidence">
                    <h3>추가 확인이 필요한 사항</h3>
                    <ul><li v-for="item in data.analysis.unknowns" :key="item">{{ item }}</li></ul>
                  </section>
                  <small
                    >분석 모드: {{ data.analysis?.mode || "대기" }}<span v-if="data.analysis?.model"> ({{ data.analysis.model }})</span></small
                  ></template
                ><template v-if="tab === 'Code Evidence'"
                  ><h2>코드 근거 처리</h2>
                  <p>
                    문자열 리터럴과 주석을 제거한 정적 분석 근거입니다. 런타임
                    동작과 실제 저장 경로는 별도 확인이 필요할 수 있습니다.
                  </p>
                  <code>{{ data.fingerprint }}</code></template
                ><template v-if="tab === 'Remediation'"
                  ><h2>개선 권고</h2>
                  <p>
                    {{
                      data.analysis?.remediation ||
                      "검증된 개선 권고가 아직 없습니다."
                    }}
                  </p>
                  <pre v-if="data.analysis?.example">{{
                    data.analysis.example
                  }}</pre>
                  <small
                    >예시는 수정 방향을 설명하며 원본 코드나 적용된 패치가
                    아닙니다.</small
                  ></template
                ><template v-if="tab === 'Security References'"
                  ><h2>검색된 근거</h2>
                  <article
                    class="reference"
                    v-for="r in data.analysis?.references"
                  >
                    <div class="reference-head">
                      <Badge :value="r.documentType" /><span class="tag">{{ data.analysis?.citedReferenceIds?.includes(r.chunkId) ? "LLM이 인용한 근거" : "검색된 참고 근거" }}</span>
                    </div>
                    <h3><code>{{ r.sectionId }}</code> {{ r.sectionTitle }}</h3>
                    <small
                      >{{ r.documentId }} @{{ r.documentVersion }},
                      {{ r.pageNumber }}쪽</small
                    >
                    <p>{{ r.content }}</p>
                    <small>{{ r.source }}</small>
                  </article>
                  <p v-if="!data.analysis?.references?.length">
                    검색된 근거가 없습니다. 출처를 추정하지 않습니다.
                  </p></template
                ><template v-if="tab === 'Activity'"
                  ><h2>활동 기록</h2>
                  <div class="list-row" v-for="a in data.activity">
                    <span class="grow">{{ a.message }}</span
                    ><small class="time">{{ date(a.timestamp) }}</small>
                  </div></template
                >
              </section>
            </div></template
          >
          <template v-if="page === 'policies'"
            ><div class="filters bare">
              <label class="search"
                ><Search :size="16" /><input
                  v-model="search"
                  aria-label="정책 검색"
                  placeholder="문서, 조항, 원문 검색"
              /></label>
            </div>
            <div class="policy-grid">
              <button
                v-for="p in visible"
                class="panel policy-card"
                @click="drawer = p"
              >
                <span class="policy-head"
                  ><code>{{ p.sectionId }}</code><Badge :value="p.documentType"
                /></span>
                <h2>{{ p.sectionTitle }}</h2>
                <p>{{ p.content?.slice(0, 180) }}…</p>
                <small
                  >{{ p.documentId }} v{{ p.documentVersion }},
                  {{ p.pageNumber }}쪽</small
                ><span class="text-link"
                  >조항 보기 <ArrowUpRight :size="14"
                /></span>
              </button>
            </div>
            <div v-if="!visible.length" class="panel empty">
              색인된 정책이 없습니다. RAG 색인 작업의 완료 여부를 확인하세요.
            </div></template
          >
          <template
            v-if="['findings', 'logs', 'approvals'].includes(page) && !id"
            ><section class="panel">
              <div class="filters">
                <label class="search"
                  ><Search :size="16" /><input
                    v-model="search"
                    aria-label="검색"
                    placeholder="검색어를 입력하세요" /></label
                ><select
                  v-if="page !== 'logs'"
                  v-model="status"
                  aria-label="상태 필터"
                >
                  <option value="">모든 상태</option>
                  <option
                    v-for="s in page === 'approvals'
                      ? ['PENDING', 'APPROVED', 'REJECTED', 'EXECUTED']
                      : ['OPEN', 'REVIEWING', 'RESOLVED']"
                    :value="s"
                  >
                    {{ label(s) }}
                  </option></select
                ><select
                  v-if="page === 'findings'"
                  v-model="severity"
                  aria-label="위험도"
                >
                  <option value="">모든 위험도</option>
                  <option
                    v-for="s in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']"
                    :value="s"
                  >
                    {{ label(s) }}
                  </option></select
                ><template v-if="page === 'logs'"
                  ><select v-model="logLevel" aria-label="로그 레벨">
                    <option value="">모든 레벨</option>
                    <option>INFO</option>
                    <option>WARN</option>
                    <option>ERROR</option></select
                  ><input
                    type="date"
                    v-model="since"
                    aria-label="시작 날짜"
                  /><input
                    type="date"
                    v-model="until"
                    aria-label="종료 날짜"
                  /><button @click="oldestFirst = !oldestFirst">
                    {{ oldestFirst ? "오래된 순" : "최신순" }}
                  </button></template
                >
              </div>
              <div v-if="page === 'findings'">
                <RouterLink
                  v-for="f in visible"
                  :to="'/findings/' + f.id"
                  class="finding-row"
                  ><Badge :value="f.severity" />
                  <div>
                    <strong>{{ f.title }}</strong
                    ><small class="meta"
                      ><span>{{ f.repository }}</span
                      ><span class="mono"
                        >{{ f.filePath }}:{{ f.startLine }}</span
                      ></small
                    >
                  </div>
                  <Badge :value="f.status" /><ChevronRight :size="16"
                /></RouterLink>
              </div>
              <div v-if="page === 'logs'" class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>시각 {{ oldestFirst ? "↑" : "↓" }}</th>
                      <th>이벤트 / 컴포넌트</th>
                      <th>레벨</th>
                      <th>메시지</th>
                      <th>검사 / 추적 ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="l in visible">
                      <td>{{ date(l.timestamp) }}</td>
                      <td>
                        <strong>{{ l.eventType }}</strong><small>{{ l.component }}</small>
                      </td>
                      <td><Badge :value="l.level" /></td>
                      <td class="message">{{ l.message }}</td>
                      <td>
                        <RouterLink class="mono" :to="'/scans/' + l.scanId">{{
                          l.scanId?.slice(0, 8)
                        }}</RouterLink
                        ><small class="mono">{{
                          l.traceId?.slice(0, 8)
                        }}</small>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="page === 'approvals'">
                <button
                  v-for="a in visible"
                  class="list-row approval-row"
                  @click="drawer = a"
                >
                  <ClipboardCheck :size="18" /><span class="grow"
                    ><strong>{{ a.action }}</strong
                    ><small class="meta"
                      ><span>{{ a.repository }}</span
                      ><span class="mono">{{ a.commitSha?.slice(0, 8) }}</span
                      ><span>{{ date(a.createdAt) }}</span></small
                    ></span
                  ><Badge :value="a.status" /><ChevronRight :size="16" />
                </button>
              </div>
              <div v-if="!visible.length" class="empty">
                <ShieldCheck :size="28" /><strong>표시할 항목이 없습니다</strong
                ><span>검사 결과가 저장되면 이곳에서 확인할 수 있습니다.</span>
              </div>
            </section></template
          >
          <div v-if="page !== 'overview' && !id" class="pagination">
            <span
              >{{ filtered.length }}개 항목, {{ current }} / {{ pages }}
              페이지</span
            ><button :disabled="current <= 1" @click="current--">이전</button
            ><button :disabled="current >= pages" @click="current++">
              다음
            </button>
          </div></template
        >
        <footer>정적 분석 증거와 검색된 정책 조항에 기반한 진단입니다.</footer>
      </div>
    </main>
    <Transition name="drawer">
      <div v-if="drawer" class="overlay" @click.self="drawer = null">
        <section
          class="drawer"
          role="dialog"
          aria-modal="true"
          aria-label="상세 정보"
        >
          <button class="close" @click="drawer = null" aria-label="닫기">
            <X :size="20" />
          </button>
          <template v-if="page === 'policies'"
            ><span class="policy-head"
              ><code>{{ drawer.sectionId }}</code
              ><Badge :value="drawer.documentType"
            /></span>
            <h2>{{ drawer.sectionTitle }}</h2>
            <p class="preserve">{{ drawer.content }}</p>
            <small>{{ drawer.source }}, {{ drawer.pageNumber }}쪽</small>
            <h3>관련 위험 항목</h3>
            <RouterLink class="text-link" :to="'/findings'" @click="drawer = null"
              >위험 항목에서 정책 근거 확인 <ArrowUpRight :size="14"
            /></RouterLink></template
          ><template v-else
            ><h2>승인 요청</h2>
            <Badge :value="drawer.status" />
            <h3>{{ drawer.action }}</h3>
            <dl>
              <dt>저장소</dt>
              <dd>{{ drawer.repository }}</dd>
              <dt>커밋</dt>
              <dd class="mono">{{ drawer.commitSha }}</dd>
              <dt>정책</dt>
              <dd>{{ drawer.policyVersion }}</dd>
            </dl>
            <RouterLink
              class="text-link"
              :to="'/scans/' + drawer.scanId"
              @click="drawer = null"
              >관련 검사와 근거 확인 <ArrowUpRight :size="14"
            /></RouterLink>
            <p class="note">
              승인하면 CSI 내부 보안 검토 이슈가 생성됩니다. 코드 수정이나 운영
              배포는 수행하지 않습니다.
            </p>
            <div v-if="drawer.status === 'PENDING'" class="drawer-actions">
              <button @click="decide(drawer, 'REJECTED')">거절</button
              ><button class="primary" @click="decide(drawer, 'APPROVED')">
                승인
              </button>
            </div>
            <p v-else>
              처리자 {{ drawer.decidedBy || "—" }}, {{ date(drawer.decidedAt) }}
            </p></template
          >
        </section>
      </div>
    </Transition>
    <Transition name="fade">
      <div v-if="projectModal" class="overlay center" @click.self="projectModal = false">
        <form class="modal" @submit.prevent="addProject">
          <button
            type="button"
            class="close"
            @click="projectModal = false"
            aria-label="닫기"
          >
            <X :size="20" />
          </button>
          <h2>프로젝트 등록</h2>
          <p>허용 목록에 있는 GitHub 저장소를 연결합니다.</p>
          <label
            >저장소<input
              v-model="repo"
              required
              pattern="[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
              placeholder="organization/repository" /></label
          ><label
            >기본 브랜치<input
              v-model="defaultBranch"
              required
              placeholder="develop" /></label
          ><button class="primary">프로젝트 등록</button>
        </form>
      </div>
    </Transition>
  </div>
</template>
