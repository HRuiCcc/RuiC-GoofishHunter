<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  getItem,
  setFeedback,
  type FeedbackValue,
  type ItemDetailPayload,
  type ItemRow,
} from '../api'
import { useAsyncData } from '../lib/useAsync'
import { toast } from '../lib/toast'
import {
  flagTone,
  fmtMoney,
  fmtNumber,
  fmtRatio,
  fmtStamp,
  fmtYears,
  scoreTone,
  timeAgo,
  toneText,
  verdictChip,
} from '../lib/format'
import BreakdownRow from './BreakdownRow.vue'
import Drawer from './Drawer.vue'
import Icon from './Icon.vue'
import InlineNote from './InlineNote.vue'
import LineChart, { type ChartPoint } from './LineChart.vue'
import MedianBar from './MedianBar.vue'
import ScoreMark from './ScoreMark.vue'
import StateBlock from './StateBlock.vue'
import Thumb from './Thumb.vue'

const props = defineProps<{
  open: boolean
  itemId: string | null
  initial?: ItemRow | null
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'updated', payload: { itemId: string; feedback: FeedbackValue }): void
}>()

const {
  data: detailData,
  loading: detailLoading,
  error: detailError,
  reload: reloadDetail,
} = useAsyncData<ItemDetailPayload>(async () => {
  const id = props.itemId
  if (!id) throw new Error('缺少商品 id')
  return getItem(id)
}, { immediate: false })

watch(
  [() => props.open, () => props.itemId],
  ([open, id]) => {
    if (open && id) void reloadDetail()
  },
)

const item = computed<ItemRow | null>(() => detailData.value?.item ?? props.initial ?? null)
const bestScore = computed(() => detailData.value?.scores[0] ?? null)
const score = computed(() => bestScore.value?.score ?? props.initial?.score ?? null)
const verdict = computed(() => bestScore.value?.verdict ?? props.initial?.verdict ?? null)
const reasons = computed(() => bestScore.value?.reasons_json ?? props.initial?.reasons_json ?? [])
const flags = computed(() => bestScore.value?.flags_json ?? props.initial?.flags_json ?? [])
const breakdown = computed(() => bestScore.value?.breakdown_json ?? props.initial?.breakdown_json ?? {})
const llm = computed(() => bestScore.value?.llm ?? props.initial?.llm ?? null)
const median = computed(() => bestScore.value?.market_median ?? props.initial?.market_median ?? null)
const discount = computed(() => bestScore.value?.discount_pct ?? props.initial?.discount_pct ?? null)
const seller = computed(() => detailData.value?.seller ?? null)
const snapshots = computed(() => detailData.value?.snapshots ?? [])

const images = computed(() => (item.value?.pics_json ?? []).filter(Boolean))
const itemLink = computed(() =>
  item.value?.link || (item.value ? `https://www.goofish.com/item?id=${item.value.item_id}` : ''),
)

const breakdownOrder = ['价格', '成色', '卖家', '新鲜度', '竞争', '加分项', '风险', '匹配']
const breakdownRows = computed(() =>
  breakdownOrder.flatMap((key) => {
    const value = breakdown.value[key]
    return typeof value === 'number' ? [{ label: key, value }] : []
  }),
)
const maxBreakdown = computed(() => Math.max(1, ...breakdownRows.value.map((row) => Math.abs(row.value))))

const snapshotPoints = computed<ChartPoint[]>(() =>
  [...snapshots.value]
    .reverse()
    .map((snap) => ({ label: fmtStamp(snap.seen_at).slice(6), value: snap.price, volume: snap.want_cnt })),
)

const aiVerdict = computed(() => verdictChip(llm.value?.verdict))
const discountLabel = computed(() => {
  const value = discount.value
  if (value === null || value === undefined) return ''
  return value >= 0 ? `低于中位 ${value.toFixed(1)}%` : `高于中位 ${Math.abs(value).toFixed(1)}%`
})
const chipTone: Record<string, string> = {
  jade: 'border-jade/50 text-jade',
  ochre: 'border-ochre/50 text-ochre',
  red: 'border-red/50 text-red',
  muted: 'border-line text-muted',
}

