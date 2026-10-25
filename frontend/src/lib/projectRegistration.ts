import { ApiError, csrfToken } from "./api";
import { acceptable, renderPdfPreview } from "./architecture";

/** Keep gallery formats; send an actual model-readable image to the server. */
export async function registrationImage(file?: File): Promise<File> {
  if (!file || !file.size || !acceptable(file))
    throw Error("아키텍처 파일을 필수로 첨부하세요. 지원 형식과 크기를 확인해 주세요.");
  let image: Blob = file;
  if (file.type === "application/pdf") {
    const preview = await renderPdfPreview(file, 1600);
    if (!preview) throw Error("PDF 첫 페이지를 읽을 수 없습니다. PNG/JPEG 이미지로 첨부해 주세요.");
    image = preview;
  } else if (!["image/png", "image/jpeg"].includes(file.type)) {
    const bitmap = await createImageBitmap(file);
    try {
      if (bitmap.width > 8192 || bitmap.height > 8192 || bitmap.width * bitmap.height > 16_000_000)
        throw Error("분석 이미지는 16MP, 각 변 8192px 이하여야 합니다.");
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      canvas.getContext("2d")!.drawImage(bitmap, 0, 0);
      image = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
        (blob) => blob ? resolve(blob) : reject(Error("이미지를 변환할 수 없습니다.")), "image/png",
      ));
    } finally { bitmap.close(); }
  }
  if (image.size > 5 * 1024 * 1024)
    throw Error("서버 분석용 이미지는 5 MiB 이하여야 합니다. 이미지 크기를 줄여 주세요.");
  return image === file ? file : new File([image], `${file.name}.png`, { type: "image/png" });
}

export async function registerProject(repository: string, defaultBranch: string, file?: File) {
  const image = await registrationImage(file);
  const body = new FormData();
  body.append("repository", repository);
  body.append("defaultBranch", defaultBranch);
  body.append("architecture", image);
  const response = await fetch("/api/projects", {
    method: "POST", credentials: "same-origin",
    headers: { "X-CSRF-TOKEN": await csrfToken() }, body,
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event("session-expired"));
    throw new ApiError("로그인이 필요합니다.", 401);
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw Error(error.message || `프로젝트 등록 실패 (${response.status})`);
  }
  return response.json() as Promise<{ id: string; diagramId: string; architectureStatus: "QUEUED" }>;
}
