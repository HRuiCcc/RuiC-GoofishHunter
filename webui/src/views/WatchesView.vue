<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { deleteWatch, getWatches, patchWatch, runWatch, type Watch } from '../api'
import { useAsyncData } from '../lib/useAsync'
import { useNow } from '../lib/useNow'
import { useRowIntro } from '../lib/useRowIntro'
import { countdown, fmtInterval, fmtNumber, fmtStamp, statusInfo, timeAgo, watchFilterSummary } from '../lib/format'
import { toast } from '../lib/toast'
import Icon from '../components/Icon.vue'
import PageHeader from '../components/PageHeader.vue'
import Skeleton from '../components/Skeleton.vue'
import StateBlock from '../components/StateBlock.vue'
import Toggle from '../components/Toggle.vue'
import WatchDrawer from '../components/WatchDrawer.vue'

const route = useRoute()
const router = useRouter()
const {
  data: watchList,
  loading: watchesLoading,
  error: watchesError,
  reload: reloadWatches,
} = useAsyncData<Watch[]>(() => getWatches())
const now = useNow(1000)

const drawerOpen = ref(false)
const editing = ref<Watch | null>(null)
const overrides = ref<Record<number, boolean>>({})
const busy = ref<Record<number, boolean>>({})
const confirmDelete = ref<number | null>(null)

const rows = computed(() => watchList.value ?? [])
const { fresh: freshRows, sync: syncRows } = useRowIntro()

watch(
  rows,
  (value) => syncRows(value.map((watch) => String(watch.id))),
  { immediate: true },
)

function openCreate(): void {
  editing.value = null
  drawerOpen.value = true
}

function openEdit(watch: Watch): void {
  editing.value = watch
  drawerOpen.value = true
}

function closeDrawer(): void {
  drawerOpen.value = false
}

function onSaved(saved: Watch): void {
  const wasEditing = editing.value !== null
  drawerOpen.value = false
  toast.success(wasEditing ? `已保存「${saved.name}」` : `已建好「${saved.name}」，下一轮自动扫`)
  editing.value = null
  void reloadWatches()
}

function isEnabled(watch: Watch): boolean {
  return overrides.value[watch.id] ?? watch.enabled
}

async function toggleEnabled(watch: Watch): Promise<void> {
  if (busy.value[watch.id]) return
  const next = !isEnabled(watch)
  overrides.value = { ...overrides.value, [watch.id]: next }
  busy.value = { ...busy.value, [watch.id]: true }
  try {
    await patchWatch(watch.id, { enabled: next })
    const nextOverrides = { ...overrides.value }
    delete nextOverrides[watch.id]
    overrides.value = nextOverrides
    await reloadWatches()
    toast.success(next ? `「${watch.name}」已开始盯` : `「${watch.name}」已暂停`)
  } catch (problem) {
    const nextOverrides = { ...overrides.value }
    delete nextOverrides[watch.id]
    overrides.value = nextOverrides
    toast.error(problem instanceof Error ? problem.message : '开关没保存上，再试一次。')
  } finally {
    const nextBusy = { ...busy.value }
    delete nextBusy[watch.id]
    busy.value = nextBusy
  }
}

async function startRun(watch: Watch): Promise<void> {
  busy.value = { ...busy.value, [watch.id]: true }
  try {
    await runWatch(watch.id)
    toast.success(`已触发「${watch.name}」，去「运行」页看日志`)
    window.setTimeout(() => void reloadWatches(), 4000)
  } catch (problem) {
    toast.error(problem instanceof Error ? problem.message : '没能触发这次运行。')
  } finally {
    const nextBusy = { ...busy.value }
    delete nextBusy[watch.id]
    busy.value = nextBusy
  }
}

async function removeWatch(watch: Watch): Promise<void> {
  busy.value = { ...busy.value, [watch.id]: true }
  try {
    await deleteWatch(watch.id)
    confirmDelete.value = null
    toast.success(`已删除「${watch.name}」，抓到的商品仍在商品库`)
    await reloadWatches()
  } catch (problem) {
    toast.error(problem instanceof Error ? problem.message : '删除没成功，再试一次。')
  } finally {
    const nextBusy = { ...busy.value }
    delete nextBusy[watch.id]
    busy.value = nextBusy
  }
}

