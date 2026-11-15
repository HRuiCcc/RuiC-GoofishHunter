<script setup lang="ts">
import Icon from './Icon.vue'

withDefaults(
  defineProps<{
    kind?: 'empty' | 'error'
    title: string
    description?: string
  }>(),
  { kind: 'empty', description: '' },
)
</script>

<template>
  <div class="rounded-[14px] border border-line bg-surface p-5 shadow-card">
    <div class="flex items-start gap-3">
      <span
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] border border-line bg-raise"
        :class="kind === 'error' ? 'text-red' : 'text-ink-2'"
      >
        <Icon :name="kind === 'error' ? 'alert' : 'ledger'" :size="15" />
      </span>
      <div class="min-w-0">
        <p class="text-[14.5px] font-semibold leading-snug tracking-[-0.01em] text-ink">{{ title }}</p>
        <p v-if="description" class="mt-1.5 max-w-[62ch] text-[12.5px] leading-relaxed text-ink-2">
          {{ description }}
        </p>
        <div v-if="$slots.default" class="mt-4 flex flex-wrap items-center gap-2">
          <slot />
        </div>
      </div>
    </div>
  </div>
</template>
