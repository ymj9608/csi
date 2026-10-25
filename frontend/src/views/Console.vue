<script setup lang="ts">
import Sidebar from "../components/Sidebar.vue";
import HeaderBar from "../components/HeaderBar.vue";
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  FolderGit2,
  ScanLine,
  ShieldAlert,
  ScrollText,
  ClipboardCheck,
  Search,
  ArrowUpRight,
  RefreshCw,
  ChevronRight,
  ChevronLeft,
  LogOut,
  Menu,
  X,
  Plus,
  GitBranch,
  Activity,
  ShieldCheck,
  Bot,
  FileText,
  Folder,
  FolderOpen,
  ChevronDown,
  ImagePlus,
} from "lucide-vue-next";
import { api, date } from "../lib/api";
import { analysisStatus, hasAnalysisText } from "../lib/analysisStatus";
import { useSession } from "../stores/session";
import Badge from "../components/Badge.vue";
import Chart from "../components/Chart.vue";
import ChangeReview from "../components/ChangeReview.vue";
import CodingProposal from "../components/CodingProposal.vue";
import ShieldScene from "../components/ShieldScene.vue";
import { label, eventLabels, toolLabels } from "../components/labels";
import Pager from "../components/Pager.vue";
import { buildTimeline, elapsed } from "../lib/timeline";
import ArchitectureUpload from "../components/ArchitectureUpload.vue";
import { ACCEPTED_TYPES, acceptable, addFolder } from "../lib/architecture";
import { registerProject } from "../lib/projectRegistration";
import { PROJECT_SCOPED, rememberProject, rememberedProject } from "../lib/project";
const route = useRoute(),
  router = useRouter(),
  session = useSession();
const nav = [
  ["/projects", "프로젝트", FolderGit2],
  ["/scans", "검사 이력", ScanLine],
  ["/findings", "위험 항목", ShieldAlert],
  ["/logs", "실행 로그", ScrollText],
  ["/approvals", "승인 관리", ClipboardCheck],
] as const;
const page = computed(() => route.path.split("/")[1] || "projects"),
  id = computed(() => route.path.split("/")[2]);
const dash = computed(() => page.value === "dashboard");
// 프로젝트 화면은 "보안 현황"과 "아키텍처" 버튼으로 아래 내용을 바꿉니다. ?view=architecture로 유지합니다.
const dashView = computed(() =>
  dash.value && route.query.view === "architecture" ? "architecture" : "status",
);
const dashStatus = computed(() => dash.value && dashView.value === "status");
// 프로젝트 이름 아래 버튼 줄. 보안 현황·아키텍처는 같은 화면 안에서, 나머지는 각 목록 화면으로 이동합니다.
const PROJECT_TABS = [
  ["status", "보안 현황"],
  ["architecture", "아키텍처"],
  ["scans", "검사 이력"],
  ["findings", "위험 항목"],
  ["logs", "실행 로그"],
] as const;
type ProjectTab = (typeof PROJECT_TABS)[number][0];
const projectTabs = computed(
  () => dash.value || (["scans", "findings", "logs"].includes(page.value) && !id.value),
);
const activeTab = computed(() => (dash.value ? dashView.value : page.value));
function openTab(tab: ProjectTab) {
  if (tab === "status" || tab === "architecture") {
    if (dash.value) return setDashView(tab);
    const query: Record<string, string> = projectId.value ? { project: projectId.value } : {};
    if (tab === "architecture") query.view = "architecture";
    return router.push({ path: "/dashboard", query });
  }
  router.push({ path: "/" + tab, query: projectId.value ? { project: projectId.value } : {} });
}
function setDashView(view: "status" | "architecture") {
  const { view: _view, ...query } = route.query;
  router.replace({ path: route.path, query: view === "status" ? query : { ...query, view } });
}
// 목록 화면은 선택한 프로젝트(?project=) 기준으로 조회합니다. 비어 있으면 전체 프로젝트입니다.
const scoped = computed(
  () => !id.value && PROJECT_SCOPED.includes(page.value),
);
// 위험 항목은 문제 유형 카드 → 위치 목록 → 상세 순서로 봅니다.
// 기본은 최근 완료 검사만, ?history=1이면 이전 검사도 포함합니다. ?rule=은 펼친 유형입니다.
const findingsPage = computed(() => page.value === "findings");
const includeHistory = computed(() => route.query.history === "1");
const projectId = computed(() => String(route.query.project || ""));
const projectList = ref<any[]>([]),
  approvalList = ref<any[]>([]);
