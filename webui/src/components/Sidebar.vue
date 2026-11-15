<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { getHealth } from '../api'
import { useAsyncData } from '../lib/useAsync'
import Icon from './Icon.vue'

const nav = [
  { to: '/', label: '概览', icon: 'ledger' },
  { to: '/watches', label: '关注', icon: 'target' },
  { to: '/items', label: '商品库', icon: 'box' },
  { to: '/runs', label: '运行', icon: 'pulse' },
  { to: '/settings', label: '设置', icon: 'sliders' },
]

const health = useAsyncData(() => getHealth())
const online = computed(() => health.data.value?.ok === true)
const version = computed(() => health.data.value?.version ?? '')
const dataDir = computed(() => {
  const dir = health.data.value?.data_dir ?? ''
  return dir.replace(/^\/Users\/[^/]+/, '~')
})

let timer = 0
onMounted(() => {
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void health.reload()
  }, 30000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <aside
    class="z-30 flex flex-col border-b border-line bg-paper lg:fixed lg:inset-y-0 lg:left-0 lg:w-[208px] lg:border-b-0 lg:border-r"
  >
    <div class="flex items-center gap-3 px-5 py-4 lg:pb-6 lg:pt-6">
      <div class="seal" aria-hidden="true">猎</div>
      <div class="min-w-0">
        <div class="text-[15px] font-semibold leading-none tracking-[-0.02em] text-ink">闲鱼猎手</div>
        <div class="mt-1.5 text-[10px] leading-none text-muted">二手捡漏决策台</div>
      </div>
    </div>

    <div class="mx-4 border-t border-line"></div>

    <nav class="flex gap-1 overflow-x-auto px-2.5 py-3 lg:flex-col lg:overflow-visible lg:px-3" aria-label="主导航">
      <RouterLink
        v-for="item in nav"
        :key="item.to"
        :to="item.to"
        custom
        v-slot="{ isActive, navigate, href }"
      >
        <a
          :href="href"
          :aria-current="isActive ? 'page' : undefined"
          class="group relative flex h-9 shrink-0 items-center gap-1.5 rounded-[10px] px-2 text-[11px] transition-colors duration-[180ms] lg:gap-2.5 lg:px-3 lg:text-[12.5px]"
          :class="
            isActive
              ? 'bg-paper-2 text-ink'
              : 'text-ink-2 hover:bg-paper-2/60 hover:text-ink'
          "
          @click="navigate"
        >
          <span
            v-if="isActive"
            class="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-red"
            aria-hidden="true"
          ></span>
          <Icon
            :name="item.icon"
            :size="16"
            class="transition-colors duration-[180ms]"
            :class="isActive ? 'text-red' : 'text-grey group-hover:text-ink-2'"
          />
          <span>{{ item.label }}</span>
        </a>
      </RouterLink>
    </nav>

    <div class="mt-auto hidden px-5 pb-5 lg:block">
      <div class="rounded-[10px] border border-line bg-surface px-3 py-2.5">
        <div class="flex items-center gap-2 text-[10.5px] text-ink-2">
          <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="online ? 'bg-jade' : 'bg-red'" aria-hidden="true"></span>
          <span>{{ online ? '服务在线' : '后端未响应' }}</span>
          <span v-if="version" class="num ml-auto text-[10px] text-muted">v{{ version }}</span>
        </div>
        <p class="mt-1.5 truncate text-[10px] leading-4 text-muted" :title="health.data.value?.data_dir ?? ''">
          {{ online ? dataDir : '先启动 hunter（127.0.0.1:7801）' }}
        </p>
      </div>
    </div>
  </aside>
</template>
