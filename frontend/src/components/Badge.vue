<script setup lang="ts">
defineProps<{ value: string }>();
</script>
<template>
  <span class="badge" :class="value?.toLowerCase()"><i />{{ value }}</span>
</template>
