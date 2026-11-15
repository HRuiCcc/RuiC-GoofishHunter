<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    hint?: string
    help?: string
    error?: string | null
  }>(),
  { hint: '', help: '', error: null },
)
</script>

<template>
  <label class="block">
    <span class="mb-1.5 flex items-baseline justify-between gap-2">
      <span class="text-[11.5px] leading-none text-ink-2">{{ label }}</span>
      <span v-if="hint" class="text-[10px] leading-none text-muted">{{ hint }}</span>
    </span>
    <slot />
    <span v-if="error" class="mt-1 block text-[11px] leading-snug text-red">{{ error }}</span>
    <span v-else-if="help" class="mt-1 block text-[11px] leading-snug text-muted">{{ help }}</span>
  </label>
</template>
