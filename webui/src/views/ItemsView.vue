<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getItems,
  getWatches,
  setFeedback,
  type FeedbackValue,
  type ItemRow,
  type ItemsQuery,
  type Watch,
} from '../api'
import { useAsyncData, errorMessage } from '../lib/useAsync'
import { fmtMoney, fmtNumber, labelsOf, riskFlagsOf, tagsOf } from '../lib/format'
import { toast } from '../lib/toast'
import Icon from '../components/Icon.vue'
import ItemCard from '../components/ItemCard.vue'
import ItemDrawer from '../components/ItemDrawer.vue'
import MedianBar from '../components/MedianBar.vue'
import PageHeader from '../components/PageHeader.vue'
import ScoreMark from '../components/ScoreMark.vue'
import Segmented from '../components/Segmented.vue'
import SelectField from '../components/SelectField.vue'
import Skeleton from '../components/Skeleton.vue'
import StateBlock from '../components/StateBlock.vue'
import Thumb from '../components/Thumb.vue'

const route = useRoute()
const router = useRouter()
const { data: watchList } = useAsyncData<Watch[]>(() => getWatches())

const initialWatch = Number(route.query.watch)
const filters = reactive({
  watch: Number.isFinite(initialWatch) && initialWatch > 0 ? String(initialWatch) : '',
  minScore: '0',
  order: 'score',
  feedback: '',
  search: '',
})

