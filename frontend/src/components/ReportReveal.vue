<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  stage: number;
  total: number;
  active: boolean;
  labels: string[];
  completedAt?: string;
}>();
const emit = defineEmits<{ skip: []; replay: [] }>();
const total = computed(() => Number.isFinite(props.total) ? Math.max(1, Math.floor(props.total)) : 4);
const stage = computed(() => Number.isFinite(props.stage) ? Math.max(0, Math.min(total.value, Math.floor(props.stage))) : 0);
const complete = computed(() => stage.value >= total.value);
const currentLabel = computed(() => stage.value === 0
  ? '첫 항목을 펼칠 준비 중'
  : props.labels[stage.value - 1] || `${stage.value}번째 항목`);
const stageAnnouncement = computed(() => complete.value
  ? `저장된 분석 결과 ${total.value}개 항목을 모두 펼쳤습니다.`
  : `${stage.value} / ${total.value} · ${currentLabel.value}`);
const savedAt = computed(() => {
  if (!props.completedAt) return '';
  const value = new Date(props.completedAt);
  return Number.isNaN(value.getTime()) ? '' : value.toLocaleString('ko-KR', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
});
</script>

<template>
  <section class="report-reveal" aria-label="분석 결과 펼쳐보기" :data-active="active">
    <div class="report-reveal-copy">
      <div class="report-reveal-heading">
        <span class="report-reveal-mark" aria-hidden="true"><span></span><span></span><span></span></span>
        <strong>분석 결과 펼쳐보기</strong>
        <span v-if="active" class="report-reveal-cursor" aria-hidden="true"></span>
      </div>
      <p>{{ complete ? '저장된 분석 결과를 모두 펼쳤어요.' : '저장된 분석 결과를 순서대로 보여드려요.' }}</p>
      <p class="report-reveal-step" role="status" aria-live="polite" aria-atomic="true">{{ stageAnnouncement }}</p>
      <p v-if="savedAt" class="report-reveal-date">검사 완료 {{ savedAt }}</p>
    </div>
    <div class="report-reveal-controls">
      <div class="report-reveal-track" aria-hidden="true"><span :style="{ width: `${stage / total * 100}%` }"></span></div>
      <button v-if="!complete" type="button" @click="emit('skip')">전체 바로 보기</button>
      <button v-else type="button" @click="emit('replay')">다시 보기</button>
    </div>
  </section>
</template>

<style scoped>
.report-reveal{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:17px 20px;border:1px solid #dce4ff;border-radius:14px;background:linear-gradient(120deg,#f8faff,#eef2ff);color:#29345c;min-width:0}
.report-reveal-copy{min-width:0}.report-reveal-heading{display:flex;align-items:center;gap:8px;font-size:14px}.report-reveal p{margin:6px 0 0;font-size:13px;line-height:1.6;color:#5f6c92}.report-reveal .report-reveal-step{color:#465bc3;font-size:12px;min-height:19px}.report-reveal .report-reveal-date{font-size:11px;color:#7782a1}
.report-reveal-mark{display:inline-flex;flex-direction:column;gap:3px;width:14px}.report-reveal-mark span{height:2px;width:14px;background:#6575da;border-radius:2px}.report-reveal-mark span:nth-child(2){width:10px}.report-reveal-mark span:nth-child(3){width:12px}
.report-reveal-cursor{width:2px;height:14px;background:#6271d6;border-radius:1px;animation:report-cursor 1.1s ease-in-out infinite}.report-reveal-controls{display:flex;align-items:center;gap:14px;flex-shrink:0}.report-reveal-track{width:80px;height:4px;overflow:hidden;background:#dce3fb;border-radius:8px}.report-reveal-track span{display:block;height:100%;background:#6273e4;border-radius:inherit;transition:width .35s ease}.report-reveal[data-active="true"] .report-reveal-track{animation:report-track 1.4s ease-in-out infinite}
.report-reveal button{white-space:nowrap;border:1px solid #c9d3f7;border-radius:8px;padding:8px 11px;color:#4656aa;background:#fff;font-size:12px;font-weight:600;cursor:pointer}.report-reveal button:hover{background:#f3f5ff;border-color:#9caef1}.report-reveal button:focus-visible{outline:2px solid #4d65da;outline-offset:3px}
@keyframes report-cursor{0%,100%{opacity:.25}50%{opacity:1}}@keyframes report-track{0%,100%{opacity:.65}50%{opacity:1}}
@media(max-width:600px){.report-reveal{align-items:flex-start;flex-direction:column;gap:12px;padding:15px 16px}.report-reveal-controls{align-self:stretch;justify-content:space-between}.report-reveal-track{width:110px}}
@media(prefers-reduced-motion:reduce){.report-reveal-cursor,.report-reveal[data-active="true"] .report-reveal-track{animation:none}.report-reveal-track span{transition:none}}
</style>
