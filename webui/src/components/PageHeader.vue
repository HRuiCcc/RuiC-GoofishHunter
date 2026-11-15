<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <header class="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-line pb-4 pt-7 lg:pt-9">
    <div class="min-w-0">
      <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink lg:text-[30px]">
        {{ title }}
      </h1>
      <p v-if="subtitle" class="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>
