<script setup lang="ts">
import { ref, shallowRef, computed, watch, onMounted, onBeforeUnmount } from "vue";
import {
  ArrowUpRight,
  Box,
  Boxes,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  FileText,
  FlaskConical,
  Folder,
  FolderOpen,
  GitBranch,
  Globe,
  HelpCircle,
  Monitor,
  Network,
  Server,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Users,
  X,
} from "lucide-vue-next";
import {
  uploadArchitecture,
  selectCodingArchitecture,
  loadFolders,
  saveFolders,
  newId,
  isPdf,
  acceptable,
  toImages,
  ACCEPTED_TYPES as TYPES,
  type ArchitectureFolder,
} from "../lib/architecture";
import {
  uploadDiagram,
  getDiagramStatus,
  retryDiagram,
  failureMessage,
  groupByIsolation,
  STATUS_LABEL,
  STATE_LABEL,
  type DiagramState,
} from "../lib/architectureDiagram";
import { useSession } from "../stores/session";
import { registrationImage } from "../lib/projectRegistration";
const props = defineProps<{ project: string; projectName: string }>();
const session = useSession();
const connecting = ref(false);
async function connectCoding() {
  if (connecting.value) return;
  const image = viewing.value?.image;
  const project = props.project;
  if (!project) return session.notify("프로젝트를 먼저 선택하세요.");
  if (!image) return session.notify("연결할 아키텍처 파일을 선택하세요.");
  connecting.value = true;
  try {
    const file = await registrationImage(new File([image.blob], image.name, { type: image.blob.type }));
    const saved = await uploadArchitecture(project, file);
    await selectCodingArchitecture(project, saved.id);
    session.notify("아키텍처가 연결되었습니다. 위험 항목에서 새 수정안을 요청하면 이 이미지와 정책 근거로 수정 지시문을 작성합니다.");
  } catch (error: any) {
    session.notify(error.message || "아키텍처 연결에 실패했습니다.");
  } finally { connecting.value = false; }
}

const fullDate = (value: string) =>
  new Date(value).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
const defaultName = computed(() => props.projectName || "전체 프로젝트");
// IndexedDB는 Vue Proxy를 복제하지 못하므로 원본 객체를 그대로 둡니다.
const folders = shallowRef<ArchitectureFolder[]>([]),
  urls = ref<Record<string, string>>({}),
  previews = ref<Record<string, string>>({}),
  opened = ref<string[]>([]),
  dragging = ref(false),
  busy = ref(false),
  input = ref<HTMLInputElement>();
// 최근에 만든 폴더가 위에 옵니다.
const sorted = computed(() =>
  [...folders.value].sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
);
// 폴더를 가리지 않고, 전체에서 가장 최근에 올라온 사진 — 업로드 칸 미리보기용.
const latestImage = computed(() => {
  const images = folders.value.flatMap((f) => f.images);
  return images.length
    ? images.reduce((a, b) => (b.uploadedAt > a.uploadedAt ? b : a))
    : null;
});
function show(list: ArchitectureFolder[]) {
  [...Object.values(urls.value), ...Object.values(previews.value)].forEach((u) =>
    URL.revokeObjectURL(u),
  );
  folders.value = list;
  const images = list.flatMap((f) => f.images);
  urls.value = Object.fromEntries(images.map((i) => [i.id, URL.createObjectURL(i.blob)]));
  previews.value = Object.fromEntries(
    images.filter((i) => i.preview).map((i) => [i.id, URL.createObjectURL(i.preview!)]),
  );
}
async function persist(list: ArchitectureFolder[]) {
  await saveFolders(props.project, list);
  show(list);
}
watch(
  () => [props.project, defaultName.value],
  async ([key, name]) => {
    try {
      const list = await loadFolders(key, name);
      if (key === props.project) show(list);
    } catch {
      show([]);
    }
  },
  { immediate: true },
);
// 마지막으로 펼쳐 본 뒤에 추가된 사진입니다.
const unseen = (folder: ArchitectureFolder) =>
  folder.images.filter((i) => i.uploadedAt > (folder.seenAt ?? ""));
