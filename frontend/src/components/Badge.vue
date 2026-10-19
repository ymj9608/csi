<script setup lang="ts">
import { label } from "./labels";
defineProps<{ value: string }>();
</script>
<template>
  <span class="badge" :class="value?.toLowerCase()" :title="value"
    ><i />{{ label(value) }}</span
  >
</template>
