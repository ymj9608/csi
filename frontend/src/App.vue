<script setup lang="ts">
import { useSession } from "./stores/session";
const s = useSession();
</script>
<template>
  <RouterView />
  <div v-if="s.toast" class="toast" role="status">{{ s.toast }}</div>
</template>
