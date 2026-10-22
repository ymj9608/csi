import { computed, onBeforeUnmount, ref } from 'vue';

/** Reveal saved report sections without restarting on background data refreshes. */
export function useReportReveal(totalStages = 4) {
  const total = Number.isFinite(totalStages) ? Math.max(1, Math.floor(totalStages)) : 4;
  const visibleStage = ref(0);
  const started = ref(false);
  const media = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)') : undefined;
  const reducedMotion = ref(media?.matches ?? false);
  const active = computed(() => started.value && visibleStage.value < total);
  const interval = Math.min(620, 2600 / Math.max(1, total - 1));
  let currentKey: string | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;

  function clearTimer() {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
  }

  function advance() {
    timer = undefined;
    if (disposed || !started.value) return;
    visibleStage.value = Math.min(total, visibleStage.value + 1);
    if (visibleStage.value < total) timer = setTimeout(advance, interval);
  }

  function begin() {
    clearTimer();
    started.value = true;
    visibleStage.value = reducedMotion.value ? total : 0;
    if (!reducedMotion.value) timer = setTimeout(advance, 180);
  }

  function start(key: string) {
    if (disposed || currentKey === key) return;
    currentKey = key;
    begin();
  }

  function reset() {
    clearTimer();
    currentKey = undefined;
    started.value = false;
    visibleStage.value = 0;
  }

  function showAll() {
    clearTimer();
    visibleStage.value = total;
  }

  function replay() {
    if (!disposed && currentKey !== undefined) begin();
  }

  function motionChanged(event: MediaQueryListEvent) {
    reducedMotion.value = event.matches;
    if (event.matches && started.value) showAll();
  }

  media?.addEventListener('change', motionChanged);
  onBeforeUnmount(() => {
    disposed = true;
    clearTimer();
    media?.removeEventListener('change', motionChanged);
  });

  return { visibleStage, active, reducedMotion, start, reset, showAll, replay };
}
