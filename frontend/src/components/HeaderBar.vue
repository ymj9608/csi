<script setup lang="ts">
import { Menu, ChevronRight } from "lucide-vue-next";
defineProps<{ heading: string; streamState: string }>();
const emit = defineEmits<{ toggle: [] }>();
</script>
<template>
  <header>
    <button
      class="icon-button mobile-toggle"
      aria-label="메뉴 열기"
      @click="emit('toggle')"
    >
      <Menu :size="20" />
    </button>
    <div class="breadcrumb">
      워크스페이스 <ChevronRight :size="13" /><strong>{{ heading }}</strong>
    </div>
    <span class="connection" :class="{ live: streamState === '실시간 연결' }"
      ><i />{{ streamState }}</span
    >
  </header>
</template>