// 저장소별 승인 대기 건수
const pendingByRepo = computed(() => {
  const counts: Record<string, number> = {};
  for (const a of approvalList.value)
    if (a.status === "PENDING") counts[a.repository] = (counts[a.repository] || 0) + 1;
  return counts;
});
const selectedProject = computed(() =>
  projectList.value.find((p) => p.id === projectId.value),
);
const heading = computed(
  () => nav.find((n) => n[0] === "/" + page.value)?.[1] || "프로젝트",
);
// 상세 화면처럼 쿼리가 없는 곳에서도 사이드바는 마지막 선택을 이어 줍니다.
const sidebarProject = computed(() =>
  route.fullPath && (projectId.value || rememberedProject()),
);
// 최근 완료 검사의 미해결 항목 기준. 탐지 0건이어도 안전을 보증하지는 않습니다.
function risk(completed: number, open: number, criticalHigh: number) {
  if (!Number(completed)) return "NOT_SCANNED";
  if (Number(criticalHigh) > 0) return "DANGER";
  return Number(open) > 0 ? "CAUTION" : "SAFE";
}
const riskTitle: Record<string, string> = {
  NOT_SCANNED: "완료된 검사가 없습니다",
  SAFE: "미해결 위험 항목 0건 · 검사 범위 밖의 안전은 보증하지 않습니다",
  CAUTION: "중간·낮음 위험 항목만 남아 있습니다",
  DANGER: "치명·높음 위험 항목이 남아 있습니다",
};
const dashRisk = computed(() =>
  risk(data.value.completedScans, data.value.openFindings, data.value.criticalHigh),
);
const intro: Record<string, string> = {
  dashboard: "선택한 프로젝트의 최근 완료 검사 기준 위험 현황입니다.",
  projects: "검사 대상 저장소와 마지막 검사 결과입니다.",
  scans: "커밋별 검사 진행 상황과 진단 근거를 추적합니다.",
  findings: "검사에서 발견된 위험 항목을 위험도와 상태로 걸러 봅니다.",
  logs: "Agent와 검사 파이프라인의 실행 기록입니다.",
  approvals: "Agent가 요청한 조치를 검토하고 승인하거나 거절합니다.",
};
// 코드 근거는 왼쪽 패널에 늘 보이므로 탭은 오른쪽 내용만 바꿉니다.
const tabs: Record<string, string> = {
  "AI Analysis": "AI 분석",
  "Coding Proposal": "수정안 생성·검토",
  Action: "조치",
  "Security References": "보안 근거",
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
  tab = ref("AI Analysis"),
  streamState = ref("연결 대기"),
  drawer = ref<any>(null),
  projectModal = ref(false),
  repo = ref(""),
  defaultBranch = ref("develop");
const dashboardNarrative = computed(() => Number(data.value.openFindings) > 0
  ? `최근 완료 검사 기준으로 미해결 위험 항목이 ${Number(data.value.openFindings)}건 있습니다. 치명·높음 ${Number(data.value.criticalHigh) || 0}건을 포함해 아래의 근거와 검토할 항목을 확인하세요.`
  : '최근 완료 검사에서 미해결 위험 항목은 0건입니다. 검사 범위와 실행 기록을 함께 확인하세요.');
// 저장된 분석 결과는 펼쳐보기 연출 없이 처음부터 모두 보여 줍니다.
function openFindingTab(value: string) {
  tab.value = value;
}
const reviewGroups = computed(() => {
  const groups: Record<string, number> = {};
  for (const f of data.value.findings || []) {
    if (f.ruleId !== 'POL-01' || !f.analysis?.policyComparison?.field) continue;
    const key = f.analysis.policyComparison.field;
    groups[key] = (groups[key] || 0) + 1;
  }
  return Object.entries(groups);
});
// 보안 현황의 검토 피드: 위험 항목(위험도 순)과 Agent 이벤트(최신순)를 한 목록에서 필터로 전환합니다.
const feedFilter = ref<"findings" | "events">("findings");
const feedFilters = computed(() => [
  ["findings", "검토 필요", data.value.topFindings?.length || 0],
  ["events", "Agent 이벤트", data.value.recentLogs?.length || 0],
] as const);
const feedDescriptions = {
  findings:
    "가장 최근 완료된 검사에서 아직 해결되지 않은 위험 항목입니다. 치명 → 높음 → 중간 → 낮음 순으로 정렬해 먼저 볼 항목부터 보여 주며, 누르면 코드 근거와 정책 근거를 확인할 수 있습니다.",
  events:
    "Agent가 검사를 분석하면서 남긴 실행 기록입니다. 분석 도구 선택, MCP 정책 조회, 근거 평가, 보고서 저장, 승인 요청 등이 최신순으로 표시되며, 누르면 해당 검사로 이동합니다.",
};
const feed = computed(() => [
  ...(feedFilter.value === "events" ? [] : (data.value.topFindings || []).map((f: any) => ({ kind: "finding", item: f }))),
  ...(feedFilter.value === "findings" ? [] : (data.value.recentLogs || []).map((l: any) => ({ kind: "event", item: l }))),
]);
const FEED_SIZE = 5;
const feedPage = ref(1),
  feedDirection = ref<"next" | "prev">("next");
const feedPages = computed(() => Math.max(1, Math.ceil(feed.value.length / FEED_SIZE)));
const feedVisible = computed(() =>
  feed.value.slice((feedPage.value - 1) * FEED_SIZE, feedPage.value * FEED_SIZE),
);
function moveFeed(step: number) {
  feedDirection.value = step > 0 ? "next" : "prev";
  feedPage.value = Math.min(feedPages.value, Math.max(1, feedPage.value + step));
}
watch(feedFilter, () => {
  feedDirection.value = "next";
  feedPage.value = 1;
});
// 실시간 갱신으로 항목 수가 줄어도 빈 페이지에 머물지 않게 합니다.
watch(feedPages, (n) => {
  if (feedPage.value > n) feedPage.value = n;
});
// 검사 상세: 탐지 결과는 5건씩 미리 보고, 실행 로그는 단계별 타임라인으로 묶습니다.
const SCAN_FINDING_SIZE = 5;
const scanFindingPage = ref(1);
const scanFindingPages = computed(() =>
  Math.max(1, Math.ceil((data.value.findings?.length || 0) / SCAN_FINDING_SIZE)),
);
const scanFindingsVisible = computed(() =>
  (data.value.findings || []).slice(
    (scanFindingPage.value - 1) * SCAN_FINDING_SIZE,
    scanFindingPage.value * SCAN_FINDING_SIZE,
  ),
);
function moveScanFindings(step: number) {
  scanFindingPage.value = Math.min(scanFindingPages.value, Math.max(1, scanFindingPage.value + step));
}
const timeline = computed(() => buildTimeline(data.value.logs || []));
const stageList = ref<HTMLElement>();
function jumpStage(key: string) {
  const box = stageList.value,
    target = box?.querySelector<HTMLElement>(`[data-stage="${key}"]`);
  if (box && target) box.scrollTo({ top: target.offsetTop, behavior: "smooth" });
}
// 위험 항목 상세의 Agent 도구 선택을 정책 확인 → 규칙별 근거 수집 → 완료 흐름으로 나눕니다.
const toolFlow = computed(() => {
  const trace: any[] = (data.value.analysis?.orchestration?.trace || []).map((step:any,index:number)=>({turn:index+1,...step}));
  const rules: Record<string, any[]> = {};
  for (const step of trace) if (step.ruleId) (rules[step.ruleId] ||= []).push(step);
  return {
    setup: trace.filter((step) => !step.ruleId && step.tool !== "finish_analysis"),
    rules: Object.entries(rules),
    finish: trace.filter((step) => !step.ruleId && step.tool === "finish_analysis"),
  };
});
// 보안 근거: 문서별로 묶고, 규칙과 가장 관련 있는 문장 하나만 먼저 보여 줍니다.
const RULE_KEYWORDS: Record<string, string[]> = {
  "SEC-01": ["원문", "평문", "저장", "password"],
  "SEC-02": ["해시", "SHA", "MD5", "빠른"],
  "SEC-03": ["Salt", "salt", "솔트", "고정", "사전"],
  "SEC-04": ["Work Factor", "bcrypt", "12", "비용", "Argon2"],
  "SEC-05": ["로그", "토큰", "마스킹", "출력"],
  "POL-01": ["승인", "필드", "수집", "목록", "최소"],
};
function keySentence(r: any) {
  const lines = String(r.content || "").split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines[0]?.startsWith(r.sectionId)) lines.shift();
  const sentences = lines
    .join(" ")
    .split(/(?<=[.다])\s+|\s(?=(?:POL|REF)-\d+\.\d+\s*\|)/)
    .map((x) => x.trim())
    .filter((x) => x.length > 8);
  const words = RULE_KEYWORDS[data.value.ruleId] || [];
  const score = (x: string) => words.filter((w) => x.includes(w)).length;
  const best = sentences.reduce((a, b) => (score(b) > score(a) ? b : a), sentences[0] || r.content || "");
  return best.length > 180 ? best.slice(0, 180) + "…" : best;
}
const referenceGroups = computed(() => {
  const groups: Record<string, { source: string; type: string; refs: any[] }> = {};
  for (const r of data.value.analysis?.references || [])
    (groups[r.source] ||= { source: r.source, type: r.documentType, refs: [] }).refs.push(r);
  return Object.values(groups);
});
const openRefs = ref<string[]>([]);
function toggleRef(id: string) {
  openRefs.value = openRefs.value.includes(id)
    ? openRefs.value.filter((x) => x !== id)
    : [...openRefs.value, id];
}
const SEVERITY_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
const fieldOf = (f: any) => f.analysis?.policyComparison?.field;
// 같은 규칙의 탐지 위치를 문제 유형 하나로 묶습니다. 위험도가 높고 위치가 많은 유형부터 정렬합니다.
const findingGroups = computed(() => {
  if (!findingsPage.value || id.value) return [];
  const groups: Record<string, any> = {};
  for (const f of filtered.value) {
    const g = (groups[f.ruleId] ||= { ruleId: f.ruleId, title: f.title, severity: f.severity, items: [] });
    g.items.push(f);
    if (SEVERITY_RANK[f.severity] < SEVERITY_RANK[g.severity]) g.severity = f.severity;
  }
  return Object.values(groups)
    .map((g: any) => {
      const profile = profiles.find((p) => p.rules.includes(g.ruleId));
      const fields = new Set(g.items.map(fieldOf).filter(Boolean));
      return {
        ...g,
        profile,
        fields: fields.size,
        open: g.items.filter((f: any) => f.status !== "RESOLVED").length,
      };
    })
    .sort(
      (a: any, b: any) =>
        SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.items.length - a.items.length,
    );
});
const activeRule = computed(
  () => String(route.query.rule || "") || findingGroups.value[0]?.ruleId || "",
);
const activeGroup = computed(() => findingGroups.value.find((g: any) => g.ruleId === activeRule.value));
// 개인정보 필드(POL-01)는 같은 필드가 여러 클래스에 반복되므로 필드 종류로 한 번 더 묶습니다.
const activeLocations = computed(() => {
  const g = activeGroup.value;
  if (!g) return [];
  const sorted = [...g.items].sort((a: any, b: any) =>
    `${a.filePath}:${String(a.startLine).padStart(6, "0")}`.localeCompare(
      `${b.filePath}:${String(b.startLine).padStart(6, "0")}`,
    ),
  );
  const buckets: Record<string, any[]> = {};
  for (const f of sorted) (buckets[fieldOf(f) || f.filePath] ||= []).push(f);
  return Object.entries(buckets).map(([key, list]) => ({ key, isField: !!fieldOf(list[0]), items: list }));
});
// 위치 목록에서 파일:라인이 반복되지 않도록, 가린 코드 근거의 첫 줄을 제목으로 씁니다.
function snippet(f: any) {
  const line = String(f.maskedCodeEvidence || "").split("\n").map((x) => x.trim()).find(Boolean);
  return line ? (line.length > 90 ? line.slice(0, 90) + "…" : line) : `${f.filePath}:${f.startLine}`;
}
function selectRule(ruleId: string) {
  router.replace({ path: "/findings", query: { ...route.query, rule: ruleId } });
}
function setHistory(on: boolean) {
  const query = { ...route.query };
  if (on) query.history = "1";
  else delete query.history;
  router.replace({ path: route.path, query });
}
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
// 미완료 검사 = 전체 검사 - 완료된 검사(대기·진행 중·실패 포함). 아래 줄의 보조 정보도 이미 받은 데이터로 만듭니다.
const metrics = computed(() => {
  const total = Number(data.value.scans) || 0,
    done = Number(data.value.completedScans) || 0,
    last = data.value.recentScans?.[0]?.createdAt;
  const rate = total ? Math.round((done / total) * 100) : 0;
  return [
    { key: "total", name: "전체 검사", value: total, icon: ScanLine, note: last ? `마지막 검사 ${date(last)}` : "아직 검사가 없습니다" },
    { key: "done", name: "완료된 검사", value: done, icon: ShieldCheck, rate, note: `완료율 ${rate}%` },
    { key: "pending", name: "미완료 검사", value: total - done, icon: Activity, note: "대기·진행 중·실패 포함" },
  ];
});
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
const palette = ["#C8264F", "#E0701F", "#D9A400", "#7f99fa"];
const chartFont = {
  fontFamily: "'Pretendard Variable', Pretendard, sans-serif",
};
const severityColors: Record<string, string> = {
  CRITICAL: "#C8264F",
  HIGH: "#E0701F",
  MEDIUM: "#D9A400",
  LOW: "#7f99fa",
};
// 위험도 분포 범례: 0건인 등급도 함께 보여 줘서 어떤 등급이 비어 있는지 알 수 있게 합니다.
const severityLegend = computed(() => {
  const counts = Object.fromEntries(
    (data.value.distribution || []).map((x: any) => [x.severity, Number(x.count)]),
  );
  const total = Object.values(counts).reduce((a: number, b: any) => a + b, 0) as number;
  return Object.keys(severityColors).map((severity) => ({
    severity,
    count: counts[severity] || 0,
    percent: total ? Math.round(((counts[severity] || 0) / total) * 100) : 0,
  }));
});
const donut = computed(() => ({
  animation: false,
  textStyle: chartFont,
  color: palette,
  tooltip: { trigger: "item" },
  series: [
    {
      type: "pie",
      radius: ["44%", "80%"],
      center: ["50%", "50%"],
      label: { show: false },
      itemStyle: { borderColor: "#fff", borderWidth: 3, borderRadius: 4 },
      data: (data.value.distribution || []).map((x: any) => ({
        name: label(x.severity),
        value: x.count,
        itemStyle: { color: severityColors[x.severity] },
      })),
    },
  ],
}));
const trend = computed(() => ({
  animation: false,
  textStyle: chartFont,
  color: ["#3f5ee8"],
  tooltip: { trigger: "axis" },
  grid: { left: 40, right: 20, top: 25, bottom: 30 },
  xAxis: {
    type: "category",
    data: (data.value.trend || []).map((x: any) => x.day),
    axisLine: { lineStyle: { color: "#cbd4ee" } },
    axisTick: { show: false },
    axisLabel: { color: "#6b7296" },
  },
  yAxis: {
    type: "value",
    minInterval: 1,
    splitLine: { lineStyle: { color: "#e6eaf6" } },
    axisLabel: { color: "#6b7296" },
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
    // 메뉴에 프로젝트 목록을 보여 주므로 어느 화면에서나 불러옵니다.
    api("/projects")
      .then((list) => key === request && Array.isArray(list) && (projectList.value = list))
      .catch(() => {});
    // 승인 대기가 있는 프로젝트를 프로젝트 카드와 메뉴에 표시하려고 승인 목록도 함께 불러옵니다.
    api("/approvals")
      .then((list) => key === request && Array.isArray(list) && (approvalList.value = list))
      .catch(() => {});
    const query = scoped.value && projectId.value ? "?projectId=" + projectId.value : "";
    if (findingsPage.value && !id.value) {
      const params = new URLSearchParams();
      if (projectId.value) params.set("projectId", projectId.value);
      if (!includeHistory.value) params.set("latest", "true");
      const list = await api("/findings?" + params);
      if (key !== request) return;
      items.value = list;
      data.value = {};
      return;
    }
    if (dash.value) {
      const overview = await api("/dashboard/overview" + query);
      if (key !== request) return;
      data.value = overview;
      items.value = [];
      return;
    }
    const path = "/" + page.value + (id.value ? "/" + id.value : "");
    const result = await api(path + query);
    if (key !== request) return;
    data.value = Array.isArray(result) ? {} : result;
    items.value = Array.isArray(result) ? result : result.items || [];
    if (id.value && page.value === "scans") {
      const [findings, logs, comparison, changes, coding] = await Promise.all([
        api(path + "/findings"),
        api(path + "/logs"),
        api(path + "/comparison"),
        api(path + "/changes"),
        api(path + "/coding-proposals"),
      ]);
      if (key === request)
        data.value = { ...result, findings, logs, comparison, changes, coding };
    }
    if (id.value && findingsPage.value && result.scanId) {
      const [scan, coding, findings] = await Promise.all([
        api(`/scans/${result.scanId}`), api(`/scans/${result.scanId}/coding-proposals`),
        api(`/scans/${result.scanId}/findings`),
      ]);
      if (key === request) data.value = { ...result, scanStatus:scan.status, coding, codingFindings:findings };
    }
  } catch (e: any) {
    if (key === request) error.value = e.message;
  } finally {
    if (key === request) {
      loading.value = false;
    }
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
function selectProject(value: string) {
  rememberProject(value);
  const keep = dash.value && route.query.view ? { view: route.query.view } : {};
  router.replace({ path: route.path, query: value ? { project: value, ...keep } : keep });
}
// 아키텍처는 프로젝트별로만 보므로 "전체 프로젝트" 상태라면 마지막 선택 또는 첫 프로젝트를 고릅니다.
watch(
  () => [dashView.value, projectId.value, projectList.value] as const,
  ([view, project, list]) => {
    if (view !== "architecture" || project || !list.length) return;
    const remembered = rememberedProject();
    selectProject(list.some((p) => p.id === remembered) ? remembered : list[0].id);
  },
);
// 승인 관리: 등록된 프로젝트마다 폴더를 만들고, 승인 대기가 있는 폴더를 맨 위로 올립니다.
// 나머지는 프로젝트를 만든 최신순(/api/projects 순서)입니다. 폴더 안은 승인 대기부터 보여 줍니다.
const openedApprovals = ref<string[]>([]);
const toggleApprovals = (key: string) =>
  (openedApprovals.value = openedApprovals.value.includes(key)
    ? openedApprovals.value.filter((k) => k !== key)
    : [...openedApprovals.value, key]);
const approvalFolders = computed(() => {
  if (page.value !== "approvals" || id.value) return [];
  const groups = new Map<string, any[]>();
  for (const a of filtered.value) groups.set(a.repository, [...(groups.get(a.repository) || []), a]);
  const names = [
    ...projectList.value.map((p) => p.repository),
    ...[...groups.keys()].filter((r) => !projectList.value.some((p) => p.repository === r)),
  ];
  const count = (items: any[], s: string) => items.filter((a) => a.status === s).length;
  return names
    .map((name, order) => {
      const items = [...(groups.get(name) || [])].sort(
        (a, b) => Number(b.status === "PENDING") - Number(a.status === "PENDING"),
      );
      return {
        name,
        order,
        items,
        pending: count(items, "PENDING"),
        approved: count(items, "APPROVED") + count(items, "EXECUTED"),
        rejected: count(items, "REJECTED"),
      };
    })
    .filter((f) => f.items.length || !(search.value || status.value))
    .sort((a, b) => Number(b.pending > 0) - Number(a.pending > 0) || a.order - b.order);
});
// 메뉴 막대 접기 상태는 이 브라우저에 기억합니다.
const SIDEBAR_KEY = "csi.sidebar";
function readSidebar() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "collapsed";
  } catch {
    return false;
  }
}
const sidebarCollapsed = ref(readSidebar());
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  try {
    localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed.value ? "collapsed" : "open");
  } catch {}
}
let lastListKey = "";
watch(
  () => route.fullPath,
  () => {
    // 쿼리 없이 들어오면 마지막으로 고른 프로젝트를 이어서 보여줍니다.
    const remembered = rememberedProject();
    if (scoped.value && !route.query.project && remembered) {
      router.replace({ path: route.path, query: { ...route.query, project: remembered } });
      return;
    }
    if (scoped.value && projectId.value) rememberProject(projectId.value);
    mobile.value = false;
    // 위험 항목에서 유형 카드만 바꾸거나 프로젝트 화면에서 보안 현황·아키텍처 버튼만 바꾼 경우에는
    // 검색어와 필터를 유지하고 다시 불러오지 않습니다.
    const { rule: _rule, view: _view, ...listQuery } = route.query;
    const listKey = route.path + "?" + JSON.stringify(listQuery);
    const sameList =
      ((findingsPage.value && !id.value) || dash.value) && listKey === lastListKey;
    lastListKey = listKey;
    if (sameList) return;
    search.value = "";
    status.value = "";
    severity.value = "";
    branch.value = "";
    since.value = "";
    until.value = "";
    logLevel.value = "";
    oldestFirst.value = false;
    current.value = 1;
    tab.value = "AI Analysis";
    scanFindingPage.value = 1;
    openRefs.value = [];
    feedFilter.value = "findings";
    feedPage.value = 1;
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
// 첫 첨부를 서버 분석용 이미지로 저장해야 프로젝트 등록이 완료됩니다.
const archFiles = ref<File[]>([]),
  archInput = ref<HTMLInputElement>(),
  registering = ref(false);
function chooseArchFiles(files?: FileList | null) {
  const all = Array.from(files || []);
  const accepted = all.filter((file) => file.size > 0 && acceptable(file));
  if (archInput.value) archInput.value.value = "";
  if (accepted.length < all.length)
    session.notify(`형식이나 크기가 맞지 않는 ${all.length - accepted.length}개 파일은 제외했습니다.`);
  archFiles.value = [...archFiles.value, ...accepted];
}
function closeProjectModal() {
  projectModal.value = false;
  archFiles.value = [];
}
async function addProject() {
  if (registering.value) return;
  if (!archFiles.value.length) return session.notify("아키텍처 파일을 필수로 첨부하세요.");
  registering.value = true;
  try {
    const repository = repo.value;
    const files = [...archFiles.value];
    const created = await registerProject(repository, defaultBranch.value, files[0]);
    let message = "프로젝트와 아키텍처를 등록했습니다. 아키텍처 분석 대기 중입니다.";
    try {
      await addFolder(created.id, repository, files);
    } catch {
      message = "프로젝트와 분석용 이미지는 서버에 등록했습니다. 브라우저의 이미지 폴더 저장은 실패했습니다.";
    }
    closeProjectModal();
    repo.value = "";
    session.notify(message);
    load();
  } catch (e: any) {
    session.notify(e.message);
  } finally {
    registering.value = false;
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
  <div class="console" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <Sidebar
      :mobile="mobile"
      :projects="projectList"
      :collapsed="sidebarCollapsed"
      @toggle="toggleSidebar"
      :page="page"
      :project="sidebarProject"
      :project-name="
        projectList.find((p) => p.id === sidebarProject)?.repository || ''
      "
      @logout="logout"
    />
    <div v-if="mobile" class="scrim" @click="mobile = false" />
    <main class="main">
      <HeaderBar
        :heading="heading"
        :stream-state="streamState"
        @toggle="mobile = !mobile"
      />
      <div class="content">
        <div class="page-heading" :class="{ 'with-shield': dash }">
          <ShieldScene
            v-if="dash"
            compact
            class="heading-shield"
            :progress="loading ? 0 : 1"
            :state="
              loading || error ? 'idle' : data.criticalHigh > 0 ? 'alert' : 'locked'
            "
          />
          <div>
            <h1 v-if="dash" class="project-heading">
              {{ data.project?.repository || "전체 프로젝트"
              }}<Badge
                v-if="!loading && !error"
                :value="dashRisk"
                :title="riskTitle[dashRisk]"
              />
            </h1>
            <h1 v-else-if="projectTabs">
              {{ selectedProject?.repository || "전체 프로젝트" }}
            </h1>
            <h1 v-else>
              {{ id ? data.repository || data.title || heading : heading }}
            </h1>
            <p v-if="dash && data.project" class="project-sub">
              <GitBranch :size="13" />{{ data.project.defaultBranch }} · 정책
              {{ data.project.policyVersion }}
            </p>
            <p v-else-if="dash" class="project-sub">
              <FolderGit2 :size="13" />등록된 프로젝트 {{ data.projects ?? 0 }}개 합산
            </p>
            <p v-if="dash">
              <template v-if="loading">최신 검사 결과를 불러오는 중입니다.</template>
              <template v-else-if="!data.completedScans"
                >아직 완료된 검사가 없습니다. 검사 결과가 들어오면 위험도를
                판단합니다.</template
              >
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
            <p v-else-if="findingsPage && id">
              정적 분석 근거와 정책 대조 결과를 함께 검토합니다.
            </p>
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
        <div v-if="projectTabs" class="tabs dash-tabs" role="tablist" aria-label="프로젝트 화면">
          <button
            v-for="[tab, name] in PROJECT_TABS"
            :key="tab"
            role="tab"
            :aria-selected="activeTab === tab"
            :class="{ selected: activeTab === tab }"
            @click="openTab(tab)"
          >
            {{ name }}
          </button>
        </div>
        <ArchitectureUpload
          v-if="dash && dashView === 'architecture'"
          :project="projectId"
          :project-name="data.project?.repository || selectedProject?.repository || ''"
        />
        <div v-if="error && !(dash && dashView === 'architecture')" class="error" role="alert">
          {{ error }} <button @click="load()">다시 시도</button>
        </div>
        <div v-if="loading && !(dash && dashView === 'architecture')" class="skeleton-grid" aria-label="불러오는 중">
          <div v-for="n in 6" :key="n" class="skeleton" />
        </div>
        <template v-else-if="!error"
          >
          <p v-if="dashStatus && projectId && Number(data.completedScans) > 0" class="report-narrative">
            {{ dashboardNarrative }}
          </p>
          <template v-if="dashStatus"
            ><div class="metrics">
              <article v-for="m in metrics" :key="m.key" :class="'metric-' + m.key">
                <span class="metric-icon"><component :is="m.icon" :size="20" /></span>
                <div class="metric-body">
                  <span class="metric-label">{{ m.name }}</span>
                  <strong>{{ m.value }}</strong>
                  <div v-if="m.rate !== undefined" class="metric-bar" role="presentation">
                    <i :style="{ width: m.rate + '%' }" />
                  </div>
                  <small>{{ m.note }}</small>
                </div>
              </article>
            </div>
            <div class="charts-grid">
              <section class="panel">
                <div class="panel-title">
                  <h2>위험도 분포</h2>
                  <span>미해결 항목</span>
                </div>
                <div v-if="data.distribution?.length" class="donut-wrap">
                  <Chart :option="donut" />
                  <ul class="severity-legend" aria-label="위험도 범례">
                    <li class="total">
                      <span>전체 미해결 항목</span><strong>{{ data.openFindings ?? 0 }}건</strong>
                    </li>
                    <li
                      v-for="l in severityLegend"
                      :key="l.severity"
                      :class="{ zero: !l.count }"
                    >
                      <i :style="{ background: severityColors[l.severity] }" />
                      <span>{{ label(l.severity) }}</span>
                      <strong>{{ l.count }}건</strong>
                      <small>{{ l.percent }}%</small>
                    </li>
                  </ul>
                </div>
                <div v-else class="empty chart-empty">
                  <ShieldCheck :size="26" /><strong
                    >집계할 위험 항목이 없습니다</strong
                  ><span>미해결 항목이 생기면 위험도별로 나눠 보여줍니다.</span>
                </div>
              </section>
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
            </div>
          </template>
          <template v-if="dashStatus"
            ><section class="panel review-feed">
              <div class="panel-title">
                <h2>검토 피드</h2>
                <RouterLink
                  :to="{
                    path: feedFilter === 'events' ? '/logs' : '/findings',
                    query: route.query,
                  }"
                  >{{ feedFilter === "events" ? "로그 보기" : "전체 위험 항목" }}
                  <ArrowUpRight :size="14"
                /></RouterLink>
              </div>
              <div class="feed-filters" role="group" aria-label="검토 피드 필터">
                <button
                  v-for="[key, name, count] in feedFilters"
                  :key="key"
                  :aria-pressed="feedFilter === key"
                  :class="{ selected: feedFilter === key }"
                  @click="feedFilter = key"
                >
                  {{ name }}<span>{{ count }}</span>
                </button>
              </div>
              <p class="feed-description">{{ feedDescriptions[feedFilter] }}</p>
              <Transition :name="'feed-slide-' + feedDirection" mode="out-in">
                <div :key="feedFilter + feedPage" class="feed-page">
                  <template v-for="row in feedVisible" :key="row.kind + row.item.id">
                    <RouterLink
                      v-if="row.kind === 'finding'"
                      :to="'/findings/' + row.item.id"
                      class="list-row"
                      ><Badge :value="row.item.severity" /><span class="grow"
                        >{{ row.item.title
                        }}<small class="mono"
                          ><code>{{ row.item.ruleId }}</code
                          ><template v-if="!projectId">{{ row.item.repository }} · </template
                          >{{ row.item.filePath }}:{{ row.item.startLine }}</small
                        ></span
                      ><ChevronRight :size="16"
                    /></RouterLink>
                    <RouterLink
                      v-else
                      :to="row.item.scanId ? '/scans/' + row.item.scanId : '/logs'"
                      class="list-row"
                      ><span class="feed-icon"><Bot :size="15" /></span
                      ><span class="grow"
                        ><strong
                          >{{ eventLabels[row.item.eventType] || row.item.eventType
                          }}<code v-if="eventLabels[row.item.eventType]">{{
                            row.item.eventType
                          }}</code></strong
                        ><small>{{ row.item.message }}</small></span
                      ><small class="time">{{ date(row.item.timestamp) }}</small></RouterLink
                    >
                  </template>
                  <p v-if="!feed.length" class="empty">
                    {{
                      feedFilter === "events"
                        ? "아직 실행 이벤트가 없습니다."
                        : "미해결 위험 항목이 없습니다."
                    }}
                  </p>
                </div>
              </Transition>
              <Pager
                v-if="feedPages > 1"
                class="panel-pager"
                :page="feedPage"
                :pages="feedPages"
                label="검토 피드"
                @move="moveFeed"
              />
            </section></template
          >
          <template v-if="page === 'scans' && !id"
            ><section class="panel">
              <div class="panel-title">
                <h2>검사 이력</h2>
                <span>{{ filtered.length }}건</span>
              </div>
              <div class="filters">
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
                    <tr v-for="s in visible" :key="s.id">
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
                <div v-if="!visible.length" class="empty">
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
                :to="{ path: '/dashboard', query: { project: p.id } }"
                class="panel project-card"
                ><div class="project-top">
                  <FolderGit2 :size="20" /><span class="project-badges"
                    ><span
                      v-if="pendingByRepo[p.repository]"
                      class="approval-waiting"
                      :title="'승인 관리에서 처리할 요청이 ' + pendingByRepo[p.repository] + '건 있습니다'"
                      ><i />승인 대기 {{ pendingByRepo[p.repository] }}</span
                    ><Badge
                      v-if="['QUEUED', 'RUNNING', 'FAILED'].includes(p.latestStatus)"
                      :value="p.latestStatus" /><Badge
                      :value="risk(p.completedScans, p.openFindings, p.openCriticalHigh)"
                      :title="
                        riskTitle[
                          risk(p.completedScans, p.openFindings, p.openCriticalHigh)
                        ]
                      "
                  /></span>
                </div>
                <h2>{{ p.repository }}</h2>
                <p class="mono">github.com/{{ p.repository }}</p>
                <dl class="project-meta">
                  <div>
                    <dt>기본 브랜치</dt>
                    <dd><GitBranch :size="13" /> {{ p.defaultBranch }}</dd>
                  </div>
                  <div>
                    <dt>미해결 위험 항목</dt>
                    <dd class="num">{{ p.openFindings || 0 }}</dd>
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
            <CodingProposal :scan-id="id" :scan-status="data.status" :coding="data.coding" :findings="data.findings" @refresh="load(true)" />
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
                v-for="f in scanFindingsVisible"
                :key="f.id"
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
              <Pager
                v-if="scanFindingPages > 1"
                class="panel-pager"
                :page="scanFindingPage"
                :pages="scanFindingPages"
                :total="data.findings.length"
                label="탐지 결과"
                @move="moveScanFindings"
              />
            </section>
            <section class="panel scan-timeline">
              <div class="panel-title">
                <h2>실행 타임라인</h2>
                <span v-if="timeline.groups.length"
                  >총 {{ elapsed(timeline.total) }} · 이벤트 {{ data.logs.length }}건</span
                >
              </div>
              <template v-if="timeline.groups.length">
                <div class="stage-bar" aria-label="단계별 소요 시간">
                  <button
                    v-for="g in timeline.groups"
                    :key="g.key"
                    class="stage-seg"
                    :style="{
                      '--c': g.color,
                      flex: `${Math.max(g.to - g.from, timeline.total * 0.08)} 1 0`,
                    }"
                    :title="`${g.name} · ${elapsed(g.to - g.from)} · ${g.events.length}건`"
                    @click="jumpStage(g.key)"
                  >
                    <i /><strong>{{ g.name }}</strong
                    ><small>{{ elapsed(g.to - g.from) }} · {{ g.events.length }}건</small>
                  </button>
                </div>
                <div ref="stageList" class="stage-list">
                  <section
                    v-for="g in timeline.groups"
                    :key="g.key"
                    :data-stage="g.key"
                    class="stage-group"
                    :style="{ '--c': g.color }"
                  >
                    <header>
                      <i /><strong>{{ g.name }}</strong
                      ><small>시작 +{{ elapsed(g.from) }} · {{ g.events.length }}건</small>
                    </header>
                    <ol class="timeline">
                      <li
                        v-for="e in g.events"
                        :key="e.id"
                        :class="{ warn: e.level !== 'INFO' }"
                      >
                        <span class="t-offset">+{{ elapsed(e.offset) }}</span
                        ><span class="grow"
                          ><strong
                            >{{ eventLabels[e.eventType] || e.eventType
                            }}<code v-if="eventLabels[e.eventType]">{{ e.eventType }}</code></strong
                          ><small>{{ e.message }}</small></span
                        ><span class="tag">{{ e.component }}</span>
                      </li>
                    </ol>
                  </section>
                </div>
              </template>
              <p v-else class="empty">아직 실행 기록이 없습니다.</p>
            </section></template
          >
          <template v-if="findingsPage && !id"
            ><div class="finding-toolbar">
              <label class="search"
                ><Search :size="16" /><input
                  v-model="search"
                  aria-label="위험 항목 검색"
                  placeholder="제목, 파일, 규칙, 필드 검색"
              /></label
              ><select v-model="severity" aria-label="위험도">
                <option value="">모든 위험도</option>
                <option v-for="s in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']" :value="s">
                  {{ label(s) }}
                </option></select
              ><select v-model="status" aria-label="상태 필터">
                <option value="">모든 상태</option>
                <option v-for="s in ['OPEN', 'REVIEWING', 'RESOLVED']" :value="s">
                  {{ label(s) }}
                </option></select
              ><label class="history-toggle"
                ><input
                  type="checkbox"
                  :checked="includeHistory"
                  @change="setHistory(($event.target as HTMLInputElement).checked)"
                />이전 검사 결과 포함</label
              >
            </div>
            <p class="finding-summary">
              {{ includeHistory ? "모든 검사" : "최근 완료 검사" }} 기준으로
              <strong>문제 유형 {{ findingGroups.length }}종</strong>, 코드 위치
              {{ filtered.length }}곳이 발견되었습니다. 유형을 고르면 아래에 위치가 나오고, 위치를
              누르면 근거와 AI 분석을 볼 수 있습니다.
            </p>
            <div v-if="findingGroups.length" class="type-grid" role="list">
              <button
                v-for="g in findingGroups"
                :key="g.ruleId"
                role="listitem"
                class="type-card"
                :class="['sev-' + g.severity.toLowerCase(), { selected: g.ruleId === activeRule }]"
                :aria-pressed="g.ruleId === activeRule"
                @click="selectRule(g.ruleId)"
              >
                <span class="type-top"
                  ><Badge :value="g.severity" /><code>{{ g.ruleId }}</code></span
                >
                <strong>{{ g.title }}</strong>
                <small v-if="g.profile">{{ g.profile.id }} · {{ g.profile.name }}</small>
                <span class="type-count"
                  ><b>{{ g.fields ? g.fields : g.items.length }}</b
                  >{{ g.fields ? "종 필드" : "곳" }}<em v-if="g.fields"
                    >· 위치 {{ g.items.length }}곳</em
                  ><em v-if="g.open < g.items.length">· 미해결 {{ g.open }}</em></span
                >
              </button>
            </div>
            <section v-if="activeGroup" class="panel location-panel">
              <div class="panel-title">
                <div>
                  <h2>{{ activeGroup.title }}</h2>
                  <span v-if="activeGroup.profile">{{ activeGroup.profile.detail }}</span>
                </div>
                <span>{{
                  activeGroup.fields
                    ? `필드 ${activeGroup.fields}종 · 위치 ${activeGroup.items.length}곳`
                    : `위치 ${activeGroup.items.length}곳`
                }}</span>
              </div>
              <div
                v-for="loc in activeLocations"
                :key="loc.key"
                class="location-group"
              >
                <h3>
                  <code v-if="loc.isField">{{ loc.key }}</code
                  ><span v-else class="mono">{{ loc.key }}</span
                  ><small>{{ loc.items.length }}곳</small>
                </h3>
                <RouterLink
                  v-for="f in loc.items"
                  :key="f.id"
                  :to="{ path: '/findings/' + f.id, query: route.query }"
                  class="finding-row"
                  ><div>
                    <strong
                      ><template v-if="f.analysis?.policyComparison"
                        >{{ f.analysis.policyComparison.entity }}.{{
                          f.analysis.policyComparison.field
                        }}</template
                      ><template v-else>{{ snippet(f) }}</template></strong
                    ><small class="meta"
                      ><span class="mono">{{ f.filePath }}:{{ f.startLine }}</span
                      ><span v-if="!projectId">{{ f.repository }}</span
                      ><span v-if="includeHistory" class="mono">{{
                        f.commitSha?.slice(0, 8)
                      }}</span></small
                    >
                  </div>
                  <Badge :value="f.status" /><ChevronRight :size="16"
                /></RouterLink>
              </div>
            </section>
            <div v-if="!findingGroups.length" class="panel empty">
              <ShieldCheck :size="28" /><strong>표시할 위험 항목이 없습니다</strong
              ><span>{{
                includeHistory
                  ? "검사 결과가 저장되면 이곳에서 확인할 수 있습니다."
                  : "최근 완료 검사에 해당하는 항목이 없습니다. 이전 검사 결과 포함을 켜면 지난 기록을 볼 수 있습니다."
              }}</span>
            </div></template
          >
          <template v-if="findingsPage && id"
            ><RouterLink
              class="back-link"
              :to="{ path: '/findings', query: { ...route.query, rule: data.ruleId } }"
              ><ChevronLeft :size="14" />위험 항목 목록</RouterLink
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
            <p class="finding-summary" aria-label="위험 항목 검토 순서">위험 요인 확인 → AI 분석 → 수정안 생성 → 수정 근거·코드 확인 → 승인 또는 거절</p>
            <div class="tabs" role="tablist">
              <button
                v-for="(name, t) in tabs"
                role="tab"
                :aria-selected="tab === t"
                @click="openFindingTab(String(t))"
                :class="{ selected: tab === t }"
              >
                {{ name }}
              </button>
            </div>
            <div class="detail-grid">
              <section class="panel detail-panel">
                <h2 class="step-title"><b>1</b>스캐너가 찾은 사실</h2>
                <p class="step-sub">Semgrep 정적 분석이 코드에서 기계적으로 확인한 내용입니다.</p>
                <p class="mono file-path">
                  {{ data.filePath }}:{{ data.startLine }}–{{ data.endLine }}
                </p>
                <pre>{{ data.maskedCodeEvidence || "코드 원문 미제공" }}</pre>
                <p class="code-note">
                  문자열 리터럴과 주석을 제거한 정적 분석 근거입니다. 런타임 동작과
                  실제 저장 경로는 별도 확인이 필요할 수 있습니다.
                </p>
                <dl>
                  <dt>증거 수준</dt>
                  <dd>{{ label(data.evidenceStatus) }}</dd>
                  <dt>신뢰 수준</dt>
                  <dd>{{ data.confidence }}<small v-if="data.analysis?.confidenceBasis">{{ data.analysis.confidenceBasis }}</small></dd>
                  <dt>정책</dt>
                  <dd>{{ data.policyVersion }}</dd>
                  <dt>커밋</dt>
                  <dd class="mono">{{ data.commitSha }}</dd>
                  <dt>근거 지문</dt>
                  <dd class="mono fingerprint">{{ data.fingerprint }}</dd>
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
                <template v-if="tab === 'AI Analysis'"
                  ><h2 class="step-title"><b>2</b>AI의 해석</h2>
                  <p class="step-sub">Agent가 위 사실과 사내 규정을 함께 보고 판단한 내용입니다.</p>
                  <div class="analysis-status" :class="{'analysis-status-warning':data.scanStatus === 'FAILED' || data.scanStatus === 'COMPLETED' && (!hasAnalysisText(data.analysis?.red) || !hasAnalysisText(data.analysis?.blue))}" role="status" aria-label="분석 상태">
                    <strong>{{ analysisStatus(data.scanStatus, data.analysis).title }}</strong>
                    <p>{{ analysisStatus(data.scanStatus, data.analysis).detail }}</p>
                    <RouterLink v-if="data.scanId" :to="'/scans/' + data.scanId">검사 상세·실행 기록 확인</RouterLink>
                  </div>
                  <div v-if="data.analysis?.policyComparison" class="review-policy">
                    <strong class="mono">{{ data.analysis.policyComparison.entity }}.{{ data.analysis.policyComparison.field }}</strong>
                    <p>정책 대조: {{ policyLabels[data.analysis.policyComparison.inventoryStatus] }}</p>
                    <small>별도 승인 기록 미확인, 런타임 검증 미수행</small>
                  </div>
                  <div v-if="hasAnalysisText(data.analysis?.red)" class="verdict red">
                    <h2><ShieldAlert :size="18" />잠재 위험</h2>
                    <p class="threat-name">{{ data.analysis?.threatProfile }}</p>
                    <p>{{ data.analysis.red }}</p>
                  </div>
                  <div v-if="hasAnalysisText(data.analysis?.blue)" class="verdict blue">
                    <h2><ShieldCheck :size="18" />근거 검토와 불확실성</h2>
                    <p>{{ data.analysis.blue }}</p>
                  </div>
                  <section v-if="data.analysis?.unknowns?.length" class="review-evidence">
                    <h3>추가 확인이 필요한 사항</h3>
                    <ul><li v-for="item in data.analysis.unknowns" :key="item">{{ item }}</li></ul>
                  </section>
                  <p v-if="data.analysis?.fallbackReason" class="fallback-note">
                    이 항목의 일부 판단은 LLM 대신 규칙 기반으로 대체되었습니다 (사유:
                    {{ data.analysis.fallbackReason }}).
                  </p>
                  <button class="primary" @click="openFindingTab('Coding Proposal')">수정안 생성·검토로 이동</button></template
                ><template v-if="tab === 'Coding Proposal'">
                  <h2 class="step-title"><b>3</b>수정안 생성·검토</h2>
                  <p class="step-sub">분석한 위험을 보완할 코드를 생성하고, 수정 근거·테스트·diff를 확인한 뒤 승인하거나 거절하세요.</p>
                  <CodingProposal v-if="data.scanId" :key="data.scanId" :scan-id="data.scanId" :scan-status="data.scanStatus"
                    :coding="data.coding" :finding="data" :findings="data.codingFindings" @refresh="load(true)" />
                </template
                ><template v-if="tab === 'Action'"
                  ><h2 class="step-title"><b>2</b>조치</h2>
                  <p class="step-sub">위험 항목의 관리 상태를 기록합니다. 코드 수정안 승인·거절은 수정안 생성·검토 탭에서 진행하세요.</p>
                  <button class="primary" @click="tab='Coding Proposal'">수정안 생성·검토로 이동</button>
                  <section class="action-block">
                    <h3>개선 권고</h3>
                    <p>
                      {{
                        data.analysis?.remediation ||
                        "검증된 개선 권고가 아직 없습니다."
                      }}
                    </p>
                    <pre v-if="data.analysis?.example">{{ data.analysis.example }}</pre>
                    <small
                      >예시는 수정 방향을 설명하며 원본 코드나 적용된 패치가
                      아닙니다. CSI는 코드를 자동으로 수정하지 않습니다.</small
                    >
                  </section>
                  <section class="action-block">
                    <h3>검토 처리</h3>
                    <div class="status-steps" role="group" aria-label="검토 상태 변경">
                      <button
                        v-for="(s, i) in ['OPEN', 'REVIEWING', 'RESOLVED']"
                        :key="s"
                        :class="{ selected: data.status === s }"
                        :aria-pressed="data.status === s"
                        @click="data.status !== s && review(s)"
                      >
                        <b>{{ i + 1 }}</b>{{ label(s) }}
                      </button>
                    </div>
                  </section>
                  <section class="action-block">
                    <h3>처리 기록</h3>
                    <ol v-if="data.activity?.length" class="activity-list">
                      <li v-for="a in data.activity" :key="a.id || a.timestamp">
                        <span class="grow">{{ a.message }}</span
                        ><small class="time">{{ date(a.timestamp) }}</small>
                      </li>
                    </ol>
                    <p v-else class="empty-inline">
                      아직 검토 기록이 없습니다. 위에서 상태를 바꾸면 여기에 기록됩니다.
                    </p>
                  </section></template
                ><template v-if="tab === 'Security References'"
                  ><h2>검색된 근거</h2>
                  <p class="ref-intro">
                    RAG 색인에서 찾은 정책 문서 조항입니다. 이 항목과 가장 관련 있는 문장을
                    먼저 보여 주며, 원문 전체는 자세히 보기에서 확인할 수 있습니다.
                  </p>
                  <section v-for="g in referenceGroups" :key="g.source" class="ref-folder">
                    <header>
                      <FolderOpen :size="18" /><span class="grow"
                        ><strong>{{ g.source }}</strong
                        ><small>{{ label(g.type) }} · 조항 {{ g.refs.length }}개</small></span
                      >
                    </header>
                    <article
                      v-for="r in g.refs"
                      :key="r.chunkId"
                      class="reference"
                      :class="{ cited: data.analysis?.citedReferenceIds?.includes(r.chunkId) }"
                    >
                      <div class="reference-head">
                        <FileText :size="16" /><h3>
                          <code>{{ r.sectionId }}</code> {{ r.sectionTitle }}
                        </h3>
                        <span class="tag">{{
                          data.analysis?.citedReferenceIds?.includes(r.chunkId)
                            ? "LLM이 인용한 근거"
                            : "검색된 참고 근거"
                        }}</span>
                      </div>
                      <blockquote>{{ keySentence(r) }}</blockquote>
                      <div class="reference-foot">
                        <small>{{ r.documentId }} v{{ r.documentVersion }} · {{ r.pageNumber }}쪽</small>
                        <button
                          class="text-button"
                          :aria-expanded="openRefs.includes(r.chunkId)"
                          @click="toggleRef(r.chunkId)"
                        >
                          {{ openRefs.includes(r.chunkId) ? "접기" : "자세히 보기"
                          }}<ChevronDown :size="14" :class="{ flip: openRefs.includes(r.chunkId) }" />
                        </button>
                      </div>
                      <p v-if="openRefs.includes(r.chunkId)" class="reference-full">{{ r.content }}</p>
                    </article>
                  </section>
                  <p v-if="!data.analysis?.references?.length">
                    검색된 근거가 없습니다. 출처를 추정하지 않습니다.
                  </p></template
                                >
              </section>
            </div>
            <section
              v-if="tab === 'AI Analysis' && data.analysis?.orchestration"
              class="panel detail-panel flow-panel"
             
            >
              <h2 class="step-title"><b>3</b>{{ data.analysis?.mode === 'VLM' ? '통합 VLM 분석 기록' : 'Agent가 근거를 모은 과정' }}</h2>
              <p class="step-sub">
                {{ data.analysis?.mode === 'VLM' ? '호스트가 수집한 이미지·코드·정책 근거를 VLM이 함께 판단한 기록입니다.' : 'AI의 해석에 앞서 Agent가 어떤 도구로 어떤 규정을 찾아봤는지 보여 줍니다.' }}
              </p>
                  <section v-if="data.analysis?.orchestration" class="review-evidence agent-flow">
                    <p class="flow-meta">
                      <span class="tag">{{ data.analysis.orchestration.selectionMode }}</span>
                      {{ data.analysis.orchestration.turns }}턴 · 이 항목의 규칙
                      <code>{{ data.ruleId }}</code>을 강조해 표시합니다
                    </p>
                    <div class="flow">
                      <div v-if="toolFlow.setup.length" class="flow-stage">
                        <span class="flow-title"><b>1</b>{{ data.analysis?.mode === 'VLM' ? '이미지·코드·정책 통합 판단' : '정책 확인' }}</span>
                        <ol>
                          <li
                            v-for="step in toolFlow.setup"
                            :key="step.turn"
                            class="flow-node"
                            :class="{ fail: step.status !== 'OK', fallback: !['LLM','VLM'].includes(step.mode) }"
                          >
                            <b>{{ step.turn }}</b
                            ><span>{{ toolLabels[step.tool] || step.tool }}<code>{{ step.tool }}</code></span>
                          </li>
                        </ol>
                      </div>
                      <div v-if="toolFlow.rules.length" class="flow-stage">
                        <span class="flow-title"><b>2</b>규칙별 근거 수집</span>
                        <div class="flow-rules">
                          <div
                            v-for="[rule, steps] in toolFlow.rules"
                            :key="rule"
                            class="flow-rule"
                            :class="{ current: rule === data.ruleId }"
                          >
                            <code>{{ rule }}</code>
                            <ol>
                              <li
                                v-for="step in steps"
                                :key="step.turn"
                                class="flow-node"
                                :class="{ fail: step.status !== 'OK', fallback: !['LLM','VLM'].includes(step.mode) }"
                              >
                                <b>{{ step.turn }}</b
                                ><span>{{ toolLabels[step.tool] || step.tool }}<code>{{ step.tool }}</code></span>
                              </li>
                            </ol>
                          </div>
                        </div>
                      </div>
                      <div v-if="toolFlow.finish.length" class="flow-stage">
                        <span class="flow-title"><b>3</b>분석 완료</span>
                        <ol>
                          <li
                            v-for="step in toolFlow.finish"
                            :key="step.turn"
                            class="flow-node done"
                            :class="{ fail: step.status !== 'OK' }"
                          >
                            <b>{{ step.turn }}</b
                            ><span>{{ toolLabels[step.tool] || step.tool }}<code>{{ step.tool }}</code></span>
                          </li>
                        </ol>
                      </div>
                    </div>
                    <small>VLM은 이미지·코드·RAG 통합 판단입니다. LLM·RULE_BASED·LLM_FALLBACK은 이전 검사 경로입니다.</small>
                  </section>
                                <small class="flow-tech"
                >분석 모드 {{ data.analysis?.mode || "대기"
                }}<template v-if="data.analysis?.model"> ({{ data.analysis.model }})</template
                ><template v-if="data.analysis?.contextBudget">
                  · 모델 호출 {{ data.analysis.contextBudget.calls }}회 · 입력 예산 상한 사용
                  {{ data.analysis.contextBudget.maxInputBound }} · 누적 예약
                  {{ data.analysis.contextBudget.reservedTokens }}</template
                ></small
              >
            </section>
</template
          >
          <template
            v-if="['logs', 'approvals'].includes(page) && !id"
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
              <div v-if="page === 'approvals'" class="approval-folders">
                <div
                  v-for="f in approvalFolders"
                  :key="f.name"
                  class="approval-folder"
                  :class="{ open: openedApprovals.includes(f.name), waiting: f.pending }"
                >
                  <button
                    class="approval-folder-bar"
                    :aria-expanded="openedApprovals.includes(f.name)"
                    @click="toggleApprovals(f.name)"
                  >
                    <component :is="openedApprovals.includes(f.name) ? FolderOpen : Folder" :size="20" />
                    <span class="grow"
                      ><strong>{{ f.name }}</strong
                      ><small
                        >승인 요청 {{ f.items.length }}건 · 승인 {{ f.approved }} · 거절
                        {{ f.rejected }}</small
                      ></span
                    ><span v-if="f.pending" class="approval-waiting"
                      ><i />승인 대기 {{ f.pending }}</span
                    ><ChevronDown :size="16" class="chevron" />
                  </button>
                  <div v-if="openedApprovals.includes(f.name)" class="approval-items">
                    <button
                      v-for="a in f.items"
                      :key="a.id"
                      class="list-row approval-row"
                      @click="drawer = a"
                    >
                      <ClipboardCheck :size="18" /><span class="grow"
                        ><strong>{{ a.action }}</strong
                        ><small class="meta"
                          ><span class="mono">{{ a.commitSha?.slice(0, 8) }}</span
                          ><span>{{ date(a.createdAt) }}</span></small
                        ></span
                      ><Badge :value="a.status" /><ChevronRight :size="16" />
                    </button>
                    <p v-if="!f.items.length" class="approval-none">승인 요청이 없습니다.</p>
                  </div>
                </div>
              </div>
              <div v-if="page === 'approvals' ? !approvalFolders.length : !visible.length" class="empty">
                <ShieldCheck :size="28" /><strong>표시할 항목이 없습니다</strong
                ><span>검사 결과가 저장되면 이곳에서 확인할 수 있습니다.</span>
              </div>
            </section></template
          >
          <Pager
            v-if="!id && !dash && !findingsPage && page !== 'approvals' && filtered.length"
            :page="current"
            :pages="pages"
            :total="filtered.length"
            @move="(step) => (current = Math.min(pages, Math.max(1, current + step)))"
          />
          <template v-if="dashStatus"
            ><section class="panel" v-if="data.failures?.length">
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
          ></template
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
          <h2>{{ drawer.action === 'CODING_PROPOSAL_APPROVED' ? '수정안 승인 알림' : '승인 요청' }}</h2>
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
            <p v-if="drawer.action === 'CODING_PROPOSAL_APPROVED'" class="note">
              검토자가 승인한 수정안의 알림입니다. 관련 검사에서 수정안을 확인할 수 있으며, 원본 코드 반영은 별도 작업입니다.
            </p>
            <p v-else class="note">
              승인하면 CSI 내부 보안 검토 이슈가 생성됩니다. 코드 수정이나 운영
              배포는 수행하지 않습니다.
            </p>
            <div v-if="drawer.status === 'PENDING' && drawer.action === 'CREATE_SECURITY_REVIEW_ISSUE'" class="drawer-actions">
              <button @click="decide(drawer, 'REJECTED')">거절</button
              ><button class="primary" @click="decide(drawer, 'APPROVED')">
                승인
              </button>
            </div>
            <p v-else>
              처리자 {{ drawer.decidedBy || "—" }}, {{ date(drawer.decidedAt) }}
            </p>
        </section>
      </div>
    </Transition>
    <Transition name="fade">
      <div v-if="projectModal" class="overlay center" @click.self="closeProjectModal">
        <form class="modal" @submit.prevent="addProject">
          <button
            type="button"
            class="close"
            @click="closeProjectModal"
            aria-label="닫기"
          >
            <X :size="20" />
          </button>
          <h2>프로젝트 등록</h2>
          <p>GitHub 저장소를 등록하고, 아키텍처 이미지를 필수로 첨부합니다.</p>
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
          ><div class="arch-field">
            <span class="arch-field-label">아키텍처 <small>필수 첨부</small></span>
            <button type="button" class="arch-pick" @click="archInput?.click()">
              <ImagePlus :size="15" />아키텍처 파일 선택
            </button>
            <input
              ref="archInput"
              type="file"
              multiple
              hidden
              aria-label="아키텍처 파일"
              :accept="ACCEPTED_TYPES.join(',')"
              @change="chooseArchFiles(($event.target as HTMLInputElement).files)"
            />
            <ul v-if="archFiles.length" class="arch-files">
              <li v-for="(f, i) in archFiles" :key="i">
                <span>{{ f.name }}</span
                ><small>{{ (f.size / 1024 / 1024).toFixed(2) }}MB</small
                ><button
                  type="button"
                  :aria-label="f.name + ' 빼기'"
                  @click="archFiles = archFiles.filter((_, j) => j !== i)"
                >
                  <X :size="14" />
                </button>
              </li>
            </ul>
            <small class="arch-hint"
              >아키텍처 파일을 1개 이상 첨부해야 등록할 수 있습니다. 첫 번째 파일을 분석하며, PDF는 첫 페이지를 사용합니다.
              PNG·JPEG·WebP·GIF·PDF, 파일당 최대 30MB. 분석용 변환 이미지는 5 MiB·16MP 이하입니다.</small
            >
          </div
          ><button class="primary" :disabled="registering || !archFiles.length">
            {{ registering ? "등록 중…" : "프로젝트 등록" }}
          </button>
        </form>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.arch-field{display:flex;flex-direction:column;gap:8px;margin:0 0 20px}
.arch-field-label{font-size:13px;font-weight:550;color:var(--ink-2)}
.arch-field-label small{margin-left:4px;font-weight:500;color:var(--ink-3)}
.arch-pick{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:10px;border:1px dashed var(--line-2);background:transparent;color:var(--ink-2)}
.arch-pick:hover{border-color:var(--blue);color:var(--blue)}
.arch-files{display:grid;gap:6px;margin:0;padding:0;list-style:none}
.arch-files li{display:flex;align-items:center;gap:8px;padding:6px 8px 6px 12px;border:1px solid var(--line);border-radius:var(--r-md);font-size:12px}
.arch-files li span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.arch-files li small{color:var(--ink-3)}
.arch-files li button{padding:4px;border:0;background:none;color:var(--ink-3)}
.arch-hint{font-size:12px;line-height:1.5;color:var(--ink-3)}
.analysis-status{margin-bottom:20px;padding:16px;border:1px solid #cbd5e1;border-radius:12px;background:#f8fafc;line-height:1.7}
.analysis-status p{margin:6px 0}
.analysis-status-warning{background:#fff7ed;border-color:#fdba74;color:#9a3412}
.report-narrative{margin:0 0 20px;padding:0 4px;color:var(--on-dark-2,#334155);font-size:15px;line-height:1.85}
</style>
