<script setup lang="ts">
import { dismissToast, toasts, type ToastTone } from '../lib/toast'
import Icon from './Icon.vue'

const bar: Record<ToastTone, string> = {
  success: 'bg-jade',
  error: 'bg-red',
  info: 'bg-ink-2',
}
</script>

<template>
  <Teleport to="body">
    <div
      class="toast-host pointer-events-none fixed bottom-5 right-5 z-[80] flex w-[min(92vw,340px)] flex-col gap-2"
      role="status"
      aria-live="polite"
    >
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast-item pointer-events-auto relative flex items-start gap-2 overflow-hidden rounded-[10px] border border-line bg-raise py-3 pl-4 pr-3 text-[12.5px] leading-snug text-ink shadow-float"
      >
        <span class="absolute inset-y-2.5 left-0 w-[2px] rounded-full" :class="bar[item.tone]" aria-hidden="true"></span>
        <p class="min-w-0 flex-1">{{ item.message }}</p>
        <button
          type="button"
          class="-mr-0.5 -mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-muted hover:bg-paper-2 hover:text-ink"
          aria-label="关闭提示"
          @click="dismissToast(item.id)"
        >
          <Icon name="close" :size="12" />
        </button>
      </div>
    </div>
  </Teleport>
</template>
