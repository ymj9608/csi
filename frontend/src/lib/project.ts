// 프로젝트 단위로 걸러 보는 화면입니다. 선택값은 ?project= 쿼리와 마지막 선택(localStorage)으로 유지합니다.
export const PROJECT_SCOPED = ["dashboard", "scans", "findings", "logs", "approvals"];
const KEY = "csi.project";

export function rememberedProject() {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

export function rememberProject(id: string) {
  try {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
  } catch {}
}

export function scopedLink(path: string, project: string) {
  return project && PROJECT_SCOPED.includes(path.slice(1))
    ? { path, query: { project } }
    : { path };
}
