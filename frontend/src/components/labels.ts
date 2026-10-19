// API가 돌려주는 상태 코드를 화면에 표시할 한국어로 바꿉니다. 값 자체는 바꾸지 않습니다.
const labels: Record<string, string> = {
  CRITICAL: "치명",
  HIGH: "높음",
  MEDIUM: "중간",
  LOW: "낮음",
  QUEUED: "대기",
  RUNNING: "실행 중",
  COMPLETED: "완료",
  FAILED: "실패",
  ERROR: "오류",
  OPEN: "미해결",
  REVIEWING: "검토 중",
  RESOLVED: "해결",
  PENDING: "승인 대기",
  APPROVED: "승인",
  REJECTED: "거절",
  EXECUTED: "실행됨",
  NOT_SCANNED: "미검사",
  SUSPECTED: "의심",
  CONFIRMED: "확인됨",
  INTERNAL_POLICY: "사내 정책",
};
export const label = (value?: string) =>
  (value && labels[value.toUpperCase()]) || value || "—";
