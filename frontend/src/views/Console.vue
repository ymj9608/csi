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
const route = useRoute(),
  router = useRouter(),
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
const page = computed(() => route.path.split("/")[1] || "overview"),
  id = computed(() => route.path.split("/")[2]);
const heading = computed(
  () => nav.find((n) => n[0] === "/" + page.value)?.[1] || "Security overview",
);
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
  ["Critical / High", data.value.criticalHigh, Activity],
  ["검토 대기", data.value.pendingApprovals, ClipboardCheck],
]);
const profiles = [
  {
    id: "T1",
    name: "오프라인 비밀번호 추측",
    rules: "SEC-01 · SEC-02 · SEC-04",
    detail: "평문 · 빠른 해시 · bcrypt 비용",
  },
  {
    id: "T2",
    name: "사전 계산 결과 재사용",
    rules: "SEC-03",
    detail: "고정 Salt · 사용자별 고유성",
  },
  {
    id: "T3",
    name: "로그를 통한 비밀정보 유출",
    rules: "SEC-05",
    detail: "비밀번호 · 인증 토큰 · 개인정보",
  },
  {
    id: "T4",
    name: "미승인 개인정보 처리",
    rules: "POL-01",
    detail: "승인 항목 · 신규 필드 · 처리 경로",
  },
];
const palette = ["#fb7185", "#fb923c", "#fbbf24", "#52c5d5"];
const donut = computed(() => ({
  animation: false,
  color: palette,
  tooltip: { trigger: "item" },
  series: [
    {
      type: "pie",
      radius: ["64%", "83%"],
      center: ["50%", "48%"],
      label: { show: false },
      data: (data.value.distribution || []).map((x: any) => ({
        name: x.severity,
        value: x.count,
        itemStyle: {
          color: (
            {
              CRITICAL: "#fb7185",
              HIGH: "#fb923c",
              MEDIUM: "#fbbf24",
              LOW: "#52c5d5",
            } as Record<string, string>
          )[x.severity],
        },
      })),
    },
  ],
  legend: {
    bottom: 0,
    textStyle: { color: "#94a3b8" },
    itemWidth: 8,
    itemHeight: 8,
  },
}));
const trend = computed(() => ({
  animation: false,
  color: ["#51c7d8"],
  tooltip: { trigger: "axis" },
  grid: { left: 40, right: 20, top: 25, bottom: 30 },
  xAxis: {
    type: "category",
    data: (data.value.trend || []).map((x: any) => x.day),
    axisLine: { lineStyle: { color: "#29445e" } },
    axisLabel: { color: "#94a3b8" },
  },
  yAxis: {
    type: "value",
    minInterval: 1,
    splitLine: { lineStyle: { color: "#203750" } },
    axisLabel: { color: "#94a3b8" },
  },
  series: [
    {
      type: "line",
      smooth: false,
      data: (data.value.trend || []).map((x: any) => x.count),
      areaStyle: { color: "rgba(81,199,216,.09)" },
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
      const [findings, logs, comparison] = await Promise.all([
        api(path + "/findings"),
        api(path + "/logs"),
        api(path + "/comparison"),
      ]);
      if (key === request)
        data.value = { ...result, findings, logs, comparison };
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
    <main class="main">
      <HeaderBar
        :heading="heading"
        :stream-state="streamState"
        @toggle="mobile = !mobile"
      />
      <div class="content">
        <div class="page-heading">
          <div>
            <div class="eyebrow">CYBER SECURITY INSPECTOR</div>
            <h1>
              {{ id ? data.repository || data.title || heading : heading
              }}<span v-if="page === 'overview'" class="heading-dot" />
            </h1>
            <p>
              {{
                page === "overview"
                  ? "코드의 변화부터 정책의 근거까지, 보안 현황을 한눈에 확인하세요."
                  : page === "scans"
                    ? "커밋별 검사 진행 상황과 진단 근거를 추적합니다."
                    : "확인 가능한 근거를 바탕으로 보안 업무를 관리합니다."
              }}
            </p>
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
                v-for="[label, value, icon] in metrics"
                :key="String(label)"
              >
                <div>{{ label }}<component :is="icon" :size="18" /></div>
                <strong>{{ value ?? 0 }}</strong
                ><small>현재 워크스페이스 기준</small>
              </article>
            </div>
            <section class="threat-section">
              <div class="panel-title">
                <h2>고정 진단 범위 · 4개 위협 유형</h2>
                <span>정적 증거 + MCP 정책 검증</span>
              </div>
              <div class="threat-grid">
                <article v-for="p in profiles" :key="p.id">
                  <span class="eyebrow">{{ p.id }} / DEFENSE REVIEW</span>
                  <h3>{{ p.name }}</h3>
                  <p>{{ p.detail }}</p>
                  <code>{{ p.rules }}</code>
                </article>
              </div>
            </section>
            <div class="charts-grid">
              <section class="panel">
                <div class="panel-title">
                  <h2>위험 항목 발견 추이</h2>
                  <span>최근 14일 · KST</span>
                </div>
                <Chart v-if="data.trend?.length" :option="trend" />
                <div v-else class="empty chart-empty">
                  <Activity :size="28" /><strong
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
                  <div class="empty-ring">
                    <strong>0</strong><small>FINDINGS</small>
                  </div>
                  <span>집계할 위험 항목이 없습니다.</span>
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
                  {{ page === "overview" ? "최근 검사 현황" : "검사 이력" }}
                </h2>
                <RouterLink v-if="page === 'overview'" to="/scans"
                  >전체 이력 <ArrowUpRight :size="14" /></RouterLink
                ><span v-else>{{ filtered.length }} scans</span>
              </div>
              <div v-if="page !== 'overview'" class="filters">
                <label class="search"
                  ><Search :size="16" /><input
                    v-model="search"
                    placeholder="Repository · Commit 검색" /></label
                ><select v-model="status" aria-label="검사 상태">
                  <option value="">모든 상태</option>
                  <option
                    v-for="s in ['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED']"
                  >
                    {{ s }}
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
                  <option v-for="s in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']">
                    {{ s }}
                  </option>
                </select>
              </div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>REPOSITORY / SCAN</th>
                      <th>BRANCH / COMMIT</th>
                      <th>STATUS</th>
                      <th>FINDINGS</th>
                      <th>REQUESTED / FINISHED</th>
                      <th>TRIGGER</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="s in scanRows" :key="s.id">
                      <td>
                        <RouterLink :to="'/scans/' + s.id"
                          ><strong>{{ s.repository }}</strong
                          ><small>{{ s.id.slice(0, 8) }}</small></RouterLink
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
                      <td>{{ s.findingCount }}</td>
                      <td>
                        {{ date(s.createdAt)
                        }}<small>{{ date(s.finishedAt) }}</small>
                      </td>
                      <td>
                        <span class="badge">{{ s.triggerType }}</span>
                      </td>
                      <td>
                        <RouterLink
                          :to="'/scans/' + s.id"
                          aria-label="검사 상세"
                          ><ArrowUpRight :size="16"
                        /></RouterLink>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div v-if="!scanRows.length" class="empty">
                  <ScanLine :size="30" /><strong>표시할 검사가 없습니다</strong
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
            ><div class="bottom-grid">
              <section class="panel">
                <div class="panel-title">
                  <h2>Repository별 위험 항목</h2>
                  <FolderGit2 :size="17" />
                </div>
                <div v-for="p in data.repositoryRisk" class="list-row">
                  <RouterLink :to="'/projects/' + p.id">{{
                    p.repository
                  }}</RouterLink
                  ><strong>{{ p.count }}</strong>
                </div>
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
                  <span
                    ><strong>{{ l.eventType }}</strong
                    ><small>{{ l.message }}</small></span
                  ><small>{{ date(l.timestamp) }}</small>
                </div>
                <p v-if="!data.recentLogs?.length" class="empty">
                  아직 실행 이벤트가 없습니다.
                </p>
              </section>
            </div>
            <section class="panel" v-if="data.failures?.length">
              <div class="panel-title"><h2>최근 실패 검사</h2></div>
              <RouterLink
                v-for="s in data.failures"
                :to="'/scans/' + s.id"
                class="list-row"
                >{{ s.repository }}<Badge :value="s.status"
              /></RouterLink>
            </section>
            <section v-if="data.topFindings?.length" class="panel">
              <div class="panel-title"><h2>우선 검토 항목</h2></div>
              <RouterLink
                v-for="f in data.topFindings"
                :to="'/findings/' + f.id"
                class="list-row"
                ><span
                  >{{ f.title
                  }}<small>{{ f.filePath }}:{{ f.startLine }}</small></span
                ><Badge :value="f.severity"
              /></RouterLink>
            </section>
            <div class="evidence-note">
              <ShieldCheck :size="16" />모든 지표는 저장된 검사 결과를 기준으로
              합니다. 탐지 결과가 없더라도 전체 시스템의 안전을 보증하지
              않습니다.
            </div></template
          >
          <template v-if="page === 'projects' && !id"
            ><div class="filters">
              <label class="search"
                ><Search :size="16" /><input
                  v-model="search"
                  placeholder="Repository 검색"
              /></label>
            </div>
            <div class="project-grid">
              <RouterLink
                v-for="p in visible"
                :key="p.id"
                :to="'/projects/' + p.id"
                class="panel project-card"
                ><div class="project-top">
                  <FolderGit2 :size="24" /><ArrowUpRight :size="18" />
                </div>
                <h2>{{ p.repository }}</h2>
                <p class="mono">github.com/{{ p.repository }}</p>
                <div class="list-row">
                  <span><GitBranch :size="13" /> {{ p.defaultBranch }}</span
                  ><Badge :value="p.latestStatus || 'NOT_SCANNED'" />
                </div>
                <div class="project-meta">
                  <span
                    >마지막 검사<small>{{ date(p.lastScanAt) }}</small></span
                  ><span
                    >위험 항목<small>{{ p.findingCount || 0 }}</small></span
                  >
                </div>
                <p>정책 {{ p.policyVersion }}</p></RouterLink
              >
            </div>
            <div v-if="!visible.length" class="panel empty">
              <FolderGit2 :size="32" /><strong
                >첫 번째 프로젝트를 연결하세요</strong
              ><span
                >서버의 Repository Allowlist에 포함된 저장소를 등록합니다.</span
              ><button class="primary" @click="projectModal = true">
                프로젝트 등록
              </button>
            </div></template
          >
          <template v-if="page === 'scans' && id"
            ><section class="panel scan-summary">
              <Badge :value="data.status" /><span
                ><GitBranch :size="14" /> {{ data.branch }}</span
              ><code>{{ data.commitSha }}</code
              ><a
                v-if="data.runUrl"
                :href="data.runUrl"
                target="_blank"
                rel="noopener noreferrer"
                >GitHub Actions <ArrowUpRight :size="14"
              /></a>
              <div class="summary-grid">
                <span
                  >요청 시각<strong>{{ date(data.createdAt) }}</strong></span
                ><span
                  >완료 시각<strong>{{ date(data.finishedAt) }}</strong></span
                ><span>정적 분석<strong>완료 · Semgrep</strong></span
                ><span
                  >Agent 분석<strong>{{
                    data.status === "COMPLETED" ? "완료" : data.status
                  }}</strong></span
                ><span
                  >정책 버전<strong>{{ data.policyVersion }}</strong></span
                ><span
                  >분석 모드<strong>{{
                    data.analysisMode || "대기 중"
                  }}</strong></span
                >
              </div>
            </section>
            <div v-if="data.comparison" class="comparison">
              <span>이전 동일 브랜치 검사 대비</span
              ><strong>신규 {{ data.comparison.added }}</strong
              ><strong>미탐지 {{ data.comparison.removed }}</strong
              ><span>유지 {{ data.comparison.unchanged }}</span
              ><small
                >미탐지는 수정 완료의 자동 확정을 의미하지 않습니다.</small
              >
            </div>
            <section class="panel">
              <div class="panel-title">
                <h2>탐지 결과 · 코드 위치별 후보</h2>
                <span>{{ data.findings?.length || 0 }} findings</span>
              </div>
              <div v-if="reviewGroups.length" class="review-groups">
                <strong>정책 필드 {{ reviewGroups.length }}종 · 관련 위치는 아래에서 각각 확인</strong>
                <span v-for="[field, count] in reviewGroups" :key="field">{{ field }} · {{ count }}곳</span>
              </div>
              <RouterLink
                class="finding-row"
                v-for="f in data.findings"
                :to="'/findings/' + f.id"
                ><Badge :value="f.severity" />
                <div>
                  <strong>{{ f.title }}</strong
                  ><small class="mono"
                    >{{ f.ruleId }} · {{ f.filePath }}:{{ f.startLine }}</small
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
              <div class="list-row" v-for="l in data.logs">
                <span
                  >{{ l.eventType }}<small>{{ l.message }}</small></span
                ><span>{{ date(l.timestamp) }}</span>
              </div>
            </section></template
          >
          <template v-if="page === 'findings' && id"
            ><div class="detail-header">
              <Badge :value="data.severity" /><Badge
                :value="data.evidenceStatus"
              /><Badge :value="data.status" /><code>{{ data.ruleId }}</code
              ><select
                :value="data.status"
                @change="review(($event.target as HTMLSelectElement).value)"
                aria-label="검토 상태 변경"
              >
                <option>OPEN</option>
                <option>REVIEWING</option>
                <option>RESOLVED</option>
              </select>
            </div>
            <div class="tabs">
              <button
                v-for="t in [
                  'Overview',
                  'Code Evidence',
                  'AI Analysis',
                  'Remediation',
                  'Security References',
                  'Activity',
                ]"
                @click="tab = t"
                :class="{ selected: tab === t }"
              >
                {{ t }}
              </button>
            </div>
            <div class="detail-grid">
              <section class="panel detail-panel">
                <h2>정적 분석 근거</h2>
                <p class="mono">
                  {{ data.filePath }}:{{ data.startLine }}–{{ data.endLine }}
                </p>
                <pre>{{ data.maskedCodeEvidence || "코드 원문 미제공" }}</pre>
                <dl>
                  <dt>증거 수준</dt>
                  <dd>{{ data.evidenceStatus }}</dd>
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
                    <strong>{{ fact.id }} <small v-if="data.analysis.citedFactIds?.includes(fact.id)">리뷰에 인용됨</small></strong>
                    <p>{{ fact.text }}</p>
                    <small v-if="fact.filePath" class="mono">{{ fact.filePath }}:{{ fact.line }}</small>
                    <small v-if="fact.section">{{ fact.section }} · p.{{ fact.page }}</small>
                  </article>
                </section>
                <RouterLink :to="'/scans/' + data.scanId"
                  >검사 상세로 이동 <ArrowUpRight :size="14"
                /></RouterLink>
              </section>
              <section class="panel detail-panel">
                <template v-if="tab === 'Overview' || tab === 'AI Analysis'"
                  ><div v-if="data.analysis?.policyComparison" class="review-policy">
                    <strong>{{ data.analysis.policyComparison.entity }}.{{ data.analysis.policyComparison.field }}</strong>
                    <p>정책 대조: {{ policyLabels[data.analysis.policyComparison.inventoryStatus] }}</p>
                    <small>별도 승인 기록 미확인 · 런타임 검증 미수행</small>
                  </div><span class="eyebrow">RED ANALYSIS</span>
                  <h2>잠재 위험</h2>
                  <p class="threat-name">{{ data.analysis?.threatProfile }}</p>
                  <p>{{ data.analysis?.red || "분석 결과 대기 중" }}</p>
                  <span class="eyebrow blue">BLUE VERIFICATION</span>
                  <h2>근거 검토와 불확실성</h2>
                  <p>{{ data.analysis?.blue || "분석 결과 대기 중" }}</p>
                  <section v-if="data.analysis?.unknowns?.length" class="review-evidence">
                    <h3>추가 확인이 필요한 사항</h3>
                    <ul><li v-for="item in data.analysis.unknowns" :key="item">{{ item }}</li></ul>
                  </section>
                  <small
                    >분석 모드: {{ data.analysis?.mode || "대기" }}<span v-if="data.analysis?.model"> · {{ data.analysis.model }}</span></small
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
                    <Badge :value="r.documentType" />
                    <h3>{{ r.sectionId }} · {{ r.sectionTitle }}</h3><small>{{ data.analysis?.citedReferenceIds?.includes(r.chunkId) ? "LLM이 인용한 근거" : "검색된 참고 근거" }}</small>
                    <small
                      >{{ r.documentId }} @{{ r.documentVersion }} · p.{{
                        r.pageNumber
                      }}</small
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
                    <span>{{ a.message }}</span
                    ><small>{{ date(a.timestamp) }}</small>
                  </div></template
                >
              </section>
            </div></template
          >
          <template v-if="page === 'policies'"
            ><div class="filters">
              <label class="search"
                ><Search :size="16" /><input
                  v-model="search"
                  placeholder="문서 · 조항 · 원문 검색"
              /></label>
            </div>
            <div class="policy-grid">
              <button
                v-for="p in visible"
                class="panel policy-card"
                @click="drawer = p"
              >
                <Badge :value="p.documentType" />
                <h2>{{ p.sectionId }} · {{ p.sectionTitle }}</h2>
                <p>{{ p.content?.slice(0, 180) }}…</p>
                <small
                  >{{ p.documentId }} · v{{ p.documentVersion }} · p.{{
                    p.pageNumber
                  }}</small
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
                  >
                    {{ s }}
                  </option></select
                ><select
                  v-if="page === 'findings'"
                  v-model="severity"
                  aria-label="위험도"
                >
                  <option value="">모든 위험도</option>
                  <option v-for="s in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']">
                    {{ s }}
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
                    ><small
                      >{{ f.repository }} · {{ f.filePath }}:{{
                        f.startLine
                      }}</small
                    >
                  </div>
                  <Badge :value="f.status" /><ChevronRight :size="16"
                /></RouterLink>
              </div>
              <div v-if="page === 'logs'" class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>TIMESTAMP {{ oldestFirst ? "↑" : "↓" }}</th>
                      <th>EVENT / COMPONENT</th>
                      <th>LEVEL</th>
                      <th>MESSAGE</th>
                      <th>SCAN / TRACE</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="l in visible">
                      <td>{{ date(l.timestamp) }}</td>
                      <td>
                        {{ l.eventType }}<small>{{ l.component }}</small>
                      </td>
                      <td><Badge :value="l.level" /></td>
                      <td>{{ l.message }}</td>
                      <td>
                        <RouterLink :to="'/scans/' + l.scanId">{{
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
                  <ClipboardCheck :size="20" /><span
                    ><strong>{{ a.action }}</strong
                    ><small
                      >{{ a.repository }} · {{ a.commitSha?.slice(0, 8) }} ·
                      {{ date(a.createdAt) }}</small
                    ></span
                  ><Badge :value="a.status" /><ChevronRight :size="16" />
                </button>
              </div>
              <div v-if="!visible.length" class="empty">
                <ShieldCheck :size="30" /><strong>표시할 항목이 없습니다</strong
                ><span>검사 결과가 저장되면 이곳에서 확인할 수 있습니다.</span>
              </div>
            </section></template
          >
          <div v-if="page !== 'overview' && !id" class="pagination">
            <span
              >{{ filtered.length }}개 항목 · 페이지 {{ current }} /
              {{ pages }}</span
            ><button :disabled="current <= 1" @click="current--">이전</button
            ><button :disabled="current >= pages" @click="current++">
              다음
            </button>
          </div></template
        >
        <footer>
          CSI <span>CYBER SECURITY INSPECTOR</span
          ><small>정적 분석 증거와 검색된 정책에 기반한 진단</small>
        </footer>
      </div>
    </main>
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
        <h2>{{ drawer.sectionId || "승인 요청" }}</h2>
        <template v-if="page === 'policies'"
          ><Badge :value="drawer.documentType" />
          <h3>{{ drawer.sectionTitle }}</h3>
          <p class="preserve">{{ drawer.content }}</p>
          <small>{{ drawer.source }} · p.{{ drawer.pageNumber }}</small>
          <h3>관련 위험 항목</h3>
          <RouterLink :to="'/findings'" @click="drawer = null"
            >위험 항목에서 정책 근거 확인</RouterLink
          ></template
        ><template v-else
          ><Badge :value="drawer.status" />
          <h3>{{ drawer.action }}</h3>
          <p>{{ drawer.repository }}</p>
          <code>{{ drawer.commitSha }}</code>
          <p>정책 {{ drawer.policyVersion }}</p>
          <RouterLink :to="'/scans/' + drawer.scanId" @click="drawer = null"
            >관련 검사 및 근거 확인</RouterLink
          >
          <p>
            승인은 CSI 내부 보안 검토 이슈를 생성합니다. 코드 수정이나 운영
            배포는 수행하지 않습니다.
          </p>
          <div v-if="drawer.status === 'PENDING'" class="heading-actions">
            <button @click="decide(drawer, 'REJECTED')">거절</button
            ><button class="primary" @click="decide(drawer, 'APPROVED')">
              승인
            </button>
          </div>
          <p v-else>
            처리자: {{ drawer.decidedBy || "—" }} · {{ date(drawer.decidedAt) }}
          </p></template
        >
      </section>
    </div>
    <div v-if="projectModal" class="overlay" @click.self="projectModal = false">
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
        <p>허용된 GitHub Repository를 연결합니다.</p>
        <label
          >Repository<input
            v-model="repo"
            required
            pattern="[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
            placeholder="organization/repository" /></label
        ><label
          >기본 브랜치<input
            v-model="defaultBranch"
            required
            placeholder="develop" /></label
        ><button class="primary">등록</button>
      </form>
    </div>
  </div>
</template>
