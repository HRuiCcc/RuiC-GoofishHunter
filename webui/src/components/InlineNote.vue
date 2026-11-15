<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = withDefaults(defineProps<{ tone?: 'error' | 'ok' | 'info' | 'muted' }>(), { tone: 'info' })

const icon = computed(() => ({ error: 'alert', ok: 'check', info: 'clock', muted: 'dot' })[props.tone])
const color = computed(
  () => ({ error: 'text-red', ok: 'text-jade', info: 'text-ink-2', muted: 'text-muted' })[props.tone],
)
</script>

<template>
  <p class="flex items-start gap-1.5 text-[11.5px] leading-relaxed" :class="color">
    <Icon :name="icon" :size="13" class="mt-[2px] shrink-0" />
    <span class="min-w-0"><slot /></span>
  </p>
</template>
