<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';

const props = withDefaults(defineProps<{ text: string; animate?: boolean }>(), { animate: false });
const media = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  ? window.matchMedia('(prefers-reduced-motion: reduce)') : undefined;
const reducedMotion = ref(media?.matches ?? false);
const displayed = ref(props.text);
const typing = computed(() => props.animate && !reducedMotion.value && displayed.value !== props.text);
let timer: ReturnType<typeof setTimeout> | undefined;

function clearTimer() {
  if (timer !== undefined) clearTimeout(timer);
  timer = undefined;
}

watch(() => [props.text, props.animate] as const, ([text, animate]) => {
  clearTimer();
  if (!animate || reducedMotion.value || !text) {
    displayed.value = text;
    return;
  }
  const characters = Array.from(text);
  const chunk = Math.max(3, Math.ceil(characters.length / 24));
  let length = 0;
  displayed.value = '';
  function advance() {
    timer = undefined;
    length = Math.min(characters.length, length + chunk);
    displayed.value = characters.slice(0, length).join('');
    if (length < characters.length) timer = setTimeout(advance, 45);
  }
  timer = setTimeout(advance, 45);
}, { immediate: true });

function motionChanged(event: MediaQueryListEvent) {
  reducedMotion.value = event.matches;
  if (event.matches) {
    clearTimer();
    displayed.value = props.text;
  }
}
media?.addEventListener('change', motionChanged);
onBeforeUnmount(() => {
  clearTimer();
  media?.removeEventListener('change', motionChanged);
});
</script>

<template>
  <span class="report-text" :data-typing="typing">
    <span class="report-text-accessible">{{ text }}</span><span aria-hidden="true">{{ displayed }}<span v-if="typing" class="report-text-cursor"></span></span>
  </span>
</template>

<style scoped>
.report-text{white-space:pre-wrap;overflow-wrap:anywhere}.report-text-accessible{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.report-text-cursor{display:inline-block;width:2px;height:.95em;margin-left:2px;border-radius:1px;background:#6374d9;vertical-align:-.08em;animation:report-text-cursor 1s ease-in-out infinite}
@keyframes report-text-cursor{0%,100%{opacity:.2}50%{opacity:1}}
@media(prefers-reduced-motion:reduce){.report-text-cursor{animation:none;display:none}}
</style>