const searchInput = ref('')
const searchRef = ref<HTMLInputElement | null>(null)
const items = ref<ItemRow[]>([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref<string | null>(null)
const lastBatch = ref(0)
const offset = ref(0)
const LIMIT = 40

const view = ref<'table' | 'cards'>(
  typeof localStorage !== 'undefined' && localStorage.getItem('hunter:items-view') === 'cards'
    ? 'cards'
    : 'table',
)
const activeItem = ref<ItemRow | null>(null)
const drawerOpen = computed(() => activeItem.value !== null)

let latest = 0
let searchTimer = 0

const watchOptions = computed(() => [
  { value: '', label: '全部关注' },
  ...(watchList.value ?? []).map((watch) => ({ value: String(watch.id), label: watch.name })),
])

const minScoreOptions = [
  { value: '0', label: '不限最低分' },
  { value: '50', label: '50 分以上' },
  { value: '65', label: '65 分以上' },
  { value: '80', label: '80 分以上' },
]

const orderOptions = [
  { value: 'score', label: '分数优先' },
  { value: 'discount', label: '折扣优先' },
  { value: 'new', label: '最新发现' },
  { value: 'price', label: '价格从低到高' },
]

const feedbackOptions: Array<{ value: string; label: string }> = [
  { value: '', label: '全部' },
  { value: 'good', label: '值得聊' },
  { value: 'bad', label: '不合适' },
  { value: 'deal', label: '已成交' },
]

const viewOptions = [
  { value: 'table', label: '表格', icon: 'rows' },
  { value: 'cards', label: '卡片', icon: 'grid' },
]

const hasFilters = computed(
  () =>
    filters.watch !== '' ||
    filters.minScore !== '0' ||
    filters.search !== '' ||
    filters.feedback !== '',
)

const hasMore = computed(() => lastBatch.value === LIMIT && items.value.length < total.value)

async function load(reset = true): Promise<void> {
  const request = ++latest
  if (reset) {
    loading.value = true
    offset.value = 0
  } else {
    loadingMore.value = true
  }
  error.value = null
  try {
    const result = await getItems({
      watch_id: filters.watch ? Number(filters.watch) : null,
      min_score: Number(filters.minScore) || 0,
      search: filters.search,
      limit: LIMIT,
      offset: reset ? 0 : offset.value,
      order: filters.order as ItemsQuery['order'],
      feedback: filters.feedback,
    })
    if (request !== latest) return
    total.value = result.total
    lastBatch.value = result.items.length
    if (reset) {
      items.value = result.items
      offset.value = result.items.length
    } else {
      items.value = [...items.value, ...result.items]
      offset.value += result.items.length
    }
  } catch (problem) {
    if (request === latest) error.value = errorMessage(problem)
  } finally {
    if (request === latest) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

watch(
  () => [filters.watch, filters.minScore, filters.order, filters.feedback, filters.search] as const,
  () => void load(true),
  { immediate: true },
)

watch(searchInput, (value) => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    filters.search = value.trim()
  }, 320)
})

watch(view, (value) => {
  localStorage.setItem('hunter:items-view', value)
})

function setView(value: string): void {
  view.value = value === 'cards' ? 'cards' : 'table'
}

function resetFilters(): void {
  window.clearTimeout(searchTimer)
  searchInput.value = ''
  filters.watch = ''
  filters.minScore = '0'
  filters.order = 'score'
  filters.feedback = ''
  filters.search = ''
}

function openItem(row: ItemRow): void {
  activeItem.value = row
}

function closeItem(): void {
  activeItem.value = null
}

async function mark(row: ItemRow, value: Exclude<FeedbackValue, ''>): Promise<void> {
  const next: FeedbackValue = row.feedback === value ? '' : value
  const previous = row.feedback ?? ''
  row.feedback = next
  try {
    await setFeedback(row.item_id, next)
    toast.success(
      next === '' ? '已取消标记' : `已标记为${next === 'good' ? '值得聊' : next === 'bad' ? '不合适' : '已成交'}`,
    )
    if (filters.feedback && filters.feedback !== next) void load(true)
  } catch (problem) {
    row.feedback = previous
    toast.error(problem instanceof Error ? problem.message : '标记没保存上，再试一次。')
  }
}

function onFeedback(payload: { itemId: string; feedback: FeedbackValue }): void {
  const row = items.value.find((entry) => entry.item_id === payload.itemId)
  if (row) row.feedback = payload.feedback
  if (filters.feedback && filters.feedback !== payload.feedback) void load(true)
}

function feedbackClass(value: FeedbackValue): string {
  if (value === 'good') return 'border-jade/60 bg-jade/10 text-jade'
  if (value === 'bad') return 'border-red/60 bg-red/10 text-red'
  if (value === 'deal') return 'border-ink/40 bg-ink/10 text-ink'
  return ''
}

function onKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    searchRef.value?.focus()
    searchRef.value?.select()
    return
  }
  if (event.key === 'Escape' && document.activeElement === searchRef.value) {
    event.preventDefault()
    if (searchInput.value) {
      searchInput.value = ''
      filters.search = ''
    } else {
      searchRef.value?.blur()
    }
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div>
    <PageHeader title="商品库" subtitle="所有扫到的商品都在这里；点一行看评分构成、AI 判断和卖家底细。">
      <template #actions>
        <button type="button" class="btn btn-ghost" @click="load(true)">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
        <button type="button" class="btn btn-primary" @click="router.push('/watches?new=1')">
          <Icon name="plus" :size="13" /> 新建关注
        </button>
      </template>
    </PageHeader>

    <div class="surface-card mt-4 p-3">
      <div class="flex flex-wrap items-center gap-2">
        <div class="w-[140px]">
          <SelectField v-model="filters.watch" :options="watchOptions" small aria-label="按关注筛选" />
        </div>
        <div class="w-[128px]">
          <SelectField v-model="filters.minScore" :options="minScoreOptions" small aria-label="最低分" />
        </div>
        <div class="w-[128px]">
          <SelectField v-model="filters.order" :options="orderOptions" small aria-label="排序" />
        </div>

        <div class="flex items-center rounded-full border border-line bg-paper-2 p-1">
          <button
            v-for="option in feedbackOptions"
            :key="option.value"
            type="button"
            class="h-7 rounded-full px-2.5 text-[11px] leading-none transition-colors duration-150"
            :class="
              filters.feedback === option.value
                ? 'bg-ink text-paper'
                : 'text-muted hover:text-ink-2'
            "
            :aria-pressed="filters.feedback === option.value"
            @click="filters.feedback = option.value"
          >
            {{ option.label }}
          </button>
        </div>

        <label class="relative min-w-[200px] flex-1">
          <Icon
            name="search"
            :size="14"
            class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
          />
          <input
            ref="searchRef"
            v-model="searchInput"
            class="field h-9 pl-9 pr-[64px]"
            type="search"
            placeholder="搜标题或描述"
            aria-label="搜索商品"
          />
          <kbd
            class="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 rounded-[6px] border border-line bg-raise px-1.5 py-0.5 text-[9.5px] text-muted sm:block"
          >
            ⌘K
          </kbd>
        </label>

        <button v-if="hasFilters" type="button" class="btn btn-quiet btn-sm h-8" @click="resetFilters">
          清空筛选
        </button>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <p class="text-[11.5px] text-ink-2">
        库内共 <span class="num font-medium text-ink">{{ fmtNumber(total) }}</span> 条
        <template v-if="items.length">，已显示 <span class="num text-ink">{{ items.length }}</span> 条</template>
        <span v-if="hasFilters" class="text-muted"> · 已套用筛选</span>
      </p>
      <div class="hidden md:block">
        <Segmented
          :model-value="view"
          :options="viewOptions"
          aria-label="切换表格或卡片视图"
          @update:model-value="setView"
        />
      </div>
    </div>

    <div v-if="loading && items.length === 0" class="surface-card mt-3 p-4">
      <div v-for="index in 6" :key="index" class="flex items-center gap-4 border-b border-line/70 py-3.5 last:border-b-0">
        <Skeleton width="3rem" height="3rem" />
        <div class="flex-1 space-y-1.5">
          <Skeleton width="55%" height="0.8rem" />
          <Skeleton width="30%" height="0.65rem" />
        </div>
        <Skeleton width="5rem" height="0.8rem" />
        <Skeleton width="2.5rem" height="1.1rem" />
        <Skeleton width="6rem" height="0.7rem" />
      </div>
    </div>

    <StateBlock v-else-if="error && items.length === 0" kind="error" title="商品库没读出来" :description="error" class="mt-3">
      <button type="button" class="btn btn-ghost" @click="load(true)">重试</button>
    </StateBlock>

    <StateBlock
      v-else-if="items.length === 0 && hasFilters"
      title="没有符合条件的商品"
      description="把最低分降到 50，或者清掉搜索词和标记筛选；也可能是这一轮还没跑到过线的货。"
      class="mt-3"
    >
      <button type="button" class="btn btn-ghost" @click="resetFilters">清空筛选</button>
      <button type="button" class="btn btn-quiet" @click="router.push('/runs')">看看运行日志</button>
    </StateBlock>

    <StateBlock
      v-else-if="items.length === 0"
      title="商品库还是空的"
      description="去「关注」建一个关键词，点「立即运行」跑一轮；扫到的商品会按分数排在这里。"
      class="mt-3"
    >
      <button type="button" class="btn btn-primary" @click="router.push('/watches?new=1')">
        <Icon name="plus" :size="13" /> 建第一个关注
      </button>
    </StateBlock>

    <template v-else>
      <div v-if="view === 'table'" class="surface-card mt-3 hidden overflow-hidden md:block">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[1000px] table-fixed border-collapse">
            <colgroup>
              <col style="width: 68px" />
              <col />
              <col style="width: 160px" />
              <col style="width: 80px" />
              <col style="width: 132px" />
              <col style="width: 184px" />
            </colgroup>
            <thead>
              <tr class="border-b border-line text-left">
                <th class="px-4 py-2.5"><span class="label-xs">图</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">商品 / 标签</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">价格 / 相对中位价</span></th>
                <th class="px-1 py-2.5 text-center"><span class="label-xs">分数</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">风险旗标</span></th>
                <th class="px-4 py-2.5 text-right"><span class="label-xs">反馈</span></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in items"
                :key="row.item_id"
                class="group cursor-pointer border-b border-line/70 transition-[background-color,box-shadow] duration-150 last:border-b-0 hover:bg-paper-2 hover:shadow-[inset_2px_0_0_#D8432A]"
                tabindex="0"
                :aria-label="`查看 ${row.title}`"
                @click="openItem(row)"
                @keydown.enter.prevent="openItem(row)"
                @keydown.space.prevent="openItem(row)"
              >
                <td class="px-4 py-3 align-middle">
                  <Thumb
                    :src="row.pics_json?.[0] ?? null"
                    :alt="row.title"
                    size-class="h-14 w-14"
                    :icon-size="15"
                  />
                </td>

                <td class="px-3 py-3 align-middle">
                  <p class="line-clamp-2 text-[13px] font-medium leading-snug tracking-[-0.01em] text-ink">
                    {{ row.title }}
                  </p>
                  <div class="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] text-muted">
                    <span
                      v-if="row.spec_key"
                      class="num rounded-full border border-line bg-raise px-1.5 py-0.5 leading-none text-ink-2"
                    >
                      {{ row.spec_key }}
                    </span>
                    <span
                      v-for="label in labelsOf(row)"
                      :key="`${label.label}-${label.value}`"
                      class="rounded-full border border-line bg-raise px-1.5 py-0.5 leading-none text-ink-2"
                    >
                      {{ label.value }}
                    </span>
                    <span v-for="tag in tagsOf(row)" :key="tag" class="text-jade">{{ tag }}</span>
                    <span class="truncate">{{ row.area || '地区未知' }}</span>
                  </div>
                </td>

                <td class="px-3 py-3 align-middle">
                  <div class="flex items-baseline gap-1.5">
                    <span class="num text-[14px] leading-none text-ink">{{ fmtMoney(row.price) }}</span>
                    <span v-if="row.want_cnt" class="num text-[9.5px] text-muted">{{ row.want_cnt }} 人想要</span>
                  </div>
                  <div class="mt-1.5">
                    <MedianBar :price="row.price" :median="row.market_median" />
                  </div>
                </td>

                <td class="px-1 py-3 text-center align-middle">
                  <ScoreMark :score="row.score" :verdict="row.verdict" size="sm" stack />
                </td>

                <td class="px-3 py-3 align-middle">
                  <div class="min-w-0 space-y-0.5">
                    <span
                      v-for="flag in riskFlagsOf(row, 2)"
                      :key="flag"
                      class="flex items-start gap-1 text-[10px] leading-snug text-red"
                    >
                      <Icon name="alert" :size="9" class="mt-[2px] shrink-0" />
                      <span class="truncate" :title="flag">{{ flag }}</span>
                    </span>
                    <span v-if="riskFlagsOf(row, 2).length === 0" class="text-[10px] text-muted">无</span>
                  </div>
                </td>

                <td class="px-4 py-3 align-middle" @click.stop>
                  <div class="flex items-center justify-end gap-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100 max-md:opacity-100">
                    <button
                      v-for="option in feedbackOptions.slice(1)"
                      :key="option.value"
                      type="button"
                      class="shrink-0 whitespace-nowrap rounded-full border px-2 py-1 text-[10px] leading-none transition-colors duration-150"
                      :class="
                        row.feedback === option.value
                          ? feedbackClass(option.value as FeedbackValue)
                          : 'border-line text-ink-2 hover:border-[#d5cec1] hover:bg-paper-2 hover:text-ink'
                      "
                      :aria-pressed="row.feedback === option.value"
                      :title="`标记为${option.label}`"
                      @click="mark(row, option.value as Exclude<FeedbackValue, ''>)"
                    >
                      {{ option.label }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div
        class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
        :class="view === 'table' ? 'md:hidden' : ''"
      >
        <ItemCard
          v-for="row in items"
          :key="row.item_id"
          :item="row"
          @open="openItem"
          @mark="mark"
        />
      </div>

      <div class="mt-4 flex items-center justify-between gap-3 text-[10.5px] text-muted">
        <span>
          已显示 <span class="num text-ink-2">{{ items.length }}</span> 条
          <template v-if="hasMore">，还有更多</template>
        </span>
        <button v-if="hasMore" type="button" class="btn btn-ghost btn-sm" :disabled="loadingMore" @click="load(false)">
          {{ loadingMore ? '正在读…' : '载入更多' }}
        </button>
        <span v-else>按当前筛选已到底</span>
      </div>
    </template>

    <ItemDrawer
      :open="drawerOpen"
      :item-id="activeItem?.item_id ?? null"
      :initial="activeItem"
      @close="closeItem"
      @updated="onFeedback"
    />
  </div>
</template>
