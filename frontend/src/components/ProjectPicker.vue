<script setup lang="ts">
import { FolderGit2 } from "lucide-vue-next";
defineProps<{ projects: any[]; modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>
<template>
  <label class="project-picker">
    <FolderGit2 :size="15" />
    <span class="sr-only">프로젝트 선택</span>
    <select
      :value="modelValue"
      aria-label="프로젝트 선택"
      @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option value="">전체 프로젝트</option>
      <option v-for="p in projects" :key="p.id" :value="p.id">
        {{ p.repository }}
      </option>
    </select>
  </label>
</template>
