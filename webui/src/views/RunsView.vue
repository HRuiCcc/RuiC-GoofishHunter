<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  EVENTS_URL,
  getLogs,
  getRuns,
  getWatches,
  runWatch,
  type LogEvent,
  type RunRow,
  type Watch,
} from '../api'
import { toast } from '../lib/toast'
import { errorMessage, useAsyncData } from '../lib/useAsync'
import { useNow } from '../lib/useNow'
import { fmtDuration, fmtNumber, fmtStamp, statusInfo, timeAgo } from '../lib/format'
import Icon from '../components/Icon.vue'
import PageHeader from '../components/PageHeader.vue'
import Skeleton from '../components/Skeleton.vue'
import StateBlock from '../components/StateBlock.vue'

const {
  data: runRows,
  loading: runsLoading,
  error: runsError,
  reload: reloadRuns,
} = useAsyncData<RunRow[]>(() => getRuns(30))
const { data: watchList } = useAsyncData<Watch[]>(() => getWatches())
const now = useNow(1000)

/** 本页的任务选择：下拉选一个关注，点「运行」立刻跑一轮。 */
const taskList = computed(() => watchList.value ?? [])
const selectedTaskId = ref<number | ''>('')
const selectedTask = computed(() => taskList.value.find((watch) => watch.id === selectedTaskId.value) ?? null)
const startingRun = ref(false)
const runButtonTitle = computed(() =>
  selectedTask.value ? `立即运行「${selectedTask.value.name}」` : '还没有关注任务，先去「关注」建一个',
)

watch(
  taskList,
  (list) => {
    if (list.length === 0) {
      selectedTaskId.value = ''
      return
    }
    if (list.some((watch) => watch.id === selectedTaskId.value)) return
    selectedTaskId.value = (list.find((watch) => watch.enabled) ?? list[0]).id
  },
  { immediate: true },
)

async function startSelectedRun(): Promise<void> {
  const task = selectedTask.value
  if (!task) {
    toast.info('还没有关注任务，先去「关注」建一个。')
    return
  }
  if (startingRun.value) return
  startingRun.value = true
  try {
    await runWatch(task.id)
    toast.success(`「${task.name}」已开始跑，日志会打在最下面的控制台。`)
    autoScroll.value = true
    await reloadRuns()
    window.setTimeout(() => void reloadRuns(), 1500)
    await nextTick()
    scrollBottom()
  } catch (problem) {
    toast.error(`没跑起来：${errorMessage(problem)}`)
  } finally {
    startingRun.value = false
  }
}

const logs = ref<LogEvent[]>([])
const logsLoading = ref(true)
const logError = ref<string | null>(null)
const connection = ref<'connecting' | 'live' | 'reconnecting'>('connecting')
const autoScroll = ref(true)
const consoleFilter = ref('')
const consoleBody = ref<HTMLElement | null>(null)
const seen = new Set<string>()
let source: EventSource | null = null

const MAX_LOGS = 600

const filterOptions = computed(() => {
  const names = new Set<string>()
  for (const log of logs.value) {
    if (log.watch) names.add(log.watch)
  }
  for (const watch of watchList.value ?? []) names.add(watch.name)
  return [
    { value: '', label: '全部关注' },
    ...[...names].sort((a, b) => a.localeCompare(b, 'zh-CN')).map((name) => ({ value: name, label: name })),
  ]
})

const filteredLogs = computed(() =>
  consoleFilter.value ? logs.value.filter((log) => log.watch === consoleFilter.value) : logs.value,
)

const connectionInfo = computed(
  () =>
    ({
      connecting: { label: '连接中', color: '#F0B429' },
      live: { label: '实时连接', color: '#4ED6A8' },
      reconnecting: { label: '重连中', color: '#FF5A3C' },
    })[connection.value],
)

function keyOf(event: LogEvent): string {
  return `${event.ts}|${event.level}|${event.msg}|${event.watch ?? ''}|${event.run ?? ''}|${event.score ?? ''}`
}

function push(event: LogEvent): void {
  const key = keyOf(event)
  if (seen.has(key)) return
  seen.add(key)
  logs.value.push(event)
  if (logs.value.length > MAX_LOGS) {
    const removed = logs.value.splice(0, logs.value.length - MAX_LOGS)
    for (const item of removed) seen.delete(keyOf(item))
  }
}

async function bootstrap(): Promise<void> {
  logsLoading.value = true
  try {
    const seed = await getLogs(200)
    logs.value = []
    seen.clear()
    for (const event of seed) push(event)
    logError.value = null
  } catch (problem) {
    logError.value = errorMessage(problem)
  } finally {
    logsLoading.value = false
  }
  connect()
}

