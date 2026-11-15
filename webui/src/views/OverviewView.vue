<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  getOverview,
  getWatches,
  type FeedbackValue,
  type ItemRow,
  type Overview,
  type Watch,
} from '../api'
import { useAsyncData } from '../lib/useAsync'
import { useNow } from '../lib/useNow'
import { useRowIntro } from '../lib/useRowIntro'
import {
  countdown,
  fmtMoney,
  fmtNumber,
  fmtStamp,
  relativeText,
  statusInfo,
  timeAgo,
  verdictFromScore,
} from '../lib/format'
import CountUp from '../components/CountUp.vue'
import Icon from '../components/Icon.vue'
import ItemDrawer from '../components/ItemDrawer.vue'
import LineChart, { type ChartPoint } from '../components/LineChart.vue'
import MedianBar from '../components/MedianBar.vue'
import PageHeader from '../components/PageHeader.vue'
import ScoreMark from '../components/ScoreMark.vue'
import Skeleton from '../components/Skeleton.vue'
import StateBlock from '../components/StateBlock.vue'

const router = useRouter()
const {
  data: overviewData,
  loading: overviewLoading,
  error: overviewError,
  reload: reloadOverview,
} = useAsyncData<Overview>(() => getOverview())
const {
  data: watchList,
  loading: watchesLoading,
  error: watchesError,
  reload: reloadWatches,
} = useAsyncData<Watch[]>(() => getWatches())
const now = useNow(1000)
const { fresh: freshRows, sync: syncIntro } = useRowIntro()

const rows = computed(() => overviewData.value?.top ?? [])
const activeItem = ref<ItemRow | null>(null)
const drawerOpen = computed(() => activeItem.value !== null)

watch(
  rows,
  (value) => syncIntro(value.map((row) => row.item_id)),
  { immediate: true },
)

const activeWatches = computed(() => (watchList.value ?? []).filter((watch) => watch.enabled))

const nextWatch = computed(() => {
  const sorted = [...activeWatches.value]
    .filter((watch) => watch.next_run_at)
    .sort((a, b) => String(a.next_run_at).localeCompare(String(b.next_run_at)))
  return sorted[0] ?? null
})

const nextCountdown = computed(() => countdown(nextWatch.value?.next_run_at ?? null, now.value))

const railWatches = computed(() =>
  [...activeWatches.value]
    .sort((a, b) => String(a.next_run_at ?? '9999').localeCompare(String(b.next_run_at ?? '9999')))
    .slice(0, 4),
)

const verdictLine = computed(() => {
  const by = overviewData.value?.by_verdict ?? {}
  return `强推 ${by['强烈推荐'] ?? 0} · 值得看 ${by['值得看'] ?? 0} · 观望 ${by['观望'] ?? 0}`
})

const lastRunText = computed(() => {
  const last = overviewData.value?.last_run
  if (!last) return '还没有扫描记录'
  return `上次扫描 ${fmtStamp(last.started_at)} · ${statusInfo(last.status).label}`
})

const metrics = computed(() => {
  const data = overviewData.value
  return [
    {
      label: '今日新货',
      value: data?.today_items ?? 0,
      decimals: 0,
      unit: '条',
      sub: `共 ${fmtNumber(data?.total_items ?? 0)} 条在库`,
    },
    {
      label: '今日推送',
      value: data?.alerts_today ?? 0,
      decimals: 0,
      unit: '条',
      sub: `跑了 ${fmtNumber(data?.today_runs ?? 0)} 轮`,
    },
    {
      label: '平均分',
      value: data?.avg_score ?? null,
      decimals: 1,
      unit: data?.avg_score !== null && data?.avg_score !== undefined ? '分' : '',
      sub: verdictLine.value,
    },
    {
      label: '在跑关注',
      value: data?.active_watches ?? 0,
      decimals: 0,
      unit: '条',
      sub: activeWatches.value.length ? `下次 ${nextCountdown.value.text}` : '全部暂停',
    },
  ]
})

const trendPoints = computed<ChartPoint[]>(() =>
  (overviewData.value?.trend ?? []).map((point) => ({
    label: point.day.slice(5),
    value: point.avg_price,
    volume: point.n,
  })),
)

