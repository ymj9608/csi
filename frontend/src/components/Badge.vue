<script setup lang="ts">
import { label } from "./labels";
defineProps<{ value: string; title?: string }>();
</script>
<template>
  <span class="badge" :class="value?.toLowerCase()" :title="title || value"
    ><i />{{ label(value) }}</span
  >
</template>
