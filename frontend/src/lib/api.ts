let csrf = "";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  if (method !== "GET" && !csrf) {
    const r = await fetch("/api/auth/csrf", { credentials: "same-origin" });
    if (!r.ok) throw Error("보안 세션을 시작할 수 없습니다.");
    csrf = (await r.json()).token;
  }
  const r = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-TOKEN": csrf } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) {
    csrf = "";
    if (!path.startsWith("/auth/"))
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      "로그인이 필요하거나 계정 정보가 올바르지 않습니다.",
      401,
    );
  }
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw Error(data.message || `요청 실패 (${r.status})`);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}
export function clearCsrf() {
  csrf = "";
}
export const date = (value?: string) =>
  value
    ? new Date(value).toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
