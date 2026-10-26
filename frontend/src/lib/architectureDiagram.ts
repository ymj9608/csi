import { api, csrfToken } from "./api";
import { registrationImage } from "./projectRegistration";

export type DiagramStatus = "QUEUED" | "LOADING_MODEL" | "ANALYZING" | "EXTRACTED" | "FAILED";

export interface ArchitectureComponent {
  name: string;
  role: string;
  isolationStatus: "ISOLATED" | "PRODUCTION" | "UNKNOWN";
  state: "OBSERVED" | "INFERRED" | "UNKNOWN";
}

export interface DiagramState {
  id?: string;
  errorCode?: string | null;
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
  FAILED: "분석 실패",
};

export function failureMessage(code?: string | null): string {
  const messages: Record<string, string> = {
    MODEL_TIMEOUT: "모델 응답 시간이 초과되었습니다.",
    MODEL_UNAVAILABLE: "분석 모델에 연결할 수 없거나 모델 요청이 실패했습니다.",
    INVALID_RESULT: "모델이 올바른 형식의 분석 결과를 반환하지 못했습니다.",
    BACKEND_UNAVAILABLE: "분석 자료 조회 또는 결과 저장에 실패했습니다.",
    WORKER_TIMEOUT: "제한 시간 안에 분석이 완료되지 않았습니다. Worker 실행 상태를 확인해 주세요.",
  };
  return messages[code || ""] || "아키텍처 분석을 완료하지 못했습니다.";
}

export const retryDiagram = (projectId: string, diagramId: string): Promise<{id: string; status: DiagramStatus}> =>
  api(`/projects/${projectId}/architecture/retry`, "POST", {diagramId});

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
  body.append("file", await registrationImage(file));
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
