<script setup lang="ts">
import { computed } from 'vue'
import { scoreTone, toneText, verdictFromScore } from '../lib/format'
import CountUp from './CountUp.vue'

const props = withDefaults(
  defineProps<{
    score?: number | null
    verdict?: string | null
    size?: 'sm' | 'md' | 'lg'
    stack?: boolean
  }>(),
  { score: null, verdict: null, size: 'md', stack: false },
)

const tone = computed(() => toneText(scoreTone(props.score)))
const label = computed(() => props.verdict || verdictFromScore(props.score))
const sizeClass = computed(
  () => ({ sm: 'text-[16px]', md: 'text-[20px]', lg: 'text-[36px]' })[props.size],
)
</script>

<template>
  <div :class="stack ? 'flex flex-col leading-none' : 'flex items-baseline gap-1.5'">
    <CountUp
      :value="score"
      :decimals="0"
      class="font-semibold leading-none tracking-[-0.02em]"
      :class="[tone, sizeClass]"
    />
    <span v-if="stack" class="mt-1 text-[10px] leading-none" :class="tone">{{ label }}</span>
    <span v-else class="text-[10.5px] leading-none" :class="tone">{{ label }}</span>
  </div>
</template>