function connect(): void {
  source?.close()
  connection.value = 'connecting'
  const stream = new EventSource(EVENTS_URL)
  source = stream
  stream.onopen = () => {
    if (source === stream) connection.value = 'live'
  }
  stream.onerror = () => {
    if (source === stream) connection.value = 'reconnecting'
  }
  stream.onmessage = (message) => {
    try {
      push(JSON.parse(message.data) as LogEvent)
    } catch {
      // 忽略解析不了的行
    }
  }
}

function levelLabel(level: string): string {
  return ({ info: '信息', ok: '完成', warn: '注意', error: '出错', score: '评分' } as Record<string, string>)[level] ?? level
}

function levelClass(level: string): string {
  return (
    {
      info: 'text-[#6f6a60]',
      ok: 'text-jade',
      warn: 'text-amber',
      error: 'text-red',
      score: 'text-amber',
    } as Record<string, string>
  )[level] ?? 'text-[#6f6a60]'
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-red'
  if (score >= 65) return 'text-jade'
  if (score >= 50) return 'text-amber'
  return 'text-muted'
}

function statusPill(tone: 'jade' | 'ochre' | 'red' | 'muted'): string {
  if (tone === 'jade') return 'border-jade/40 bg-jade/10 text-jade'
  if (tone === 'ochre') return 'border-amber/40 bg-amber/10 text-amber'
  if (tone === 'red') return 'border-red/40 bg-red/10 text-red'
  return 'border-line bg-raise text-muted'
}

function scrollBottom(): void {
  const element = consoleBody.value
  if (!element) return
  element.scrollTop = element.scrollHeight
}

function onScroll(): void {
  const element = consoleBody.value
  if (!element) return
  autoScroll.value = element.scrollHeight - element.scrollTop - element.clientHeight < 12
}

function toggleAutoScroll(): void {
  autoScroll.value = !autoScroll.value
  if (autoScroll.value) void nextTick(scrollBottom)
}

function clearLogs(): void {
  logs.value = []
  seen.clear()
}

watch(
  () => filteredLogs.value.length,
  () => {
    if (autoScroll.value) void nextTick(scrollBottom)
  },
)

watch(consoleFilter, () => {
  if (autoScroll.value) void nextTick(scrollBottom)
})

let pollTimer = 0
onMounted(() => {
  void bootstrap()
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void reloadRuns()
  }, 20000)
})

onBeforeUnmount(() => {
  source?.close()
  source = null
  window.clearInterval(pollTimer)
})
</script>

