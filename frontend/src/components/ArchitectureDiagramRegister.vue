<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from "vue";
import { UploadCloud } from "lucide-vue-next";
import {
  uploadDiagram,
  getDiagramStatus,
  groupByIsolation,
  STATUS_LABEL,
  STATE_LABEL,
  type DiagramState,
} from "../lib/architectureDiagram";
import { useSession } from "../stores/session";

const props = defineProps<{ project: string }>();
const session = useSession();

const state = ref<DiagramState | null>(null),
  uploading = ref(false),
  input = ref<HTMLInputElement>();
let poll: ReturnType<typeof setInterval> | undefined;

const groups = computed(() => (state.value?.components ? groupByIsolation(state.value.components) : []));

function stopPolling() {
  clearInterval(poll);
  poll = undefined;
}

async function refresh() {
  try {
    state.value = await getDiagramStatus(props.project);
    if (state.value.status === "EXTRACTED") stopPolling();
  } catch {
    // 아직 업로드된 다이어그램이 없으면 404 — 조용히 무시, 업로드 화면 그대로 둠.
    state.value = null;
    stopPolling();
  }
}

function startPolling() {
  stopPolling();
  poll = setInterval(refresh, 2000);
}

async function choose(files?: FileList | null) {
  const file = files?.[0];
  if (input.value) input.value.value = "";
  if (!file) return;
  uploading.value = true;
  try {
    await uploadDiagram(props.project, file);
    await refresh();
    startPolling();
  } catch (e: any) {
    session.notify(e.message || "업로드에 실패했습니다.");
  } finally {
    uploading.value = false;
  }
}

refresh().then(() => {
  if (state.value && state.value.status !== "EXTRACTED") startPolling();
});

onBeforeUnmount(stopPolling);
</script>

<template>
  <div class="panel architecture-diagram-register">
    <h3>아키텍처 다이어그램 등록 (분석용)</h3>
    <p class="consent">
      이 이미지는 아키텍처 분석을 위해 서버로 전송됩니다. 기존 "아키텍처" 탭의 개인 보관함과는 별개입니다.
    </p>

    <input
      ref="input"
      type="file"
      accept="image/png,image/jpeg,image/webp,image/gif,application/pdf"
      style="display: none"
      @change="choose(($event.target as HTMLInputElement).files)"
    />
    <button class="primary" :disabled="uploading" @click="input?.click()">
      <UploadCloud :size="16" />{{ uploading ? "업로드 중…" : "다이어그램 업로드" }}
    </button>

    <div v-if="state" class="status">
      <p v-if="state.status !== 'EXTRACTED'" class="progress">
        {{ STATUS_LABEL[state.status] }}…
      </p>

      <template v-else>
        <p class="summary">{{ state.summary }}</p>
        <section v-for="group in groups" :key="group.key" class="isolation-group" :class="group.key.toLowerCase()">
          <h4>{{ group.label }} <span class="count">{{ group.items.length }}개</span></h4>
          <ul class="components">
            <li v-for="(c, i) in group.items" :key="i" class="component-card">
              <div class="component-head">
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
    </div>
  </div>
</template>

<style scoped>
.architecture-diagram-register {
  padding: 1rem;
}
.consent {
  color: var(--muted, #666);
  font-size: 0.85rem;
}
.progress {
  color: var(--muted, #666);
}
.summary {
  font-size: 1rem;
  font-weight: 500;
  margin-bottom: 1rem;
}
.isolation-group {
  margin-bottom: 1.25rem;
}
.isolation-group h4 {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}
.isolation-group .count {
  font-weight: 400;
  color: var(--muted, #666);
  font-size: 0.8rem;
}
/* 격리된 환경은 경고 톤, 실제 서비스는 중립 톤으로 — 핵심 구분을 색으로도 바로 보이게. */
.isolation-group.isolated h4 {
  color: #92620a;
}
.isolation-group.production h4 {
  color: #1d4ed8;
}
.component-card {
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
}
.isolated .component-card {
  border-left: 3px solid #d08c1d;
}
.production .component-card {
  border-left: 3px solid #93b4f0;
}
.component-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.component-card p {
  margin: 0.25rem 0 0;
  color: var(--muted, #555);
}
.badge {
  font-size: 0.75rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: var(--chip-bg, #eee);
}
</style>
