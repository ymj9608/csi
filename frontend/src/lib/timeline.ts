// 검사 실행 로그를 단계별로 묶어 타임라인과 단계 막대로 보여 주기 위한 계산입니다.
export const STAGES = [
  { key: "intake", name: "접수", color: "#8fa8ff" },
  { key: "prepare", name: "준비", color: "#5b7cf0" },
  { key: "investigate", name: "근거 수집", color: "#3f5ee8" },
  { key: "analysis", name: "위험 분석", color: "#3a2fb8" },
  { key: "report", name: "리포트", color: "#1F8A63" },
  { key: "approval", name: "승인", color: "#C27A00" },
] as const;

const STAGE_OF: Record<string, number> = {
  SCAN_ACCEPTED: 0, KAFKA_PUBLISHED: 0, KAFKA_RETRY: 0, DELIVERY_FAILED: 0,
  validate_scan: 1, load_findings: 1,
  select_analysis_tools: 2, model_decision: 2, assess_evidence: 2, agent_fallback: 2,
  red_risk_analysis: 3, blue_defense_verification: 3, context_budget: 3, llm_fallback: 3,
  generate_security_report: 4, persist_result: 4, finalize: 4, REPORT_SAVED: 4,
  approval_interrupt: 5, APPROVAL_DECIDED: 5, ISSUE_CREATED: 5,
};

export function buildTimeline(logs: any[]) {
  const sorted = [...(logs || [])].sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)));
  if (!sorted.length) return { start: 0, total: 0, groups: [] as any[] };
  const start = Date.parse(sorted[0].timestamp);
  const end = Date.parse(sorted[sorted.length - 1].timestamp);
  // MCP 호출처럼 여러 단계에서 나오는 이벤트는 직전 단계에 붙여 순서가 뒤로 가지 않게 합니다.
  let stage = 0;
  const groups = STAGES.map((s) => ({ ...s, events: [] as any[], from: 0, to: 0 }));
  for (const e of sorted) {
    const mapped = STAGE_OF[e.eventType];
    if (mapped !== undefined && mapped > stage) stage = mapped;
    groups[stage].events.push({ ...e, offset: Date.parse(e.timestamp) - start });
  }
  const used = groups.filter((g) => g.events.length);
  used.forEach((g, i) => {
    g.from = g.events[0].offset;
    g.to = i + 1 < used.length ? used[i + 1].events[0].offset : end - start;
  });
  return { start, total: end - start, groups: used };
}

export function elapsed(ms: number) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)}초` : `${Math.floor(s / 60)}분 ${Math.round(s % 60)}초`;
}
