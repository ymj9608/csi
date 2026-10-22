// 아키텍처 이미지는 서버 업로드 없이 브라우저 IndexedDB에 프로젝트별 폴더 목록으로 보관합니다.
const DB = "csi",
  STORE = "architecture";
export interface ArchitectureImage {
  id: string;
  blob: Blob;
  name: string;
  size: number;
  uploadedAt: string;
  // PDF는 첫 페이지를 그린 PNG를 썸네일로 함께 보관합니다.
  preview?: Blob;
}
export const isPdf = (image: { blob: Blob }) => image.blob.type === "application/pdf";

// pdf.js는 PDF를 올릴 때만 불러옵니다. 그리지 못하면 썸네일 없이 저장합니다.
export async function renderPdfPreview(file: Blob, width = 480): Promise<Blob | undefined> {
  try {
    const pdfjs = await import("pdfjs-dist");
    pdfjs.GlobalWorkerOptions.workerSrc = (
      await import("pdfjs-dist/build/pdf.worker.min.mjs?url")
    ).default;
    const pdf = await pdfjs.getDocument({ data: await file.arrayBuffer(), isEvalSupported: false })
      .promise;
    try {
      const page = await pdf.getPage(1);
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: width / base.width });
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      await page.render({ canvasContext: ctx, viewport }).promise;
      return (await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"))) || undefined;
    } finally {
      pdf.destroy();
    }
  } catch {
    return undefined;
  }
}
export interface ArchitectureFolder {
  id: string;
  name: string;
  createdAt: string;
  // 폴더를 마지막으로 펼쳐 본 시각. 이후에 추가된 사진을 "새 사진"으로 표시합니다.
  seenAt?: string;
  images: ArchitectureImage[];
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await open();
  try {
    return await new Promise<T>((resolve, reject) => {
      const req = fn(db.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

// 프로젝트를 고르지 않은 경우는 "전체 프로젝트" 목록 하나로 보관합니다.
const key = (project: string) => project || "all";
// crypto.randomUUID는 HTTPS·localhost에서만 쓸 수 있어 LAN 주소 접속에서도 되는 값을 씁니다.
export const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2);

// 이전 버전은 이미지 한 장 또는 폴더 없는 이미지 목록을 저장했습니다. 읽을 때 폴더 하나로 묶습니다.
function migrate(value: any, name: string): ArchitectureFolder[] {
  if (!value) return [];
  const list = Array.isArray(value) ? value : [value];
  // 확인 기록이 없던 폴더는 모두 확인한 상태로 시작합니다.
  if (!list.length || "images" in list[0])
    return list.map((f: ArchitectureFolder) => ({
      ...f,
      seenAt: f.seenAt ?? f.images.reduce((a, i) => (i.uploadedAt > a ? i.uploadedAt : a), f.createdAt),
    }));
  const images = list.map((i: any) => ({
    id: i.id || newId(),
    blob: i.blob,
    name: i.name,
    size: i.size,
    uploadedAt: i.updatedAt,
  }));
  const createdAt = images[0].uploadedAt;
  return [{ id: newId(), name, createdAt, seenAt: createdAt, images }];
}
export const loadFolders = async (project: string, name: string) =>
  migrate(await run<any>("readonly", (s) => s.get(key(project))), name);
export const saveFolders = (project: string, folders: ArchitectureFolder[]) =>
  run<void>("readwrite", (s) =>
    folders.length ? s.put(folders, key(project)) : s.delete(key(project)),
  );

// SVG는 스크립트를 담을 수 있어 래스터 이미지와 PDF만 받습니다.
export const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"];
export const MAX_BYTES = 30 * 1024 * 1024;
export const acceptable = (file: File) => ACCEPTED_TYPES.includes(file.type) && file.size <= MAX_BYTES;
export const toImages = (files: File[], uploadedAt: string): Promise<ArchitectureImage[]> =>
  Promise.all(
    files.map(async (f) => ({
      id: newId(),
      blob: f,
      name: f.name,
      size: f.size,
      uploadedAt,
      ...(f.type === "application/pdf" ? { preview: await renderPdfPreview(f) } : {}),
    })),
  );
// 프로젝트 등록처럼 화면 밖에서 새 폴더를 만들 때 씁니다.
export async function addFolder(project: string, name: string, files: File[]) {
  const now = new Date().toISOString();
  const folders = await loadFolders(project, name);
  const images = await toImages(files, now);
  await saveFolders(project, [...folders, { id: newId(), name, createdAt: now, seenAt: now, images }]);
}