const trendSummary = computed(() => {
  const values = trendPoints.value
    .map((point) => point.value)
    .filter((value): value is number => value !== null)
  if (values.length < 2) return ''
  const first = values[0]
  const last = values[values.length - 1]
  const average = values.reduce((total, value) => total + value, 0) / values.length
  const delta = first ? ((last - first) / first) * 100 : 0
  return `14 天均价 ${fmtMoney(average)} · 较首日${delta >= 0 ? '涨' : '跌'} ${Math.abs(delta).toFixed(1)}%`
})

const trendSummaryShort = computed(() => {
  const values = trendPoints.value
    .map((point) => point.value)
    .filter((value): value is number => value !== null)
  if (values.length < 2) return ''
  return fmtMoney(values[values.length - 1])
})

const bestItem = computed(() => rows.value[0] ?? null)
const bestScore = computed(() => bestItem.value?.score ?? overviewData.value?.best?.score ?? null)
const bestVerdict = computed(() =>
  bestItem.value?.verdict || verdictFromScore(bestScore.value),
)
const bestTitle = computed(() => bestItem.value?.title ?? overviewData.value?.best?.title ?? '')
const bestPrice = computed(() => bestItem.value?.price ?? overviewData.value?.best?.price ?? null)
const bestMeta = computed(() => {
  if (!bestItem.value) return ''
  return [bestItem.value.spec_key, bestItem.value.area, bestItem.value.seller_nick]
    .filter(Boolean)
    .join(' · ')
})
const bestDiscount = computed(() =>
  bestItem.value ? relativeText(bestItem.value.price, bestItem.value.market_median) : '',
)
const bestReasons = computed(() => (bestItem.value?.reasons_json ?? []).slice(0, 3))

function openItem(row: ItemRow): void {
  activeItem.value = row
}

function openBest(): void {
  if (bestItem.value) activeItem.value = bestItem.value
  else router.push('/items')
}

function closeItem(): void {
  activeItem.value = null
}

function onFeedback(payload: { itemId: string; feedback: FeedbackValue }): void {
  const row = overviewData.value?.top.find((entry) => entry.item_id === payload.itemId)
  if (row) row.feedback = payload.feedback
}

function reload(): void {
  void reloadOverview()
  void reloadWatches()
}

