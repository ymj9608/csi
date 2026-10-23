import { api, csrfToken } from "./api";

export type DiagramStatus = "QUEUED" | "LOADING_MODEL" | "ANALYZING" | "EXTRACTED";

export interface ArchitectureComponent {
  name: string;
  role: string;
  isolationStatus: "ISOLATED" | "PRODUCTION" | "UNKNOWN";
  state: "OBSERVED" | "INFERRED" | "UNKNOWN";
}

export interface DiagramState {
  status: DiagramStatus;
  components: ArchitectureComponent[] | null;
  summary: string | null;
  confirmed: boolean;
}

// 업로드 진행 단계를 사람이 읽을 문구로 — coding_agent 수정안 화면의 단계 표시와 같은 패턴.
export const STATUS_LABEL: Record<DiagramStatus, string> = {
  QUEUED: "대기 중",
  LOADING_MODEL: "Qwen 모델 로드 중",
  ANALYZING: "아키텍처 인식 중",
  EXTRACTED: "인식 완료",
};

export const ISOLATION_LABEL: Record<ArchitectureComponent["isolationStatus"], string> = {
  PRODUCTION: "실제 서비스",
  ISOLATED: "격리된 환경",
  UNKNOWN: "판단 불가",
};

export const STATE_LABEL: Record<ArchitectureComponent["state"], string> = {
  OBSERVED: "확인됨",
  INFERRED: "추정",
  UNKNOWN: "판단 불가",
};

// 핵심 구분(실제 서비스 vs 격리된 환경)으로 묶어서 보여주기 위한 그룹핑.
// UNKNOWN은 "실제 서비스"처럼 안전하다고 오해하지 않도록 별도 그룹으로 둔다.
export function groupByIsolation(components: ArchitectureComponent[]) {
  const groups: Record<ArchitectureComponent["isolationStatus"], ArchitectureComponent[]> = {
    PRODUCTION: [],
    ISOLATED: [],
    UNKNOWN: [],
  };
  for (const c of components) groups[c.isolationStatus].push(c);
  return (["PRODUCTION", "ISOLATED", "UNKNOWN"] as const)
    .map((key) => ({ key, label: ISOLATION_LABEL[key], items: groups[key] }))
    .filter((g) => g.items.length > 0);
}

export async function uploadDiagram(projectId: string, file: File): Promise<void> {
  const token = await csrfToken();
  const body = new FormData();
  body.append("file", file);
  const r = await fetch(`/api/projects/${projectId}/architecture`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-TOKEN": token },
    body,
  });
  if (!r.ok) throw Error(`업로드 실패 (${r.status})`);
}

export const getDiagramStatus = (projectId: string): Promise<DiagramState> =>
  api(`/projects/${projectId}/architecture`);
