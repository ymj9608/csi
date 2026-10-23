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
