<script setup lang="ts">
import { computed } from 'vue'
import { fmtMoney, medianGeometry, relativeText } from '../lib/format'

const props = withDefaults(defineProps<{ price?: number | null; median?: number | null; showLabels?: boolean }>(), {
  showLabels: true,
})

const geometry = computed(() => medianGeometry(props.price, props.median))
const relative = computed(() => relativeText(props.price, props.median))
</script>

<template>
  <div>
    <div v-if="geometry" class="relative h-1 w-full rounded-full bg-[#ede8de]" aria-hidden="true">
      <div
        class="absolute inset-y-0 left-0 rounded-full bg-ink/20"
        :style="{ width: `${geometry.pricePct}%` }"
      ></div>
      <div
        v-if="geometry.below"
        class="absolute inset-y-0 rounded-full bg-jade"
        :style="{
          left: `${geometry.pricePct}%`,
          width: `${Math.max(0, geometry.medianPct - geometry.pricePct)}%`,
        }"
      ></div>
      <div
        v-else
        class="absolute inset-y-0 rounded-full bg-red"
        :style="{
          left: `${geometry.medianPct}%`,
          width: `${Math.max(0, geometry.pricePct - geometry.medianPct)}%`,
        }"
      ></div>
      <div
        class="absolute -top-[2px] h-[8px] w-px bg-ink/60"
        :style="{ left: `${geometry.medianPct}%` }"
      ></div>
    </div>

    <div v-if="showLabels" class="mt-1.5 flex items-baseline justify-between gap-2 text-[10px] leading-none">
      <span class="truncate text-muted">中位 {{ fmtMoney(median, '样本不足') }}</span>
      <span
        class="num shrink-0 font-medium"
        :class="geometry ? (geometry.below ? 'text-jade' : 'text-red') : 'text-muted'"
      >
        {{ relative }}
      </span>
    </div>
  </div>
</template>
