<script setup lang="ts">
import { ref, onBeforeUnmount } from "vue";
import { UploadCloud } from "lucide-vue-next";
import {
  uploadDiagram,
  getDiagramStatus,
  STATUS_LABEL,
  type DiagramState,
} from "../lib/architectureDiagram";
import { useSession } from "../stores/session";

const props = defineProps<{ project: string }>();
const session = useSession();

const state = ref<DiagramState | null>(null),
  uploading = ref(false),
  input = ref<HTMLInputElement>();
let poll: ReturnType<typeof setInterval> | undefined;

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
        <ul class="components">
          <li v-for="(c, i) in state.components" :key="i" class="component-card">
            <div class="component-head">
              <strong>{{ c.name }}</strong>
              <span class="badge" :class="c.state.toLowerCase()">{{ c.state }}</span>
            </div>
            <p>{{ c.role }}</p>
            <span class="isolation" :class="c.isolationStatus.toLowerCase()">{{ c.isolationStatus }}</span>
          </li>
        </ul>
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
.component-card {
  border: 1px solid var(--border, #ddd);
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
}
.component-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.badge,
.isolation {
  font-size: 0.75rem;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: var(--chip-bg, #eee);
}
</style>
