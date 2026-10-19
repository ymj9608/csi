<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
// progress: 0이면 자물쇠가 열려 있고 1이면 걸쇠가 끝까지 내려옵니다.
// state가 locked가 되는 순간 "철컥" 하고 잠기며 체크 표시가 나타납니다.
const props = withDefaults(
  defineProps<{
    progress?: number;
    state?: "idle" | "scanning" | "locked" | "error" | "alert";
    compact?: boolean;
  }>(),
  { progress: 0, state: "idle", compact: false },
);
const root = ref<HTMLElement>();
const tilt = ref({ x: 0, y: 0 });
const clack = ref(0);
const shake = ref(0);
const uid = Math.random().toString(36).slice(2, 8);
const id = (name: string) => `${name}-${uid}`;
const url = (name: string) => `url(#${id(name)})`;
const lift = computed(() => {
  if (props.state === "locked" || props.state === "scanning") return 0;
  if (props.state === "error" || props.state === "alert") return 18;
  return 18 * (1 - Math.min(1, Math.max(0, props.progress)));
});
const label = computed(() =>
  props.state === "locked"
    ? "잠긴 자물쇠"
    : props.state === "scanning"
      ? "자물쇠를 잠그는 중"
      : props.state === "alert"
        ? "확인이 필요한 위험이 있어 열린 자물쇠"
        : "열린 자물쇠",
);
watch(
  () => props.state,
  (next, prev) => {
    if (next === "locked" && prev !== "locked") clack.value++;
    if (next === "error") shake.value++;
  },
);
let reduce = false;
function move(e: PointerEvent) {
  const r = root.value!.getBoundingClientRect();
  tilt.value = {
    x: ((e.clientX - r.left) / r.width - 0.5) * 2,
    y: ((e.clientY - r.top) / r.height - 0.5) * 2,
  };
}
function leave() {
  tilt.value = { x: 0, y: 0 };
}
onMounted(() => {
  reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!props.compact && !reduce) {
    window.addEventListener("pointermove", move);
    document.addEventListener("pointerleave", leave);
  }
  if (props.state === "locked") clack.value++;
});
onBeforeUnmount(() => {
  window.removeEventListener("pointermove", move);
  document.removeEventListener("pointerleave", leave);
});
</script>
<template>
  <div
    ref="root"
    class="shield-scene"
    :class="['is-' + state, { compact }]"
    :style="{
      '--tx': tilt.x.toFixed(3),
      '--ty': tilt.y.toFixed(3),
      '--lift': lift + 'px',
    }"
  >
    <svg viewBox="0 0 360 360" role="img" :aria-label="label">
      <defs>
        <linearGradient :id="id('face')" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#9DB3FF" />
          <stop offset=".55" stop-color="#5E7EF7" />
          <stop offset="1" stop-color="#3F5EE8" />
        </linearGradient>
        <linearGradient :id="id('side')" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#4B66E0" />
          <stop offset="1" stop-color="#2E44B8" />
        </linearGradient>
        <linearGradient :id="id('inner')" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#B9C9FF" stop-opacity=".55" />
          <stop offset="1" stop-color="#6A88F8" stop-opacity=".15" />
        </linearGradient>
        <linearGradient :id="id('ring')" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#C7D3FF" stop-opacity=".2" />
          <stop offset=".5" stop-color="#A9BBFF" />
          <stop offset="1" stop-color="#C7D3FF" stop-opacity=".2" />
        </linearGradient>
        <radialGradient :id="id('floor')">
          <stop offset="0" stop-color="#9DB0FF" stop-opacity=".45" />
          <stop offset="1" stop-color="#9DB0FF" stop-opacity="0" />
        </radialGradient>
        <linearGradient :id="id('sweep')" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#fff" stop-opacity="0" />
          <stop offset=".5" stop-color="#fff" stop-opacity=".75" />
          <stop offset="1" stop-color="#fff" stop-opacity="0" />
        </linearGradient>
        <linearGradient :id="id('tile')" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#7F99FA" />
          <stop offset="1" stop-color="#4463EA" />
        </linearGradient>
        <clipPath :id="id('clip')">
          <path
            d="M180 58C210 76 244 84 268 84V168C268 222 230 258 180 280C130 258 92 222 92 168V84C116 84 150 76 180 58Z"
          />
        </clipPath>
      </defs>

      <ellipse cx="180" cy="306" rx="150" ry="40" :fill="url('floor')" />
      <ellipse class="disk" cx="180" cy="306" rx="54" ry="14" />
      <ellipse class="disk-core" cx="180" cy="306" rx="18" ry="5" />
      <ellipse
        :key="'pulse' + clack"
        class="pulse"
        cx="180"
        cy="306"
        rx="54"
        ry="14"
      />

      <path
        v-if="!compact"
        class="ring"
        d="M24 196A156 50 0 0 1 336 196"
        :stroke="url('ring')"
      />

      <g class="parallax far" v-if="!compact">
        <g class="float f1">
          <rect x="34" y="108" width="50" height="40" rx="9" :fill="url('tile')" />
          <rect x="44" y="119" width="30" height="4" rx="2" fill="#fff" />
          <rect x="44" y="128" width="20" height="4" rx="2" fill="#fff" opacity=".7" />
          <rect x="44" y="137" width="25" height="4" rx="2" fill="#fff" opacity=".7" />
        </g>
        <g class="float f3">
          <rect x="54" y="232" width="38" height="38" rx="9" :fill="url('tile')" />
          <path d="M66 249v-4a7 7 0 0 1 14 0v4" fill="none" stroke="#fff" stroke-width="3" />
          <rect x="63" y="249" width="20" height="14" rx="3" fill="#fff" />
        </g>
      </g>

      <g class="body-group">
        <g :key="'shake' + shake" class="shield">
          <path
            transform="translate(12 8)"
            d="M180 58C210 76 244 84 268 84V168C268 222 230 258 180 280C130 258 92 222 92 168V84C116 84 150 76 180 58Z"
            :fill="url('side')"
          />
          <path
            d="M180 58C210 76 244 84 268 84V168C268 222 230 258 180 280C130 258 92 222 92 168V84C116 84 150 76 180 58Z"
            :fill="url('face')"
          />
          <path
            d="M180 78C205 93 233 100 252 100V168C252 212 220 242 180 261C140 242 108 212 108 168V100C127 100 155 93 180 78Z"
            :fill="url('inner')"
            stroke="#fff"
            stroke-opacity=".45"
            stroke-width="1.5"
          />
          <g :clip-path="url('clip')">
            <path
              d="M92 58H180V290H92Z"
              fill="#fff"
              opacity=".1"
            />
            <rect
              class="sweep"
              x="80"
              y="0"
              width="200"
              height="70"
              :fill="url('sweep')"
            />
          </g>

          <g class="lock">
            <path
              class="shackle"
              d="M158 176V142a22 22 0 0 1 44 0v18"
              fill="none"
              stroke="#F4F7FF"
              stroke-width="11"
              stroke-linecap="round"
            />
            <g :key="'clack' + clack" class="lock-body">
              <rect x="143" y="158" width="74" height="60" rx="13" fill="#2E44B8" opacity=".35" transform="translate(3 4)" />
              <rect x="143" y="158" width="74" height="60" rx="13" fill="#F7F9FF" />
              <rect x="143" y="158" width="74" height="12" rx="6" fill="#fff" />
              <g class="keyhole">
                <circle cx="180" cy="183" r="7.5" />
                <path d="M176 186h8l2.5 15h-13Z" />
              </g>
              <path
                class="check"
                d="M165 188l10 10 21-22"
                fill="none"
                stroke-width="7"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <g class="bang">
                <rect x="176.5" y="172" width="7" height="20" rx="3.5" />
                <circle cx="180" cy="202" r="4" />
              </g>
            </g>
          </g>
        </g>
      </g>

      <g class="parallax near" v-if="!compact">
        <g class="float f2">
          <rect x="232" y="30" width="40" height="40" rx="9" :fill="url('tile')" />
          <circle cx="252" cy="44" r="6" fill="#fff" />
          <path d="M241 62a11 9 0 0 1 22 0Z" fill="#fff" />
          <rect x="278" y="38" width="66" height="24" rx="12" fill="#fff" opacity=".85" />
          <g fill="#7F99FA">
            <circle cx="292" cy="50" r="3" /><circle cx="302" cy="50" r="3" />
            <circle cx="312" cy="50" r="3" /><circle cx="322" cy="50" r="3" />
            <circle cx="332" cy="50" r="3" />
          </g>
        </g>
        <g class="float f4">
          <rect x="290" y="140" width="42" height="42" rx="10" :fill="url('tile')" />
          <g fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round">
            <path d="M301 170c0-9 4-15 10-15s10 6 10 15" />
            <path d="M306 172c0-8 2-12 5-12s5 4 5 10" />
            <path d="M311 166v8" />
          </g>
        </g>
      </g>

      <path
        v-if="!compact"
        class="ring"
        d="M336 196A156 50 0 0 1 24 196"
        :stroke="url('ring')"
      />
    </svg>
  </div>
