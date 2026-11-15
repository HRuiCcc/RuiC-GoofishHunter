<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ label: string; value: number; max: number; index?: number }>(), {
  index: 0,
})

const pct = computed(() => (props.max > 0 ? Math.min(100, (Math.abs(props.value) / props.max) * 100) : 0))
const positive = computed(() => props.value > 0)
const negative = computed(() => props.value < 0)
const toneClass = computed(() => (positive.value ? 'text-jade' : negative.value ? 'text-red' : 'text-muted'))
const barClass = computed(() => (positive.value ? 'bg-jade' : negative.value ? 'bg-red' : 'bg-[#c9c2b5]'))
</script>

<template>
  <div class="grid grid-cols-[46px_minmax(0,1fr)_56px] items-center gap-3">
    <span class="text-[11px] text-ink-2">{{ label }}</span>
    <div class="relative h-1 rounded-full bg-[#ede8de]">
      <div
        v-if="value !== 0"
        class="bar-grow absolute inset-y-0 left-0 rounded-full"
        :class="barClass"
        :style="{ width: `${Math.max(pct, 2)}%`, animationDelay: `${index * 40}ms` }"
      ></div>
    </div>
    <span class="num text-right text-[11px]" :class="toneClass">
      {{ value > 0 ? '+' : '' }}{{ value.toFixed(1) }}
    </span>
  </div>
</template>