const feedback = ref<FeedbackValue>('')
const saving = ref(false)
const copied = ref(false)
const linkCopied = ref(false)

watch(
  item,
  (value) => {
    feedback.value = (value?.feedback ?? '') as FeedbackValue
  },
  { immediate: true },
)

async function mark(value: Exclude<FeedbackValue, ''>): Promise<void> {
  const current = item.value
  if (!current || saving.value) return
  const next: FeedbackValue = feedback.value === value ? '' : value
  const previous = feedback.value
  feedback.value = next
  saving.value = true
  try {
    await setFeedback(current.item_id, next)
    emit('updated', { itemId: current.item_id, feedback: next })
    toast.success(
      next === '' ? '已取消标记' : `已标记为${next === 'good' ? '值得聊' : next === 'bad' ? '不合适' : '已成交'}`,
    )
  } catch (problem) {
    feedback.value = previous
    toast.error(problem instanceof Error ? problem.message : '标记没保存上，再试一次。')
  } finally {
    saving.value = false
  }
}

async function copyAsk(text: string | undefined): Promise<void> {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    toast.success('已复制问卖家的话')
    window.setTimeout(() => {
      copied.value = false
    }, 1500)
  } catch {
    toast.error('复制失败，浏览器不允许访问剪贴板')
    copied.value = false
  }
}

async function copyLink(): Promise<void> {
  if (!itemLink.value) return
  try {
    await navigator.clipboard.writeText(itemLink.value)
    linkCopied.value = true
    toast.success('链接已复制')
    window.setTimeout(() => {
      linkCopied.value = false
    }, 1500)
  } catch {
    toast.error('复制失败，浏览器不允许访问剪贴板')
  }
}

const feedbackOptions: Array<{ value: Exclude<FeedbackValue, ''>; label: string }> = [
  { value: 'good', label: '值得聊' },
  { value: 'bad', label: '不合适' },
  { value: 'deal', label: '已成交' },
]

function feedbackClass(value: Exclude<FeedbackValue, ''>): string {
  if (feedback.value !== value) return ''
  if (value === 'good') return 'border-jade bg-jade/10 text-jade'
  if (value === 'bad') return 'border-red bg-red/10 text-red'
  return 'border-ink bg-ink/5 text-ink'
}
</script>

