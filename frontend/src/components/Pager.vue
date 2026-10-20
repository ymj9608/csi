<script setup lang="ts">
import { ChevronLeft, ChevronRight } from "lucide-vue-next";
// 목록 하단 중앙의 이전/다음 버튼입니다. 페이지가 적으면 점, 많으면 "현재 / 전체"로 표시합니다.
const props = defineProps<{ page: number; pages: number; total?: number; label?: string }>();
const emit = defineEmits<{ move: [step: number] }>();
const DOT_LIMIT = 6;
</script>
<template>
  <div class="pager">
    <button
      :disabled="props.page <= 1"
      :aria-label="'이전 ' + (props.label || '페이지')"
      @click="emit('move', -1)"
    >
      <ChevronLeft :size="16" />이전
    </button>
    <span v-if="props.pages <= DOT_LIMIT" class="pager-dots" aria-hidden="true"
      ><i v-for="n in props.pages" :key="n" :class="{ on: n === props.page }"
    /></span>
    <span v-else class="pager-count" aria-hidden="true"
      ><strong>{{ props.page }}</strong> / {{ props.pages }}</span
    >
    <span class="sr-only">{{ props.page }} / {{ props.pages }} 페이지</span>
    <button
      :disabled="props.page >= props.pages"
      :aria-label="'다음 ' + (props.label || '페이지')"
      @click="emit('move', 1)"
    >
      다음<ChevronRight :size="16" />
    </button>
    <small v-if="props.total !== undefined" class="pager-total">총 {{ props.total }}개</small>
  </div>
</template>
