<script setup lang="ts">
import { computed } from 'vue'
import type { FeedbackValue, ItemRow } from '../api'
import {
  fmtMoney,
  labelsOf,
  relativeText,
  riskFlagsOf,
  tagsOf,
  verdictFromScore,
} from '../lib/format'
import Icon from './Icon.vue'
import MedianBar from './MedianBar.vue'
import ScoreMark from './ScoreMark.vue'
import Thumb from './Thumb.vue'

const props = defineProps<{ item: ItemRow }>()
const emit = defineEmits<{
  (event: 'open', item: ItemRow): void
  (event: 'mark', item: ItemRow, value: Exclude<FeedbackValue, ''>): void
}>()

const chips = computed(() => [
  ...labelsOf(props.item).map((label) => label.value),
  ...tagsOf(props.item),
])

const risks = computed(() => riskFlagsOf(props.item, 2))

function feedbackClass(value: string): string {
  if (props.item.feedback !== value) {
    return 'border-line text-ink-2 hover:border-[#d5cec1] hover:bg-paper-2 hover:text-ink'
  }
  if (value === 'good') return 'border-jade/60 bg-jade/10 text-jade'
  if (value === 'bad') return 'border-red/60 bg-red/10 text-red'
  return 'border-ink/40 bg-ink/10 text-ink'
}
</script>

<template>
  <article
    class="group relative flex cursor-pointer flex-col rounded-[14px] border border-line bg-surface p-4 shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-[#d5cec1] hover:shadow-lift"
    tabindex="0"
    role="button"
    :aria-label="`查看 ${item.title}`"
    @click="emit('open', item)"
    @keydown.enter.prevent="emit('open', item)"
    @keydown.space.prevent="emit('open', item)"
  >
    <div class="flex items-start gap-3">
      <Thumb
        :src="item.pics_json?.[0] ?? null"
        :alt="item.title"
        size-class="h-12 w-12 rounded-[10px]"
        :icon-size="14"
      />
      <div class="min-w-0 flex-1">
        <p class="line-clamp-2 text-[13px] font-medium leading-snug tracking-[-0.01em] text-ink">
          {{ item.title }}
        </p>
        <p class="mt-1 flex flex-wrap items-center gap-x-1.5 text-[10.5px] text-muted">
          <span>{{ item.area || '地区未知' }}</span>
          <span v-if="item.seller_nick">· {{ item.seller_nick }}</span>
          <span v-if="item.spec_key" class="num text-ink-2">· {{ item.spec_key }}</span>
        </p>
      </div>
      <ScoreMark
        :score="item.score"
        :verdict="item.verdict || verdictFromScore(item.score)"
        size="sm"
        stack
      />
    </div>

    <div class="mt-3 flex flex-wrap gap-1.5">
      <span v-for="chip in chips" :key="chip" class="rounded-full border border-line bg-raise px-2 py-0.5 text-[10px] text-ink-2">
        {{ chip }}
      </span>
      <span
        v-for="flag in risks"
        :key="flag"
        class="inline-flex items-center gap-1 rounded-full border border-red/40 bg-red/10 px-2 py-0.5 text-[10px] text-red"
      >
        <Icon name="alert" :size="9" />
        {{ flag }}
      </span>
    </div>

    <div class="mt-auto pt-4">
      <div class="flex items-end justify-between gap-2">
        <div class="min-w-0">
          <p class="num truncate text-[20px] font-semibold leading-none tracking-[-0.02em] text-ink">
            {{ fmtMoney(item.price) }}
          </p>
          <p class="mt-1 text-[10.5px] text-muted">{{ relativeText(item.price, item.market_median) }}</p>
        </div>
        <div class="shrink-0 text-right">
          <p class="text-[9.5px] text-muted">中位</p>
          <p class="num text-[11px] text-ink-2">{{ fmtMoney(item.market_median, '样本不足') }}</p>
        </div>
      </div>
      <MedianBar class="mt-2.5" :price="item.price" :median="item.market_median" :show-labels="false" />
    </div>

    <div class="mt-3 flex items-center justify-between gap-2 border-t border-line pt-2.5">
      <span class="num text-[10px] text-muted">{{ item.want_cnt ?? 0 }} 人想要</span>
      <div
        class="flex shrink-0 items-center gap-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100 max-md:opacity-100"
        @click.stop
      >
        <button
          v-for="option in [
            { value: 'good', label: '值得聊' },
            { value: 'bad', label: '不合适' },
            { value: 'deal', label: '已成交' },
          ]"
          :key="option.value"
          type="button"
          class="whitespace-nowrap rounded-full border px-2 py-1 text-[10px] leading-none transition-colors duration-150"
          :class="feedbackClass(option.value)"
          :aria-pressed="item.feedback === option.value"
          @click="emit('mark', item, option.value as Exclude<FeedbackValue, ''>)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>
  </article>
</template>