<template>
  <div>
    <PageHeader title="运行" subtitle="每一轮扫描都记一笔；选一个任务点「运行」就能立刻跑一轮，下面那台控制台会实时打印。">
      <template #actions>
        <button type="button" class="btn btn-ghost" @click="reloadRuns()">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
        <RouterLink to="/watches" class="btn btn-ghost">
          <Icon name="target" :size="13" /> 去关注
        </RouterLink>

        <div class="flex items-center gap-1.5">
          <span class="relative flex items-center">
            <select
              v-model="selectedTaskId"
              class="h-10 w-[176px] max-w-[50vw] appearance-none truncate rounded-[10px] border border-line bg-surface pl-3 pr-8 text-[12px] text-ink transition-[border-color,background-color] duration-150 hover:border-[#d6cec0] hover:bg-[#fffdf9] disabled:cursor-not-allowed disabled:text-muted disabled:hover:border-line disabled:hover:bg-surface"
              :disabled="taskList.length === 0"
              aria-label="选择要运行的任务"
            >
              <option v-if="taskList.length === 0" value="">暂无关注任务</option>
              <option v-for="task in taskList" :key="task.id" :value="task.id">
                {{ task.name }}{{ task.enabled ? '' : ' · 已暂停' }}
              </option>
            </select>
            <Icon
              name="chevronDown"
              :size="12"
              class="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
            />
          </span>

          <button
            type="button"
            class="btn btn-primary"
            :disabled="startingRun || !selectedTask"
            :title="runButtonTitle"
            :aria-label="runButtonTitle"
            @click="startSelectedRun"
          >
            <Icon
              :name="startingRun ? 'loader' : 'play'"
              :size="13"
              :class="startingRun ? 'animate-spin' : ''"
            />
            {{ startingRun ? '正在跑' : '运行' }}
          </button>
        </div>
      </template>
    </PageHeader>

    <section class="mt-6">
      <div class="flex items-baseline justify-between gap-4 pb-2.5">
        <h2 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">运行历史</h2>
        <span class="num text-[10.5px] text-muted">
          {{ runRows?.length ? `最近 ${runRows.length} 轮 · 表内滚动` : '最近 0 轮' }}
        </span>
      </div>

      <div v-if="runsLoading && !runRows" class="surface-card p-4">
        <div v-for="index in 4" :key="index" class="flex items-center gap-5 border-b border-line/70 py-3.5 last:border-b-0">
          <Skeleton width="7rem" height="0.8rem" />
          <Skeleton width="10rem" height="0.8rem" />
          <Skeleton width="3rem" height="0.8rem" />
          <Skeleton width="3rem" height="0.8rem" />
          <Skeleton width="4rem" height="0.8rem" />
        </div>
      </div>

      <StateBlock
        v-else-if="runsError && !runRows"
        kind="error"
        title="运行记录没读出来"
        :description="runsError"
        class="mt-4"
      >
        <button type="button" class="btn btn-ghost" @click="reloadRuns()">重试</button>
      </StateBlock>

      <StateBlock
        v-else-if="(runRows ?? []).length === 0"
        title="还没有运行记录"
        description="在右上角选一个任务点「运行」，这里会记下这一轮抓到多少、评了多少、推了几条，下面的控制台会同时开始滚动；还没有任务就先点「去关注」建一个。"
        class="mt-4"
      >
        <RouterLink to="/watches" class="btn btn-primary">
          <Icon name="target" :size="13" /> 去关注运行一轮
        </RouterLink>
      </StateBlock>

      <div v-else class="surface-card overflow-hidden">
        <div class="max-h-[440px] overflow-y-auto">
          <table class="w-full min-w-[900px] table-fixed border-collapse">
            <colgroup>
              <col style="width: 116px" />
              <col />
              <col style="width: 60px" />
              <col style="width: 52px" />
              <col style="width: 60px" />
              <col style="width: 60px" />
              <col style="width: 86px" />
              <col style="width: 100px" />
            </colgroup>
            <thead>
              <tr>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-4 py-2.5 text-left"><span class="label-xs">时间</span></th>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-3 py-2.5 text-left"><span class="label-xs">关注</span></th>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-1 py-2.5 text-right"><span class="label-xs">抓到</span></th>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-1 py-2.5 text-right"><span class="label-xs">新</span></th>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-1 py-2.5 text-right"><span class="label-xs">评分</span></th>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-1 py-2.5 text-right"><span class="label-xs">推送</span></th>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-3 py-2.5 text-left"><span class="label-xs">耗时</span></th>
                <th class="sticky top-0 z-10 border-b border-line bg-surface px-4 py-2.5 text-right"><span class="label-xs">状态</span></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="run in runRows ?? []"
                :key="run.id"
                class="border-b border-line/70 transition-[background-color,box-shadow] duration-150 last:border-b-0 hover:bg-paper-2 hover:shadow-[inset_2px_0_0_#FF5A3C]"
              >
                <td class="px-4 py-3 align-top">
                  <p class="num text-[11.5px] leading-none text-ink">{{ fmtStamp(run.started_at) }}</p>
                  <p class="mt-1.5 text-[10px] text-muted">{{ timeAgo(run.started_at, now) }}</p>
                </td>
                <td class="min-w-0 px-3 py-3 align-top">
                  <p class="truncate text-[12.5px] text-ink">{{ run.watch_name || `关注 #${run.watch_id ?? ''}` }}</p>
                  <p class="mt-1 truncate font-mono text-[10px] text-muted" :title="run.keyword ?? ''">
                    {{ run.keyword || '关键词已删' }}
                  </p>
                  <p v-if="run.error" class="mt-1 truncate text-[10px] text-red" :title="run.error">{{ run.error }}</p>
                </td>
                <td class="num px-1 py-3 text-right align-top text-[12px] text-ink-2">{{ fmtNumber(run.found ?? 0) }}</td>
                <td class="num px-1 py-3 text-right align-top text-[12px] text-ink">{{ fmtNumber(run.new_items ?? 0) }}</td>
                <td class="num px-1 py-3 text-right align-top text-[12px] text-ink-2">{{ fmtNumber(run.scored ?? 0) }}</td>
                <td
                  class="num px-1 py-3 text-right align-top text-[12px]"
                  :class="(run.alerted ?? 0) > 0 ? 'text-red' : 'text-ink-2'"
                >
                  {{ fmtNumber(run.alerted ?? 0) }}
                </td>
                <td class="num px-3 py-3 align-top text-[11px] text-ink-2">{{ fmtDuration(run.started_at, run.finished_at) }}</td>
                <td class="px-4 py-3 text-right align-top">
                  <span
                    class="inline-flex rounded-full border px-2 py-0.5 text-[10px] leading-none"
                    :class="statusPill(statusInfo(run.status).tone)"
                  >
                    {{ statusInfo(run.status).label }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section
      class="mt-6 overflow-hidden rounded-[14px] border border-line bg-[#fbf9f4] shadow-card"
      aria-label="实时控制台"
    >
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div class="flex items-center gap-2.5">
          <h2 class="text-[13.5px] font-semibold tracking-[-0.01em] text-ink">控制台</h2>
          <span class="num text-[10px] text-muted">{{ filteredLogs.length }} 行</span>
          <span class="flex items-center gap-1.5">
            <span class="inline-block h-1.5 w-1.5 rounded-full" :style="{ backgroundColor: connectionInfo.color }" aria-hidden="true"></span>
            <span class="text-[10px]" :style="{ color: connectionInfo.color }">{{ connectionInfo.label }}</span>
          </span>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <div class="w-[140px]">
            <span class="relative block">
              <select
                v-model="consoleFilter"
                class="h-8 w-full appearance-none rounded-[10px] border border-line bg-white pl-2.5 pr-7 text-[11px] text-ink outline-none"
                aria-label="按关注过滤控制台"
              >
                <option v-for="option in filterOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <Icon
                name="chevronDown"
                :size="12"
                class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted"
              />
            </span>
          </div>
          <button
            type="button"
            class="rounded-full border border-line px-2.5 py-1 text-[10.5px] leading-none transition-colors duration-150"
            :class="autoScroll ? 'text-jade' : 'text-muted hover:text-ink'"
            :aria-pressed="autoScroll"
            @click="toggleAutoScroll"
          >
            自动滚动 {{ autoScroll ? '开' : '关' }}
          </button>
          <button
            type="button"
            class="rounded-full border border-line px-2.5 py-1 text-[10.5px] leading-none text-muted transition-colors duration-150 hover:text-ink"
            @click="clearLogs"
          >
            清空
          </button>
        </div>
      </div>

      <div
        ref="consoleBody"
        class="console-scroll overflow-y-auto px-4 py-2 font-mono text-[11.5px] leading-[1.8]"
        :class="filteredLogs.length ? 'h-[340px]' : 'h-[220px]'"
        @scroll.passive="onScroll"
      >
        <div v-if="logsLoading" class="space-y-2 py-2">
          <div class="h-3 w-2/3 rounded bg-[#ece7dd]"></div>
          <div class="h-3 w-1/2 rounded bg-[#ece7dd]"></div>
          <div class="h-3 w-3/4 rounded bg-[#ece7dd]"></div>
        </div>

        <p v-else-if="logError" class="py-2 text-red">日志没读出来：{{ logError }}</p>

        <p v-else-if="filteredLogs.length === 0" class="py-8 text-muted">
          {{
            consoleFilter
              ? `「${consoleFilter}」还没有日志。换一个关注，或者点「全部关注」看全部。`
              : '控制台还没收到日志：去「关注」点「立即运行」，日志会逐行打印在这里。'
          }}
        </p>

        <div
          v-for="(log, index) in filteredLogs"
          :key="index"
          class="flex gap-2 whitespace-pre-wrap break-words rounded px-1 py-[1px] transition-colors duration-100 hover:bg-white/[0.03]"
        >
          <span class="shrink-0 text-[#5f5b53]">{{ log.ts }}</span>
          <span class="w-[2rem] shrink-0" :class="levelClass(log.level)">{{ levelLabel(log.level) }}</span>
          <span v-if="log.watch" class="shrink-0 text-muted">「{{ log.watch }}」</span>
          <span class="min-w-0 text-[#d8d2c6]">{{ log.msg }}</span>
          <span
            v-if="log.score !== undefined && log.score !== null"
            class="num ml-2 shrink-0 font-medium"
            :class="scoreColor(log.score)"
          >
            {{ log.score }} 分
          </span>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-2 text-[10px] text-muted">
        <span>只留最近 {{ MAX_LOGS }} 行；断线后 EventSource 自己重连。</span>
        <span class="num">127.0.0.1:7801 /api/events</span>
      </div>
    </section>
  </div>
</template>
