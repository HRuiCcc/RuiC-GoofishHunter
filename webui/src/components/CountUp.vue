<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    value: number | null | undefined
    decimals?: number
    duration?: number
  }>(),
  { decimals: 0, duration: 500 },
)

const reduced =
  typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false

const display = ref<number | null>(typeof props.value === 'number' ? 0 : null)
const formatter = computed(
  () =>
    new Intl.NumberFormat('zh-CN', {
      minimumFractionDigits: props.decimals,
      maximumFractionDigits: props.decimals,
    }),
)
let frame = 0

function animate(target: number | null): void {
  cancelAnimationFrame(frame)
  if (target === null) {
    display.value = null
    return
  }
  if (reduced) {
    display.value = target
    return
  }
  const from = typeof display.value === 'number' ? display.value : 0
  const started = performance.now()
  const step = (now: number) => {
    const progress = Math.min(1, (now - started) / props.duration)
    const eased = 1 - Math.pow(1 - progress, 3)
    display.value = from + (target - from) * eased
    if (progress < 1) frame = requestAnimationFrame(step)
    else display.value = target
  }
  frame = requestAnimationFrame(step)
}

watch(
  () => props.value,
  (next) => animate(typeof next === 'number' ? next : null),
  { immediate: true },
)

onBeforeUnmount(() => cancelAnimationFrame(frame))

const text = computed(() => (display.value === null ? '暂无' : formatter.value.format(display.value)))
</script>

<template>
  <span class="num">{{ text }}</span>
</template>