// 폴더를 만든 뒤 가장 최근에 함께 추가된 사진 묶음입니다. 확인해도 사라지지 않는 기록입니다.
function lastAdded(folder: ArchitectureFolder) {
  const at = folder.images.reduce((a, i) => (i.uploadedAt > a ? i.uploadedAt : a), "");
  if (at <= folder.createdAt) return null;
  return { at, count: folder.images.filter((i) => i.uploadedAt === at).length };
}
const tick = ref(Date.now());
const timer = setInterval(() => (tick.value = Date.now()), 30_000);
function ago(value: string) {
  const minutes = Math.floor((tick.value - new Date(value).getTime()) / 60_000);
  if (minutes < 1) return "방금 전";
  if (minutes < 60) return `${minutes}분 전`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}시간 전`;
  if (minutes < 60 * 24 * 7) return `${Math.floor(minutes / 60 / 24)}일 전`;
  return fullDate(value);
}
// 펼칠 때 새 사진을 기억해 두고 NEW로 보여 준 뒤, 확인 시각을 저장해 배지를 없앱니다.
// 접으면 NEW 표시도 사라집니다.
const fresh = ref<Record<string, string[]>>({});
async function markSeen(id: string) {
  const list = folders.value.map((f) =>
    f.id === id ? { ...f, seenAt: new Date().toISOString() } : f,
  );
  try {
    await saveFolders(props.project, list);
    folders.value = list;
  } catch {}
}
function toggle(id: string) {
  if (opened.value.includes(id)) {
    opened.value = opened.value.filter((o) => o !== id);
    const { [id]: _closed, ...rest } = fresh.value;
    fresh.value = rest;
    return;
  }
  opened.value = [...opened.value, id];
  const folder = folders.value.find((f) => f.id === id);
  const ids = folder ? unseen(folder).map((i) => i.id) : [];
  if (ids.length) {
    fresh.value = { ...fresh.value, [id]: ids };
    markSeen(id);
  }
}

// 업로드할 파일을 고르면 바로 저장하지 않고 넣을 폴더를 먼저 고릅니다.
const pending = ref<File[]>([]),
  mode = ref<"existing" | "new">("new"),
  target = ref(""),
  folderName = ref("");

// 아키텍처 분석 — 업로드된 이미지 중 1장이 자동으로 서버에 전송되어 분석됩니다.
const analysis = ref<DiagramState | null>(null);
const retryingAnalysis = ref(false);
const analysisPending = computed(() => !!analysis.value && ["QUEUED", "LOADING_MODEL", "ANALYZING"].includes(analysis.value.status));
const analysisGroups = computed(() =>
  analysis.value?.components ? groupByIsolation(analysis.value.components) : [],
);
// 그룹 제목에 보여줄 아이콘 — 실제 서비스 vs 격리된 환경을 글자 전에 한눈에 구분하도록.
const ISOLATION_ICON = { PRODUCTION: Server, ISOLATED: ShieldAlert, UNKNOWN: HelpCircle } as const;
// 카드마다는 이름/역할의 키워드로 대략적인 종류를 추정해 다른 아이콘을 보여줍니다.
// 그룹 아이콘만 쓰면 한 그룹 안에서 전부 똑같아 보여 구분이 안 되므로.
const CATEGORY_ICONS: [RegExp, typeof Server][] = [
  [/사용자|user|public/i, Users],
  [/브라우저|browser|프론트|frontend|vue/i, Monitor],
  [/데이터|data\b|db\b|postgres|테이블/i, Database],
  [/docker|compose|배포|deploy|container/i, Boxes],
  [/테스트|test|pytest|playwright/i, FlaskConical],
  [/문서|docs|readme|export|내보내기/i, FileText],
  [/github|actions|\bci\b|\bcd\b|깃허브/i, GitBranch],
  [/보안|security|scan/i, ShieldCheck],
  [/외부|external/i, Globe],
];
function categoryIcon(c: { name: string; role: string }) {
  const text = `${c.name} ${c.role}`;
  return CATEGORY_ICONS.find(([re]) => re.test(text))?.[1] || Box;
}
let analysisPoll: ReturnType<typeof setInterval> | undefined;
function stopAnalysisPolling() {
  clearInterval(analysisPoll);
  analysisPoll = undefined;
}
async function refreshAnalysis() {
  try {
    analysis.value = await getDiagramStatus(props.project);
    if (!analysisPending.value) stopAnalysisPolling();
  } catch {
    analysis.value = null;
    stopAnalysisPolling();
  }
}
function startAnalysisPolling() {
  stopAnalysisPolling();
  if (analysisPending.value) analysisPoll = setInterval(refreshAnalysis, 2000);
}
async function retryAnalysis() {
  if (!analysis.value?.id || retryingAnalysis.value) return;
  retryingAnalysis.value = true;
  try {
    await retryDiagram(props.project, analysis.value.id);
    await refreshAnalysis();
    startAnalysisPolling();
  } catch (e: any) {
    session.notify(e.message || "분석을 다시 요청하지 못했습니다.");
  } finally {
    retryingAnalysis.value = false;
  }
}
async function requestAnalysis(image: { blob: Blob; name: string }) {
  try {
    await uploadDiagram(props.project, new File([image.blob], image.name, { type: image.blob.type }));
    await refreshAnalysis();
    startAnalysisPolling();
  } catch (e: any) {
    session.notify(e.message || "아키텍처 분석 요청에 실패했습니다.");
  }
}
// 이 프로젝트에 이미 진행 중이거나 끝난 분석이 있으면 이어서 보여줍니다.
// (프로젝트를 바꿔도 다시 조회합니다.)
watch(
  () => props.project,
  () => {
    stopAnalysisPolling();
    refreshAnalysis().then(() => {
      if (analysisPending.value) startAnalysisPolling();
    });
  },
  { immediate: true },
);
function uniqueName(base: string) {
  const names = new Set(folders.value.map((f) => f.name));
  let name = base,
    n = 2;
  while (names.has(name)) name = `${base} (${n++})`;
  return name;
}
function choose(files?: FileList | null) {
  const all = Array.from(files || []);
  const accepted = all.filter(acceptable);
  if (input.value) input.value.value = "";
  if (!all.length) return;
  if (!accepted.length)
    return session.notify("PNG, JPEG, WebP, GIF, PDF 형식의 30MB 이하 파일만 올릴 수 있습니다.");
  if (accepted.length < all.length)
    session.notify(`형식이나 크기가 맞지 않는 ${all.length - accepted.length}장은 제외했습니다.`);
  pending.value = accepted;
  mode.value = folders.value.length ? "existing" : "new";
  target.value = sorted.value[0]?.id || "";
  folderName.value = uniqueName(defaultName.value);
}
async function upload() {
  busy.value = true;
  const now = new Date().toISOString();
  const images = await toImages(pending.value, now);
  let id = target.value;
  let list: ArchitectureFolder[];
  if (mode.value === "new") {
    id = newId();
    const name = folderName.value.trim() || uniqueName(defaultName.value);
    list = [...folders.value, { id, name, createdAt: now, seenAt: now, images }];
  } else {
    // 펼쳐 둔 폴더에 추가하면 바로 보이므로 배지 대신 NEW만 붙입니다.
    const open = opened.value.includes(id);
    list = folders.value.map((f) =>
      f.id === id
        ? { ...f, images: [...f.images, ...images], ...(open ? { seenAt: now } : {}) }
        : f,
    );
    if (open)
      fresh.value = { ...fresh.value, [id]: [...(fresh.value[id] || []), ...images.map((i) => i.id)] };
  }
  try {
    // 폴더는 접힌 상태로 두고, 화살표를 눌러야 사진이 보입니다.
    await persist(list);
    pending.value = [];
    // 이미 완료된 분석 결과가 있으면 새로 업로드해도 자동으로 재분석하지 않는다 —
    // 미리보기 목적으로 사진만 더 올리고 싶을 때 기존 분석(최대 8분 걸림)을 잃지 않게.
    // 아직 분석이 없거나 실패한 상태일 때만 이번 업로드로 자동 분석을 시작한다.
    if (analysis.value?.status === "EXTRACTED") {
      session.notify(`아키텍처 이미지 ${images.length}장을 저장했습니다. (기존 분석 결과는 그대로 유지됩니다)`);
    } else {
      session.notify(`아키텍처 이미지 ${images.length}장을 저장했습니다.`);
      // 한 번에 여러 장을 올려도 분석은 항상 1장만 — 맨 처음 이미지로 자동 분석 요청.
      // (백엔드가 "프로젝트당 다이어그램 1장" 구조라, 여러 장을 전부 분석하면
      // 매번 이전 결과를 덮어쓰며 반복 실행되므로 일부러 막는다.)
      requestAnalysis(images[0]);
    }
  } catch {
    session.notify("이 브라우저에 이미지를 저장할 수 없습니다.");
  } finally {
    busy.value = false;
  }
}
function drop(e: DragEvent) {
  dragging.value = false;
  choose(e.dataTransfer?.files);
}

// 폴더 삭제는 실수를 막기 위해 한 번 더 눌러야 합니다.
const confirmDelete = ref("");
async function removeFolder(folder: ArchitectureFolder) {
  if (confirmDelete.value !== folder.id) return (confirmDelete.value = folder.id);
  confirmDelete.value = "";
  try {
    await persist(folders.value.filter((f) => f.id !== folder.id));
    session.notify("폴더를 삭제했습니다.");
  } catch {
    session.notify("폴더를 삭제할 수 없습니다.");
  }
}

// 썸네일을 누르면 크게 봅니다.
const viewer = ref<{ folder: string; index: number } | null>(null);
const viewing = computed(() => {
  const folder = folders.value.find((f) => f.id === viewer.value?.folder);
  const image = folder?.images[viewer.value!.index];
  return folder && image ? { folder, image } : null;
});
function move(step: number) {
  if (!viewing.value) return;
  const count = viewing.value.folder.images.length;
  viewer.value = { ...viewer.value!, index: (viewer.value!.index + step + count) % count };
}
async function removeImage() {
  if (!viewing.value) return;
  const { folder, image } = viewing.value;
  const images = folder.images.filter((i) => i.id !== image.id);
  try {
    // 마지막 사진을 지우면 빈 폴더도 함께 없앱니다.
    await persist(
      images.length
        ? folders.value.map((f) => (f.id === folder.id ? { ...f, images } : f))
        : folders.value.filter((f) => f.id !== folder.id),
    );
    if (!images.length) viewer.value = null;
    else viewer.value = { folder: folder.id, index: Math.min(viewer.value!.index, images.length - 1) };
    session.notify("아키텍처 이미지를 삭제했습니다.");
  } catch {
    session.notify("이미지를 삭제할 수 없습니다.");
  }
}
function keydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    viewer.value = null;
    pending.value = [];
  } else if (viewer.value && e.key === "ArrowLeft") move(-1);
  else if (viewer.value && e.key === "ArrowRight") move(1);
}
onMounted(() => window.addEventListener("keydown", keydown));
onBeforeUnmount(() => {
  window.removeEventListener("keydown", keydown);
  clearInterval(timer);
  stopAnalysisPolling();
  show([]);
});
</script>
<template>
  <!-- 업로드 칸은 항상 위에 긴 직사각형으로 두고, 폴더는 그 아래에 목록으로 쌓습니다. -->
  <div class="architecture-layout">
    <section class="panel architecture-upload">
      <input
        ref="input"
        type="file"
        :accept="TYPES.join(',')"
        multiple
        hidden
        @change="choose(($event.target as HTMLInputElement).files)"
      />
      <button
        class="architecture-drop"
        :class="{ dragging, 'has-preview': latestImage }"
        :disabled="busy"
        @click="input?.click()"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="drop"
      >
        <template v-if="latestImage">
          <img
            v-if="previews[latestImage.id] || !isPdf(latestImage)"
            class="drop-preview"
            :src="previews[latestImage.id] || urls[latestImage.id]"
            :alt="latestImage.name"
          /><span v-else class="thumb-file"><FileText :size="28" />{{ latestImage.name }}</span>
          <strong>최신 업로드 · {{ ago(latestImage.uploadedAt) }}</strong
          ><span>클릭하거나 파일을 끌어다 놓으면 새 이미지를 추가합니다.</span>
        </template>
        <template v-else>
          <Network :size="28" /><strong>아키텍처 이미지를 올려 주세요</strong
          ><span
            >클릭하거나 파일을 끌어다 놓으세요. 여러 장을 한 번에 올릴 수 있습니다.
            PNG·JPEG·WebP·GIF·PDF, 파일당 최대 30MB</span
          >
        </template>
      </button>
    </section>
    <section v-if="folders.length" class="panel architecture-folders">
      <div class="panel-title">
        <h2>폴더 <small>{{ folders.length }}개</small></h2>
      </div>
      <div class="folder-list">
        <div
          v-for="folder in sorted"
          :key="folder.id"
          class="folder"
          :class="{ open: opened.includes(folder.id) }"
        >
          <div class="folder-bar">
            <button
              class="folder-toggle"
              :aria-expanded="opened.includes(folder.id)"
              @click="toggle(folder.id)"
            >
              <component :is="opened.includes(folder.id) ? FolderOpen : Folder" :size="20" />
              <span class="folder-name"
                ><span class="folder-title"
                  ><strong>{{ folder.name }}</strong
                  ><span v-if="unseen(folder).length" class="folder-new"
                    >+{{ unseen(folder).length }} 새 사진</span
                  ></span
                ><small
                  >이미지 {{ folder.images.length }}장 · {{ fullDate(folder.createdAt) }} 생성<template
                    v-if="lastAdded(folder)"
                  >
                    · {{ ago(lastAdded(folder)!.at) }} {{ lastAdded(folder)!.count }}장 추가</template
                  ></small
                ></span
              ><ChevronDown :size="16" class="chevron" />
            </button>
            <button
              class="folder-delete"
              :class="{ confirm: confirmDelete === folder.id }"
              :aria-label="folder.name + ' 폴더 삭제'"
              @click="removeFolder(folder)"
              @blur="confirmDelete = ''"
            >
              <Trash2 :size="15" /><span v-if="confirmDelete === folder.id">삭제 확인</span>
            </button>
          </div>
          <div v-if="opened.includes(folder.id)" class="thumbs">
            <button
              v-for="(image, index) in folder.images"
              :key="image.id"
              class="thumb"
              :aria-label="`${folder.name} ${index + 1}번째 사진 크게 보기`"
              @click="viewer = { folder: folder.id, index }"
            >
              <img v-if="previews[image.id] || !isPdf(image)" :src="previews[image.id] || urls[image.id]" :alt="image.name" />
              <span v-else class="thumb-file"><FileText :size="28" />{{ image.name }}</span>
              <span class="thumb-index">{{ index + 1 }}</span
              ><span v-if="isPdf(image)" class="thumb-type">PDF</span
              ><span v-if="fresh[folder.id]?.includes(image.id)" class="thumb-new">NEW</span>
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
  <p class="evidence-note">
    이미지는 이 브라우저에 프로젝트별로 저장됩니다. 업로드 시 그중 1장은 아키텍처 분석을 위해 서버로
    전송되어 CSI 보안 검토에 참고 자료로 쓰입니다.
  </p>

  <section v-if="analysis" class="panel architecture-analysis">
    <h3>아키텍처 분석 결과</h3>
    <div v-if="analysis.status === 'FAILED'" role="alert" class="analysis-failure">
      <p><strong>분석 실패</strong> · {{ failureMessage(analysis.errorCode) }}</p>
      <p>Worker와 모델 연결 상태를 확인한 후 다시 요청해 주세요. 저장된 이미지로 재분석합니다.</p>
      <button v-if="analysis.id" :disabled="retryingAnalysis" @click="retryAnalysis">
        {{ retryingAnalysis ? '요청 중…' : '분석 다시 시도' }}
      </button>
    </div>
    <p v-else-if="analysisPending" class="analysis-progress">
      {{ STATUS_LABEL[analysis.status] }}…
    </p>
    <template v-else>
      <p class="analysis-summary">{{ analysis.summary }}</p>
      <section
        v-for="group in analysisGroups"
        :key="group.key"
        class="isolation-group"
        :class="group.key.toLowerCase()"
      >
        <h4>
          <component :is="ISOLATION_ICON[group.key]" :size="15" />{{ group.label }}
          <span class="count">{{ group.items.length }}개</span>
        </h4>
        <ul class="components">
          <li v-for="(c, i) in group.items" :key="i" class="component-card">
            <div class="component-head">
              <component :is="categoryIcon(c)" :size="16" class="component-icon" />
              <strong>{{ c.name }}</strong>
              <!-- 확인된(OBSERVED) 항목은 뱃지를 생략 — 불확실한 것만 눈에 띄게 둔다. -->
              <span v-if="c.state !== 'OBSERVED'" class="badge" :class="c.state.toLowerCase()">
                {{ STATE_LABEL[c.state] }}
              </span>
            </div>
            <p>{{ c.role }}</p>
          </li>
        </ul>
      </section>
    </template>
  </section>

  <Transition name="fade">
    <div v-if="pending.length" class="overlay center" @click.self="pending = []">
      <form class="modal folder-modal" @submit.prevent="upload">
        <button type="button" class="close" @click="pending = []" aria-label="닫기">
          <X :size="20" />
        </button>
        <h2>어느 폴더에 넣을까요?</h2>
        <p>선택한 이미지 {{ pending.length }}장</p>
        <div class="folder-choice" role="radiogroup" aria-label="저장 위치">
          <label class="choice" :class="{ disabled: !folders.length }"
            ><span
              ><input
                type="radio"
                value="existing"
                v-model="mode"
                :disabled="!folders.length"
              />기존 폴더에 추가</span
            ><select
              v-if="mode === 'existing'"
              v-model="target"
              aria-label="추가할 폴더"
            >
              <option v-for="f in sorted" :key="f.id" :value="f.id">
                {{ f.name }} ({{ f.images.length }}장)
              </option>
            </select></label
          ><label class="choice"
            ><span><input type="radio" value="new" v-model="mode" />새 폴더 만들기</span
            ><input
              v-if="mode === 'new'"
              v-model="folderName"
              maxlength="80"
              aria-label="새 폴더 이름"
              placeholder="폴더 이름"
          /></label>
        </div>
        <div class="drawer-actions">
          <button type="button" @click="pending = []">취소</button
          ><button class="primary" :disabled="busy">업로드</button>
        </div>
      </form>
    </div>
  </Transition>

  <Transition name="fade">
    <div v-if="viewing" class="overlay center" @click.self="viewer = null">
      <section class="viewer" role="dialog" aria-modal="true" aria-label="아키텍처 이미지 크게 보기">
        <button class="close" @click="viewer = null" aria-label="닫기"><X :size="20" /></button>
        <div class="viewer-stage">
          <button
            v-if="viewing.folder.images.length > 1"
            class="viewer-nav prev"
            @click="move(-1)"
            aria-label="이전 사진"
          >
            <ChevronLeft :size="22" />
          </button>
          <iframe
            v-if="isPdf(viewing.image)"
            :src="urls[viewing.image.id]"
            :title="viewing.image.name"
          />
          <img v-else :src="urls[viewing.image.id]" :alt="viewing.image.name" />
          <button
            v-if="viewing.folder.images.length > 1"
            class="viewer-nav next"
            @click="move(1)"
            aria-label="다음 사진"
          >
            <ChevronRight :size="22" />
          </button>
        </div>
        <div class="viewer-info">
          <dl>
            <dt>업로드 날짜</dt>
            <dd>{{ fullDate(viewing.image.uploadedAt) }}</dd>
            <dt>순서</dt>
            <dd>
              {{ viewer!.index + 1 }}번째 사진 (전체 {{ viewing.folder.images.length }}장)
            </dd>
            <dt>폴더</dt>
            <dd>{{ viewing.folder.name }}</dd>
            <dt>파일</dt>
            <dd>
              {{ viewing.image.name }} · {{ (viewing.image.size / 1024 / 1024).toFixed(2) }}MB
            </dd>
          </dl>
          <span class="viewer-actions"
            ><a :href="urls[viewing.image.id]" target="_blank" rel="noopener"
              >원본 보기 <ArrowUpRight :size="14" /></a
            ><button :disabled="connecting || !project" @click="connectCoding">{{ connecting ? '연결 중…' : '코딩 Agent에 연결' }}</button
            ><button @click="removeImage"><Trash2 :size="15" />삭제</button></span
          >
        </div>
      </section>
    </div>
  </Transition>
</template>
<style scoped>
.architecture-layout {
  display: grid;
  gap: 20px;
  align-items: start;
}
.architecture-layout .panel {
  margin-bottom: 0;
}
.panel-title h2 small {
  margin-left: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-3);
}
.folder-list {
  display: grid;
  gap: 10px;
  padding: 0 20px 20px;
}
.folder {
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
}
.folder.open {
  border-color: var(--blue);
}
.folder-bar {
  display: flex;
  align-items: center;
}
.folder-toggle {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 0;
  background: none;
  text-align: left;
}
.folder-toggle > svg:first-child {
  flex-shrink: 0;
  color: var(--blue);
}
.folder-name {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.folder-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.folder-new {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--blue);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.folder-name strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: var(--ink);
}
.folder-name small {
  font-size: 12px;
  color: var(--ink-3);
}
.chevron {
  flex-shrink: 0;
  color: var(--ink-3);
  transition: transform 0.15s;
}
.folder.open .chevron {
  transform: rotate(180deg);
}
.folder-delete {
  margin-right: 10px;
  padding: 7px;
  border: 0;
  background: none;
  color: var(--ink-3);
}
.folder-delete.confirm {
  padding: 7px 10px;
  border: 1px solid #e5484d;
  color: #e5484d;
}
.thumbs {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding: 0 16px 16px;
}
.thumb {
  position: relative;
  flex: 0 0 auto;
  width: 140px;
  height: 96px;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: #fff;
}
.thumb:hover {
  border-color: var(--blue);
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-file {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 100%;
  padding: 0 8px;
  overflow: hidden;
  font-size: 11px;
  color: var(--ink-3);
  word-break: break-all;
}
.thumb-file svg {
  color: var(--blue);
}
.thumb-type {
  position: absolute;
  right: 6px;
  top: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #e5484d;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}
.thumb-new {
  position: absolute;
  left: 6px;
  top: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--blue);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}
.thumb-index {
  position: absolute;
  left: 6px;
  bottom: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgb(22 20 63 / 0.7);
  color: #fff;
  font-size: 11px;
}
.architecture-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: calc(100% - 40px);
  margin: 20px;
  padding: 48px 20px;
  border: 2px dashed var(--line);
  border-radius: var(--r-lg);
  background: transparent;
  color: var(--ink-3);
  font-size: 13px;
  text-align: center;
}
.architecture-drop svg {
  color: var(--blue-light);
}
.architecture-drop strong {
  color: var(--ink);
  font-size: 14px;
}
.architecture-drop.dragging,
.architecture-drop:hover {
  border-color: var(--blue);
}
.architecture-drop.has-preview {
  padding: 20px;
}
.drop-preview {
  max-width: 420px;
  max-height: 280px;
  object-fit: contain;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: #fff;
}
.folder-modal p {
  font-size: 13px;
  color: var(--ink-3);
}
.folder-choice {
  display: grid;
  gap: 10px;
  margin: 18px 0;
}
.folder-modal .choice {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.choice:has(input[type="radio"]:checked) {
  border-color: var(--blue);
}
.choice.disabled {
  opacity: 0.5;
}
.choice > span {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
}
.choice input[type="radio"] {
  padding: 0;
  accent-color: var(--blue);
}
.viewer {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(1100px, calc(100% - 32px));
  max-height: calc(100% - 32px);
  padding: 48px 24px 20px;
  background: var(--surface);
  border-radius: 20px;
  box-shadow: 0 24px 60px rgb(22 20 63 / 0.18);
}
.viewer-stage {
  position: relative;
  display: flex;
  justify-content: center;
  min-height: 0;
}
.viewer-stage iframe {
  width: 100%;
  height: calc(100vh - 260px);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: #fff;
}
.viewer-stage img {
  max-width: 100%;
  max-height: calc(100vh - 260px);
  object-fit: contain;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: #fff;
}
.viewer-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  padding: 8px;
  border-radius: 999px;
  box-shadow: var(--shadow);
}
.viewer-nav.prev {
  left: 8px;
}
.viewer-nav.next {
  right: 8px;
}
.viewer-info {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  font-size: 13px;
}
.viewer-info dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 14px;
  margin: 0;
}
.viewer-info dt {
  color: var(--ink-3);
}
.viewer-info dd {
  margin: 0;
  color: var(--ink);
}
.viewer-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.viewer-actions a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--blue);
  font-weight: 600;
}
.architecture-analysis {
  padding: 20px;
}
.analysis-progress {
  color: var(--ink-3);
}
.analysis-summary {
  font-size: 15px;
  font-weight: 500;
  margin-bottom: 16px;
}
.isolation-group {
  margin-bottom: 18px;
}
.isolation-group h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  margin-bottom: 8px;
}
.isolation-group .count {
  font-weight: 400;
  color: var(--ink-3);
  font-size: 12px;
}
/* 격리된 환경은 경고 톤, 실제 서비스는 중립 톤으로 — 핵심 구분을 색으로도 바로 보이게. */
.isolation-group.isolated h4 {
  color: #92620a;
}
.isolation-group.production h4 {
  color: #1d4ed8;
}
.components {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.architecture-analysis .component-card {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 10px 12px;
}
.architecture-analysis .component-card p {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.isolated .component-card {
  border-left: 3px solid #d08c1d;
}
.production .component-card {
  border-left: 3px solid #93b4f0;
}
.architecture-analysis .component-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.architecture-analysis .component-head strong {
  flex: 1;
  min-width: 0;
}
.component-icon {
  flex-shrink: 0;
  color: var(--ink-3);
}
.isolated .component-icon {
  color: #92620a;
}
.production .component-icon {
  color: #1d4ed8;
}
.architecture-analysis .component-card p {
  margin: 4px 0 0;
  color: var(--ink-3);
  font-size: 13px;
}
.architecture-analysis .badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--surface-2, #eee);
}
</style>
