<script setup lang="ts">
withDefaults(defineProps<{ width?: string; height?: string }>(), { width: '100%', height: '0.75rem' })
</script>

<template>
  <span class="skel block" :style="{ width, height }" aria-hidden="true"></span>
</template>