</template>
<style scoped>
.shield-scene {
  --blue: #3f5ee8;
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  perspective: 900px;
}
svg {
  width: 100%;
  height: 100%;
  overflow: visible;
  transform: rotateX(calc(var(--ty) * -7deg)) rotateY(calc(var(--tx) * 9deg));
  transition: transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.parallax {
  transition: transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.parallax.far {
  transform: translate(calc(var(--tx) * -6px), calc(var(--ty) * -4px));
}
.parallax.near {
  transform: translate(calc(var(--tx) * 10px), calc(var(--ty) * 6px));
}
.float {
  animation: float 6s ease-in-out infinite;
}
.f2 {
  animation-duration: 7s;
  animation-delay: -2s;
}
.f3 {
  animation-duration: 5.5s;
  animation-delay: -1s;
}
.f4 {
  animation-duration: 6.5s;
  animation-delay: -3s;
}
@keyframes float {
  50% {
    transform: translateY(-6px);
  }
}
.ring {
  fill: none;
  stroke-width: 9;
  stroke-linecap: round;
  stroke-dasharray: 90 40;
  animation: orbit 14s linear infinite;
}
@keyframes orbit {
  to {
    stroke-dashoffset: -520;
  }
}
.disk {
  fill: #c9d5fb;
}
.disk-core {
  fill: #fff;
  opacity: 0.8;
}
.pulse {
  fill: none;
  stroke: var(--blue);
  stroke-width: 2;
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
}
.is-locked .pulse {
  animation: pulse 0.9s 0.18s ease-out;
}
@keyframes pulse {
  from {
    opacity: 0.6;
    transform: scale(1);
  }
  to {
    opacity: 0;
    transform: scale(2.3);
  }
}

.shackle {
  transform: translateY(calc(var(--lift) * -1));
  transition: transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.is-scanning .shackle,
.is-locked .shackle {
  transition-duration: 0.22s;
  transition-timing-function: cubic-bezier(0.6, 0, 0.9, 0.5);
}
.lock-body {
  transform-box: fill-box;
  transform-origin: 50% 0;
}
.is-locked .lock-body {
  animation: clack 0.32s 0.18s ease-out;
}
@keyframes clack {
  40% {
    transform: translateY(3px) scaleY(0.96);
  }
}
.keyhole {
  fill: var(--blue);
  transition: opacity 0.2s;
}
.check {
  stroke: var(--blue);
  stroke-dasharray: 48;
  stroke-dashoffset: 48;
  transition: stroke-dashoffset 0.35s 0.25s ease-out;
}
.is-locked .keyhole,
.is-alert .keyhole {
  opacity: 0;
}
.is-locked .check {
  stroke-dashoffset: 0;
}
.bang {
  fill: #c05a12;
  opacity: 0;
}
.is-alert .bang {
  opacity: 1;
}
.is-alert .shackle {
  stroke: #ffe3cc;
}

.sweep {
  opacity: 0;
}
.is-scanning .sweep {
  opacity: 1;
  animation: sweep 1.1s ease-in-out infinite;
}
@keyframes sweep {
  from {
    transform: translateY(-20px);
  }
  to {
    transform: translateY(290px);
  }
}
.is-error .shield {
  animation: shake 0.42s ease-in-out;
}
@keyframes shake {
  20%,
  60% {
    transform: translateX(-7px);
  }
  40%,
  80% {
    transform: translateX(7px);
  }
}
.body-group {
  animation: hover 6s ease-in-out infinite;
}
@keyframes hover {
  50% {
    transform: translateY(-5px);
  }
}
.compact .body-group,
.compact .float {
  animation: none;
}
.compact svg {
  transform: none;
}
@media (prefers-reduced-motion: reduce) {
  *,
  svg {
    animation: none !important;
    transition: none !important;
  }
  .is-scanning .sweep {
    opacity: 0.5;
    transform: translateY(120px);
  }
}
</style>