<template>
  <Drawer
    :open="open"
    title="商品详情"
    :subtitle="itemId ?? undefined"
    @close="emit('close')"
  >
    <div v-if="detailError && !item" class="px-6 py-6">
      <StateBlock
        kind="error"
        title="详情没读出来"
        :description="detailError"
      >
        <button type="button" class="btn btn-ghost" @click="reloadDetail()">
          <Icon name="refresh" :size="13" /> 重试
        </button>
      </StateBlock>
    </div>

    <div v-else-if="!item" class="space-y-4 px-6 py-6">
      <div class="skel h-[86px] w-full"></div>
      <div class="skel h-4 w-4/5"></div>
      <div class="skel h-4 w-2/5"></div>
      <div class="skel h-24 w-full"></div>
      <div class="skel h-32 w-full"></div>
    </div>

    <template v-else>
      <div v-if="detailError" class="border-b border-line px-6 py-3">
        <InlineNote tone="error">
          详情只读到缓存，部分内容可能不全：{{ detailError }}
          <button type="button" class="ml-1 underline underline-offset-2" @click="reloadDetail()">重试</button>
        </InlineNote>
      </div>

      <section class="border-b border-line px-6 py-5">
        <div v-if="images.length" class="flex gap-2 overflow-x-auto pb-1">
          <a
            v-for="(pic, index) in images.slice(0, 8)"
            :key="`${pic}-${index}`"
            :href="pic"
            target="_blank"
            rel="noreferrer"
            class="shrink-0"
            :title="`查看第 ${index + 1} 张原图`"
          >
            <Thumb :src="pic" :alt="`商品图 ${index + 1}`" size-class="h-[86px] w-[86px]" :icon-size="18" />
          </a>
        </div>
        <p v-else class="text-[12px] text-ink-2">这条没有抓到图片，去原页面看实拍更稳。</p>
      </section>

      <section class="border-b border-line px-6 py-5">
        <h3 class="text-[18px] font-semibold leading-snug tracking-[-0.02em] text-ink">{{ item.title }}</h3>
        <p class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-ink-2">
          <span v-if="item.area">{{ item.area }}</span>
          <span v-if="item.seller_nick" class="text-muted">卖家 {{ item.seller_nick }}</span>
          <span class="text-muted">{{ item.publish_at ? `${timeAgo(item.publish_at)}发布` : '发布时间未知' }}</span>
        </p>

        <div class="mt-3 flex flex-wrap items-end gap-x-2.5 gap-y-1.5">
          <span class="num text-[34px] font-semibold leading-none tracking-[-0.03em] text-ink">
            {{ fmtMoney(item.price, '未标价') }}
          </span>
          <span v-if="item.original_price" class="num text-[12px] leading-none text-muted line-through">
            原价 {{ fmtMoney(item.original_price) }}
          </span>
          <span
            v-if="discountLabel"
            class="rounded-full border px-2 py-[3px] text-[10.5px] leading-none"
            :class="(discount ?? 0) >= 0 ? 'border-jade/50 text-jade' : 'border-red/50 text-red'"
          >
            {{ discountLabel }}
          </span>
        </div>

        <div class="mt-3 max-w-[320px]">
          <MedianBar :price="item.price" :median="median" />
        </div>

        <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-2">
          <span>想要 {{ fmtNumber(item.want_cnt, '未知') }}</span>
          <span>状态 {{ item.status || '未知' }}</span>
          <span v-if="item.transport_fee === 0">包邮</span>
          <span v-else-if="item.transport_fee">运费 {{ fmtMoney(item.transport_fee) }}</span>
        </div>
      </section>

      <section class="border-b border-line px-6 py-5">
        <div class="flex items-baseline justify-between gap-4">
          <h3 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">价格轨迹</h3>
          <span class="num text-[10px] text-muted">共 {{ snapshots.length }} 次记录</span>
        </div>
        <div v-if="snapshotPoints.length >= 2" class="mt-3">
          <LineChart :points="snapshotPoints" :height="104" aria-label="这条商品的价格轨迹" />
        </div>
        <p v-else class="mt-2 text-[12px] leading-relaxed text-ink-2">
          还没记到第二次价格。同一条商品被扫到两轮后，这里会画出它降没降价。
        </p>
      </section>

      <section class="border-b border-line px-6 py-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">评分构成</h3>
            <p class="mt-1 text-[11px] text-ink-2">规则分：低于市场价 + 成色 + 卖家可信度 - 风险</p>
          </div>
          <ScoreMark :score="score" :verdict="verdict" size="lg" stack />
        </div>

        <div v-if="breakdownRows.length && typeof score === 'number'" class="mt-4 space-y-1.5">
          <BreakdownRow
            v-for="(row, index) in breakdownRows"
            :key="row.label"
            :label="row.label"
            :value="row.value"
            :max="maxBreakdown"
            :index="index"
          />
          <div class="mt-2 flex items-center justify-between border-t border-line pt-2 text-[11px]">
            <span class="text-ink-2">
              规则总分 <span class="text-[9.5px] text-muted">含基础分，逐项相加后取整</span>
            </span>
            <span class="num text-ink">{{ score }} 分</span>
          </div>
        </div>
        <p v-else class="mt-3 text-[12px] text-ink-2">这条还没评分，等下一轮扫描。</p>

        <div v-if="reasons.length" class="mt-5">
          <h4 class="text-[11.5px] text-ink-2">理由</h4>
          <ol class="mt-2 border-t border-line">
            <li
              v-for="(reason, index) in reasons"
              :key="index"
              class="flex gap-3 border-b border-line/70 py-2 text-[12px] leading-relaxed text-ink"
            >
              <span class="num mt-[1px] shrink-0 text-[10px] text-grey">
                {{ String(index + 1).padStart(2, '0') }}
              </span>
              <span>{{ reason }}</span>
            </li>
          </ol>
        </div>

        <div v-if="flags.length" class="mt-4 flex flex-wrap gap-1.5">
          <span
            v-for="flag in flags"
            :key="flag"
            class="rounded-full border border-line px-2 py-[2px] text-[10px]"
            :class="{
              'text-red': flagTone(flag) === 'red',
              'text-jade': flagTone(flag) === 'jade',
              'text-ink-2': flagTone(flag) === 'muted',
            }"
          >
            {{ flag }}
          </span>
        </div>
      </section>

      <section class="border-b border-line px-6 py-5">
        <div class="flex items-center justify-between gap-4">
          <h3 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">AI 复核</h3>
          <div class="flex items-center gap-2">
            <span v-if="llm?.model" class="num text-[10px] text-muted">{{ llm?.model }}</span>
            <span
              v-if="llm && !llm.error"
              class="rounded-full border px-2 py-[2px] text-[10px] leading-none"
              :class="chipTone[aiVerdict.tone]"
            >
              {{ aiVerdict.label }}
            </span>
          </div>
        </div>

        <template v-if="llm && !llm.error">
          <p v-if="llm?.summary" class="mt-2.5 text-[12.5px] leading-relaxed text-ink">{{ llm?.summary }}</p>
          <p v-if="llm?.condition" class="mt-1 text-[11.5px] leading-relaxed text-ink-2">
            成色判断：{{ llm?.condition }}
          </p>

          <div v-if="llm?.ask_seller" class="mt-3 border-l-2 border-red bg-paper-2/60 px-3 py-2.5">
            <div class="flex items-start justify-between gap-2">
              <p class="text-[10.5px] tracking-[0.08em] text-muted">该问卖家什么</p>
              <button
                type="button"
                class="btn btn-quiet btn-sm -mr-1 -mt-1 px-1.5"
                @click="copyAsk(llm?.ask_seller)"
              >
                <Icon name="copy" :size="12" />
                {{ copied ? '已复制' : '复制' }}
              </button>
            </div>
            <p class="mt-1 text-[12.5px] leading-relaxed text-ink">{{ llm?.ask_seller }}</p>
          </div>

          <div v-if="llm?.missing_info?.length" class="mt-4">
            <h4 class="text-[11px] text-ink-2">还缺的信息</h4>
            <ul class="mt-1.5 space-y-1">
              <li
                v-for="(entry, index) in llm?.missing_info ?? []"
                :key="index"
                class="flex gap-2 text-[11.5px] leading-relaxed text-ink"
              >
                <span class="mt-[7px] h-px w-2 shrink-0 bg-grey" aria-hidden="true"></span>
                <span>{{ entry }}</span>
              </li>
            </ul>
          </div>

          <div v-if="llm?.risks?.length" class="mt-4">
            <h4 class="text-[11px] text-ink-2">可能的风险</h4>
            <ul class="mt-1.5 space-y-1">
              <li
                v-for="(entry, index) in llm?.risks ?? []"
                :key="index"
                class="flex gap-2 text-[11.5px] leading-relaxed text-ink"
              >
                <Icon name="alert" :size="11" class="mt-[3px] shrink-0 text-red" />
                <span>{{ entry }}</span>
              </li>
            </ul>
          </div>

          <p v-if="llm?.confidence" class="mt-4 text-[10.5px] text-muted">
            模型置信度 <span class="num">{{ Math.round((llm?.confidence ?? 0) * 100) }}%</span>
          </p>
        </template>

        <p v-else-if="llm?.error" class="mt-2.5 text-[12px] leading-relaxed text-red">
          AI 这次没跑通：{{ llm?.error }}
        </p>

        <p v-else class="mt-2.5 text-[12px] leading-relaxed text-ink-2">
          这条还没过 AI 复核。打开设置里的 AI 开关、并在关注里勾选「AI 复核」，下一轮就会补上。
        </p>
      </section>

      <section class="border-b border-line px-6 py-5">
        <h3 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">卖家</h3>
        <template v-if="seller">
          <div class="mt-1.5 flex items-baseline gap-2">
            <span class="text-[13px] text-ink">{{ seller.nick || item.seller_nick || '匿名卖家' }}</span>
            <span class="text-[11px] text-muted">{{ seller.city || '' }}</span>
          </div>
          <dl class="mt-3 grid grid-cols-2 gap-x-5 gap-y-2 text-[11.5px]">
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">信用</dt>
              <dd class="text-ink">{{ seller.credit_text || '暂无' }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">芝麻</dt>
              <dd class="text-ink">{{ seller.zhima ? '已认证' : '未认证' }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">注册</dt>
              <dd class="num text-ink">{{ fmtYears(seller.reg_days) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">在售</dt>
              <dd class="num text-ink">{{ fmtNumber(seller.item_count) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">已售</dt>
              <dd class="num text-ink">{{ fmtNumber(seller.sold_count) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">24h 回复率</dt>
              <dd class="num text-ink">{{ fmtRatio(seller.reply_ratio) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">好评率</dt>
              <dd class="num text-ink">{{ fmtRatio(seller.good_ratio) }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
              <dt class="text-muted">评价</dt>
              <dd class="num text-ink">{{ fmtNumber(seller.rate_total) }} 条</dd>
            </div>
          </dl>
          <div v-if="seller.tags?.length" class="mt-3 flex flex-wrap gap-1.5">
            <span
              v-for="tag in seller.tags"
              :key="tag"
              class="rounded-full border border-line px-2 py-[2px] text-[10px] text-ink-2"
            >
              {{ tag }}
            </span>
          </div>
        </template>
        <template v-else>
          <div class="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span class="text-[13px] text-ink">{{ item.seller_nick || '匿名卖家' }}</span>
          </div>
          <p class="mt-2 text-[12px] leading-relaxed text-ink-2">
            缓存里还没有卖家画像（信用 / 注册年限 / 回复率）。等下一轮详情抓取，或先点「打开闲鱼」看原页面。
          </p>
        </template>
      </section>

    </template>

    <template v-if="item" #footer>
      <div class="flex flex-wrap items-center gap-2">
        <a :href="itemLink" target="_blank" rel="noreferrer" class="btn btn-primary">
          打开闲鱼
          <Icon name="external" :size="13" />
        </a>
        <button type="button" class="btn btn-ghost h-9 px-3 text-[11.5px]" @click="copyLink">
          <Icon :name="linkCopied ? 'check' : 'link'" :size="13" />
          {{ linkCopied ? '已复制' : '复制链接' }}
        </button>
        <span class="mx-0.5 h-4 w-px bg-line" aria-hidden="true"></span>
        <button
          v-for="option in feedbackOptions"
          :key="`f-${option.value}`"
          type="button"
          class="btn btn-ghost h-8 rounded-full px-2.5 text-[11.5px]"
          :class="feedbackClass(option.value)"
          :disabled="saving"
          @click="mark(option.value)"
        >
          {{ option.label }}
        </button>
        <span v-if="score !== null" class="num ml-auto text-[10.5px]" :class="toneText(scoreTone(score))">
          {{ score }} 分
        </span>
      </div>
    </template>
  </Drawer>
</template>