onMounted(() => {
  if (route.query.new === '1') {
    openCreate()
    void router.replace({ path: '/watches' })
  }
})
</script>

<template>
  <div>
    <PageHeader title="关注" subtitle="每条关注按自己的间隔巡逻，只有过线的才推送。">
      <template #actions>
        <button type="button" class="btn btn-ghost" @click="reloadWatches()">
          <Icon name="refresh" :size="13" /> 刷新
        </button>
        <button type="button" class="btn btn-primary" @click="openCreate">
          <Icon name="plus" :size="13" /> 新建关注
        </button>
      </template>
    </PageHeader>

    <div v-if="watchesError && !watchList" class="pt-5">
      <StateBlock kind="error" title="关注列表没读出来" :description="watchesError">
        <button type="button" class="btn btn-ghost" @click="reloadWatches()">
          <Icon name="refresh" :size="13" /> 重试
        </button>
      </StateBlock>
    </div>

    <div v-else-if="watchesLoading && !watchList" class="surface-card mt-4 p-4">
      <div v-for="index in 4" :key="index" class="flex items-center gap-5 border-b border-line/70 py-4 last:border-b-0">
        <div class="w-44 space-y-1.5">
          <Skeleton width="70%" height="0.8rem" />
          <Skeleton width="45%" height="0.6rem" />
        </div>
        <Skeleton width="7rem" height="0.75rem" />
        <Skeleton width="30%" height="0.75rem" />
        <Skeleton width="3rem" height="0.75rem" />
        <Skeleton width="2rem" height="0.75rem" />
      </div>
    </div>

    <StateBlock
      v-else-if="rows.length === 0"
      title="还没有关注"
      description="先建一个关键词，点「试抓一次」看看能抓到什么、中位价多少，觉得词对了再保存。之后它会按你设的间隔自己跑。"
      class="mt-4"
    >
      <button type="button" class="btn btn-primary" @click="openCreate">
        <Icon name="plus" :size="13" /> 建第一个关注
      </button>
      <button type="button" class="btn btn-ghost" @click="router.push('/settings')">先登录闲鱼账号</button>
    </StateBlock>

    <template v-else>
      <div class="surface-card mt-4 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[1020px] table-fixed border-collapse">
            <colgroup>
              <col style="width: 180px" />
              <col style="width: 140px" />
              <col style="width: 238px" />
              <col style="width: 92px" />
              <col style="width: 70px" />
              <col style="width: 120px" />
              <col style="width: 104px" />
              <col style="width: 142px" />
            </colgroup>
            <thead>
              <tr class="border-b border-line text-left">
                <th class="px-4 py-2.5"><span class="label-xs">名称</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">关键词</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">筛选摘要</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">间隔</span></th>
                <th class="px-1 py-2.5 text-right"><span class="label-xs">商品数</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">上次运行</span></th>
                <th class="px-3 py-2.5"><span class="label-xs">状态</span></th>
                <th class="px-4 py-2.5 text-right"><span class="label-xs">操作</span></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(watch, index) in rows"
                :key="watch.id"
                class="group border-b border-line/70 transition-[background-color,box-shadow] duration-150 last:border-b-0 hover:bg-paper-2 hover:shadow-[inset_2px_0_0_#FF5A3C]"
                :class="{ 'row-in': freshRows.has(String(watch.id)) }"
                :style="
                  freshRows.has(String(watch.id))
                    ? { animationDelay: `${Math.min(index, 8) * 16}ms` }
                    : undefined
                "
              >
                <td class="px-4 py-3.5 align-middle">
                  <p class="truncate text-[13px] font-medium tracking-[-0.01em] text-ink" :title="watch.name">
                    {{ watch.name }}
                  </p>
                  <p class="mt-1 truncate text-[10px] text-muted" :title="watch.note || fmtStamp(watch.created_at)">
                    {{ watch.note || `建于 ${fmtStamp(watch.created_at)}` }}
                  </p>
                </td>
                <td class="px-3 py-3.5 align-middle">
                  <span class="block truncate font-mono text-[11px] text-ink-2" :title="watch.keyword">
                    {{ watch.keyword }}
                  </span>
                </td>
                <td class="px-3 py-3.5 align-middle">
                  <span class="block truncate text-[10.5px] leading-relaxed text-ink-2" :title="watchFilterSummary(watch)">
                    {{ watchFilterSummary(watch) }}
                  </span>
                </td>
                <td class="px-3 py-3.5 align-middle">
                  <p class="num text-[11.5px] text-ink">{{ fmtInterval(watch.interval_sec) }}</p>
                  <p
                    class="num mt-1 text-[10px]"
                    :class="countdown(watch.next_run_at, now).seconds < 120 ? 'text-red' : 'text-muted'"
                  >
                    {{ countdown(watch.next_run_at, now).text }}
                  </p>
                </td>
                <td class="px-1 py-3.5 text-right align-middle">
                  <RouterLink
                    :to="`/items?watch=${watch.id}`"
                    class="num text-[12px] text-ink-2 transition-colors hover:text-ink"
                  >
                    {{ fmtNumber(watch.item_count ?? 0) }}
                  </RouterLink>
                </td>
                <td class="px-3 py-3.5 align-middle">
                  <p class="truncate text-[11px] text-ink-2" :title="fmtStamp(watch.last_run_at)">
                    {{ watch.last_run_at ? timeAgo(watch.last_run_at, now) : '还没跑过' }}
                  </p>
                  <span
                    v-if="watch.last_run"
                    class="mt-1 inline-block text-[10px]"
                    :class="{
                      'text-jade': statusInfo(watch.last_run?.status).tone === 'jade',
                      'text-ochre': statusInfo(watch.last_run?.status).tone === 'ochre',
                      'text-red': statusInfo(watch.last_run?.status).tone === 'red',
                      'text-muted': statusInfo(watch.last_run?.status).tone === 'muted',
                    }"
                  >
                    {{ statusInfo(watch.last_run?.status).label }}
                  </span>
                </td>
                <td class="px-3 py-3.5 align-middle">
                  <div class="flex items-center gap-2">
                    <Toggle
                      :model-value="isEnabled(watch)"
                      :label="`启用或暂停 ${watch.name}`"
                      :disabled="busy[watch.id]"
                      @update:model-value="toggleEnabled(watch)"
                    />
                    <span class="text-[10.5px]" :class="isEnabled(watch) ? 'text-jade' : 'text-muted'">
                      {{ isEnabled(watch) ? '在跑' : '停' }}
                    </span>
                  </div>
                </td>
                <td class="px-4 py-3.5 align-middle">
                  <div
                    class="flex items-center justify-end gap-1"
                    :class="confirmDelete === watch.id ? 'opacity-100' : 'opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100 max-md:opacity-100'"
                  >
                    <template v-if="confirmDelete === watch.id">
                      <button
                        type="button"
                        class="btn btn-danger btn-sm rounded-full"
                        :disabled="busy[watch.id]"
                        @click="removeWatch(watch)"
                      >
                        删除
                      </button>
                      <button type="button" class="btn btn-quiet btn-sm rounded-full" @click="confirmDelete = null">
                        取消
                      </button>
                    </template>
                    <template v-else>
                      <button
                        type="button"
                        class="iconbtn h-8 w-8"
                        :disabled="busy[watch.id]"
                        title="立即运行一次"
                        :aria-label="`立即运行 ${watch.name}`"
                        @click="startRun(watch)"
                      >
                        <Icon name="play" :size="13" />
                      </button>
                      <button
                        type="button"
                        class="iconbtn h-8 w-8"
                        title="编辑关注"
                        :aria-label="`编辑 ${watch.name}`"
                        @click="openEdit(watch)"
                      >
                        <Icon name="pencil" :size="13" />
                      </button>
                      <button
                        type="button"
                        class="iconbtn h-8 w-8"
                        title="删除关注"
                        :aria-label="`删除 ${watch.name}`"
                        @click="confirmDelete = watch.id"
                      >
                        <Icon name="trash" :size="13" />
                      </button>
                    </template>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex items-center justify-between border-t border-line px-4 py-3 text-[10.5px] text-muted">
          <span>共 {{ rows.length }} 条关注，{{ rows.filter((item) => isEnabled(item)).length }} 条在跑。</span>
          <span>按创建顺序排列</span>
        </div>
      </div>
    </template>

    <WatchDrawer :open="drawerOpen" :watch="editing" @close="closeDrawer" @saved="onSaved" />
  </div>
</template>