let timer = 0
onMounted(() => {
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') reload()
  }, 45000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div>
    <PageHeader title="概览" :subtitle="lastRunText">
      <template #actions>
        <button type="button" class="btn btn-ghost" @click="reload">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
        <button type="button" class="btn btn-primary" @click="router.push('/watches?new=1')">
          <Icon name="plus" :size="13" /> 新建关注
        </button>
      </template>
    </PageHeader>

    <div v-if="overviewError && !overviewData" class="pt-5">
      <StateBlock kind="error" title="概览没读出来" :description="overviewError">
        <button type="button" class="btn btn-ghost" @click="reloadOverview()">
          <Icon name="refresh" :size="13" /> 重试
        </button>
      </StateBlock>
    </div>

    <template v-else>
      <section class="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="今日账目">
        <div v-for="metric in metrics" :key="metric.label" class="surface-card p-4 lg:p-5">
          <p class="text-[10.5px] font-medium tracking-[0.08em] text-muted">{{ metric.label }}</p>
          <div class="mt-3 flex items-baseline gap-1">
            <Skeleton v-if="overviewLoading && !overviewData" width="4rem" height="2.1rem" />
            <CountUp
              v-else
              :value="metric.value"
              :decimals="metric.decimals"
              class="text-[30px] font-semibold leading-none tracking-[-0.03em] text-ink lg:text-[34px]"
            />
            <span v-if="metric.unit" class="text-[10.5px] text-muted">{{ metric.unit }}</span>
          </div>
          <p class="mt-2.5 truncate text-[10.5px] text-ink-2" :title="metric.sub">{{ metric.sub }}</p>
        </div>
      </section>

      <section class="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <article class="relative flex flex-col overflow-hidden rounded-[14px] border border-[#EBD8C9] bg-cream p-5 text-cream-ink shadow-card lg:p-7">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p class="text-[10.5px] font-medium tracking-[0.16em] text-[#6B6255]">今日最强一笔</p>
              <div v-if="bestItem" class="mt-4 flex items-end gap-2.5">
                <CountUp
                  :value="bestScore"
                  :decimals="0"
                  class="text-[64px] font-semibold leading-[0.85] tracking-[-0.055em] lg:text-[78px]"
                />
                <span class="pb-2 text-[12px] text-[#6B6255]">分 · {{ bestVerdict }}</span>
              </div>
              <p v-else class="mt-4 text-[30px] font-semibold leading-tight tracking-[-0.03em]">
                今天还没开张
              </p>
            </div>
            <span
              v-if="bestMeta"
              class="max-w-[240px] truncate rounded-full border border-[#CBBCA4] px-3 py-1 text-[10.5px] text-[#5B5346]"
            >
              {{ bestMeta }}
            </span>
          </div>

          <template v-if="bestItem">
            <div class="mt-5 grid flex-1 gap-5 lg:grid-cols-[minmax(0,1.12fr)_minmax(0,0.88fr)]">
              <div class="flex min-w-0 flex-col">
                <h2 class="line-clamp-3 text-[17px] font-semibold leading-snug tracking-[-0.02em] lg:text-[19px]">
                  {{ bestTitle }}
                </h2>
                <div class="mt-4 flex flex-wrap items-end gap-x-4 gap-y-2">
                  <span class="num text-[24px] font-semibold leading-none tracking-[-0.03em]">
                    {{ fmtMoney(bestPrice) }}
                  </span>
                  <span class="text-[12px] text-[#6B6255]">
                    中位 {{ fmtMoney(bestItem.market_median, '样本不足') }}
                  </span>
                  <span
                    v-if="bestDiscount && bestDiscount !== '样本不足'"
                    class="rounded-full bg-[#15130F]/[0.08] px-2 py-0.5 text-[10.5px] text-[#15130F]"
                  >
                    {{ bestDiscount }}
                  </span>
                </div>
                <div class="mt-auto pt-6">
                  <button
                    type="button"
                    class="inline-flex h-10 shrink-0 items-center gap-2 rounded-[10px] bg-red px-4 text-[12.5px] font-medium text-[#FFF9F3] transition-colors duration-150 hover:bg-[#C4381F] focus-visible:outline-[#FFF9F3] active:scale-[0.98]"
                    @click="openBest"
                  >
                    去看看 <Icon name="arrowRight" :size="14" />
                  </button>
                </div>
              </div>

              <div class="flex min-w-0 flex-col border-t border-[#D3C6B0] pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
                <p class="text-[10.5px] font-medium tracking-[0.12em] text-[#6B6255]">为什么值得</p>
                <ul v-if="bestReasons.length" class="mt-2 space-y-1.5">
                  <li
                    v-for="(reason, index) in bestReasons"
                    :key="index"
                    class="flex gap-2 text-[12px] leading-relaxed text-[#4E4638]"
                  >
                    <span class="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[#15130F]/35" aria-hidden="true"></span>
                    <span class="line-clamp-2">{{ reason }}</span>
                  </li>
                </ul>
                <p v-else class="mt-2 text-[11.5px] leading-relaxed text-[#6B6255]">
                  还没攒到评分理由，等下一轮扫描。
                </p>

                <div class="mt-auto pt-4">
                  <div class="flex items-baseline justify-between gap-2 text-[10px] text-[#6B6255]">
                    <span>近 14 天均价</span>
                    <span class="num">{{ trendSummaryShort }}</span>
                  </div>
                  <LineChart
                    v-if="trendPoints.length >= 2"
                    :points="trendPoints"
                    :height="58"
                    :show-axis="false"
                    line-color="#15130F"
                    area-color="rgba(21,19,15,0.07)"
                    grid-color="#CBBCA4"
                    dot-color="#EDE4D6"
                    accent-color="#D8432A"
                    class="mt-1"
                    aria-label="近 14 天均价走势"
                  />
                  <p v-else class="mt-1.5 text-[10.5px] text-[#6B6255]">走势还没攒够样本</p>
                </div>
              </div>
            </div>
          </template>

          <template v-else>
            <p class="mt-4 max-w-[44ch] text-[12px] leading-relaxed text-[#6B6255]">
              建一个关键词，先试抓一次；有人低价出货时，这一格会亮起来。
            </p>
            <button
              type="button"
              class="mt-5 inline-flex h-10 items-center gap-2 rounded-[10px] bg-red px-4 text-[12.5px] font-medium text-[#FFF9F3] transition-colors duration-150 hover:bg-[#C4381F] focus-visible:outline-[#FFF9F3] focus-visible:outline-offset-[3px] active:scale-[0.98]"
              @click="router.push('/watches?new=1')"
            >
              <Icon name="plus" :size="13" /> 建第一个关注
            </button>
          </template>
        </article>

        <div class="grid gap-3">
          <section class="surface-card p-4 lg:p-5">
            <div class="flex items-baseline justify-between gap-3">
              <h2 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">在跑关注</h2>
              <span class="num text-[10.5px] text-muted">{{ activeWatches.length }} 条</span>
            </div>

            <div v-if="watchesLoading && !watchList" class="mt-3 space-y-3">
              <div v-for="index in 3" :key="index" class="space-y-1.5">
                <Skeleton width="60%" height="0.8rem" />
                <Skeleton width="40%" height="0.65rem" />
              </div>
            </div>
            <p v-else-if="watchesError" class="mt-3 text-[11.5px] text-red">{{ watchesError }}</p>
            <ul v-else-if="railWatches.length" class="mt-2">
              <li v-for="watch in railWatches" :key="watch.id">
                <RouterLink
                  :to="`/items?watch=${watch.id}`"
                  class="-mx-2 flex items-center gap-2.5 rounded-[10px] px-2 py-2.5 transition-colors duration-150 hover:bg-paper-2"
                >
                  <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-jade" aria-hidden="true"></span>
                  <span class="min-w-0 flex-1">
                    <span class="block truncate text-[12.5px] text-ink">{{ watch.name }}</span>
                    <span class="mt-1 block truncate font-mono text-[10px] text-muted">{{ watch.keyword }}</span>
                  </span>
                  <span
                    class="num shrink-0 text-[10px]"
                    :class="countdown(watch.next_run_at, now).seconds < 120 ? 'text-red' : 'text-muted'"
                  >
                    {{ countdown(watch.next_run_at, now).text }}
                  </span>
                </RouterLink>
              </li>
            </ul>
            <p v-else class="mt-3 text-[11.5px] leading-relaxed text-ink-2">
              没有启用的关注。去「关注」打开一个，或者新建一条。
            </p>

            <RouterLink
              to="/watches"
              class="mt-3 inline-flex items-center gap-1 text-[11px] text-ink-2 transition-colors hover:text-ink"
            >
              管理关注 <Icon name="chevronRight" :size="11" />
            </RouterLink>
          </section>

          <section class="surface-card p-4 lg:p-5">
            <div class="flex items-baseline justify-between gap-3">
              <h2 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">近 14 天价格</h2>
              <span class="text-[10.5px] text-muted">日均价</span>
            </div>
            <div v-if="trendPoints.length >= 2" class="mt-3">
              <LineChart :points="trendPoints" :height="110" show-volume />
              <p class="mt-2 text-[10.5px] leading-relaxed text-ink-2">{{ trendSummary }}</p>
            </div>
            <p v-else class="mt-3 text-[11.5px] leading-relaxed text-ink-2">
              同一天多次扫描不会连成线；明后天各跑一轮，这里就会按天画出均价和样本量。
            </p>
          </section>
        </div>
      </section>

      <section class="surface-card mt-3 overflow-hidden">
        <div class="flex items-baseline justify-between gap-4 border-b border-line px-4 py-3.5 lg:px-5">
          <div class="flex items-baseline gap-3">
            <h2 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">捡漏榜</h2>
            <span v-if="rows.length" class="num text-[10.5px] text-muted">按分数取前 {{ rows.length }} 条</span>
            <span v-else class="text-[10.5px] text-muted">还没有商品</span>
          </div>
          <RouterLink
            to="/items"
            class="inline-flex items-center gap-1 text-[11px] text-ink-2 transition-colors hover:text-ink"
          >
            全部商品 <Icon name="chevronRight" :size="11" />
          </RouterLink>
        </div>

        <div v-if="overviewLoading && !overviewData" class="space-y-0 px-4 py-2">
          <div v-for="index in 6" :key="index" class="flex items-center gap-4 border-b border-line/70 py-3.5">
            <Skeleton width="1.5rem" height="0.7rem" />
            <Skeleton width="2.5rem" height="1.1rem" />
            <div class="flex-1 space-y-1.5">
              <Skeleton width="70%" height="0.8rem" />
              <Skeleton width="35%" height="0.65rem" />
            </div>
            <Skeleton width="4rem" height="0.8rem" />
            <Skeleton width="6rem" height="0.8rem" />
          </div>
        </div>

        <StateBlock
          v-else-if="overviewError"
          kind="error"
          title="捡漏榜没读出来"
          :description="overviewError"
          class="m-4"
        >
          <button type="button" class="btn btn-ghost" @click="reloadOverview()">重试</button>
        </StateBlock>

        <StateBlock
          v-else-if="rows.length === 0"
          title="捡漏榜还空着"
          description="账本里还没有商品。先去「关注」建一个关键词，点「试抓一次」看看能不能抓到东西，再让它在后台按间隔扫。"
          class="m-4"
        >
          <button type="button" class="btn btn-primary" @click="router.push('/watches?new=1')">
            <Icon name="plus" :size="13" /> 建第一个关注
          </button>
          <button type="button" class="btn btn-ghost" @click="router.push('/runs')">去看运行日志</button>
        </StateBlock>

        <div v-else>
          <div class="hidden overflow-x-auto md:block">
            <table class="w-full min-w-[900px] table-fixed border-collapse">
              <colgroup>
                <col style="width: 56px" />
                <col style="width: 72px" />
                <col />
                <col style="width: 110px" />
                <col style="width: 170px" />
                <col style="width: 120px" />
                <col style="width: 100px" />
                <col style="width: 90px" />
              </colgroup>
              <thead>
                <tr class="border-b border-line text-left">
                  <th class="py-2.5 pl-5 pr-1"><span class="label-xs">名次</span></th>
                  <th class="px-1 py-2.5"><span class="label-xs">分数</span></th>
                  <th class="px-3 py-2.5"><span class="label-xs">商品</span></th>
                  <th class="px-1 py-2.5 text-right"><span class="label-xs">价格</span></th>
                  <th class="px-3 py-2.5"><span class="label-xs">对比中位价</span></th>
                  <th class="px-3 py-2.5"><span class="label-xs">卖家</span></th>
                  <th class="px-1 py-2.5"><span class="label-xs">发现</span></th>
                  <th class="px-5 py-2.5 text-right"><span class="label-xs">操作</span></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, index) in rows"
                  :key="row.item_id"
                  class="group cursor-pointer border-b border-line/70 transition-[background-color,box-shadow] duration-150 last:border-b-0 hover:bg-paper-2 hover:shadow-[inset_2px_0_0_#FF5A3C]"
                  :class="{ 'row-in': freshRows.has(row.item_id) }"
                  :style="
                    freshRows.has(row.item_id)
                      ? { animationDelay: `${Math.min(index, 8) * 16}ms` }
                      : undefined
                  "
                  tabindex="0"
                  :aria-label="`查看 ${row.title}`"
                  @click="openItem(row)"
                  @keydown.enter.prevent="openItem(row)"
                  @keydown.space.prevent="openItem(row)"
                >
                  <td class="py-3 pl-5 pr-1 align-middle">
                    <span class="num text-[11px]" :class="index === 0 ? 'text-red' : 'text-muted'">
                      {{ String(index + 1).padStart(2, '0') }}
                    </span>
                  </td>
                  <td class="px-1 py-3 align-middle">
                    <ScoreMark
                      :score="row.score"
                      :verdict="row.verdict || verdictFromScore(row.score)"
                      size="sm"
                      stack
                    />
                  </td>
                  <td class="px-3 py-3 align-middle">
                    <p class="truncate text-[13px] font-medium leading-snug tracking-[-0.01em] text-ink">
                      {{ row.title }}
                    </p>
                    <div class="mt-1.5 flex items-center gap-1.5 text-[10px] text-muted">
                      <span
                        v-if="row.spec_key"
                        class="num shrink-0 rounded-full border border-line bg-raise px-1.5 py-0.5 leading-none text-ink-2"
                      >
                        {{ row.spec_key }}
                      </span>
                      <span class="truncate">{{ row.area || '地区未知' }}</span>
                    </div>
                  </td>
                  <td class="px-1 py-3 text-right align-middle">
                    <span class="num text-[13.5px] leading-none text-ink">{{ fmtMoney(row.price) }}</span>
                  </td>
                  <td class="px-3 py-3 align-middle">
                    <MedianBar :price="row.price" :median="row.market_median" />
                  </td>
                  <td class="px-3 py-3 align-middle">
                    <span class="block truncate text-[11px] text-ink-2">{{ row.seller_nick || '匿名' }}</span>
                  </td>
                  <td class="px-1 py-3 align-middle">
                    <span class="block truncate text-[10px] text-muted" :title="fmtStamp(row.first_seen_at)">
                      {{ timeAgo(row.first_seen_at, now) }}
                    </span>
                  </td>
                  <td class="px-5 py-3 text-right align-middle">
                    <div class="flex justify-end opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100 max-md:opacity-100">
                      <button type="button" class="btn btn-ghost btn-sm rounded-full" @click.stop="openItem(row)">
                        详情
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="md:hidden">
            <div
              v-for="(row, index) in rows"
              :key="`m-${row.item_id}`"
              class="group flex cursor-pointer items-start gap-3 border-b border-line/70 px-4 py-3.5 transition-colors duration-150 last:border-b-0 hover:bg-paper-2"
              :class="{ 'row-in': freshRows.has(row.item_id) }"
              tabindex="0"
              role="button"
              :aria-label="`查看 ${row.title}`"
              @click="openItem(row)"
              @keydown.enter.prevent="openItem(row)"
              @keydown.space.prevent="openItem(row)"
            >
              <span class="num mt-1 w-4 shrink-0 text-[10px]" :class="index === 0 ? 'text-red' : 'text-muted'">
                {{ String(index + 1).padStart(2, '0') }}
              </span>
              <div class="min-w-0 flex-1">
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
                  <span>{{ row.area || '地区未知' }}</span>
                  <span class="truncate">{{ row.seller_nick || '匿名' }}</span>
                  <span class="num shrink-0">{{ timeAgo(row.first_seen_at, now) }}</span>
                </div>
                <div class="mt-2.5 flex items-baseline gap-2">
                  <span class="num text-[15px] leading-none text-ink">{{ fmtMoney(row.price) }}</span>
                  <span class="text-[10px] text-ink-2">{{ relativeText(row.price, row.market_median) }}</span>
                </div>
                <MedianBar class="mt-2" :price="row.price" :median="row.market_median" />
              </div>
              <div class="shrink-0 pt-0.5">
                <ScoreMark
                  :score="row.score"
                  :verdict="row.verdict || verdictFromScore(row.score)"
                  size="sm"
                  stack
                />
              </div>
            </div>
          </div>

          <div class="flex items-center justify-between gap-3 border-t border-line px-5 py-3 text-[10.5px] text-muted">
            <span>共 {{ fmtNumber(overviewData?.total_items) }} 条在库；这里只列分数最高的 {{ rows.length }} 条。</span>
            <RouterLink to="/items" class="inline-flex items-center gap-1 text-ink-2 hover:text-ink">
              去商品库筛选 <Icon name="chevronRight" :size="11" />
            </RouterLink>
          </div>
        </div>
      </section>
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
