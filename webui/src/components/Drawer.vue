<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './Icon.vue'

const props = defineProps<{ open: boolean; title: string; subtitle?: string }>()
const emit = defineEmits<{ (event: 'close'): void }>()

const panel = ref<HTMLElement | null>(null)

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}

watch(
  () => props.open,
  async (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
    document.body.classList.toggle('drawer-open', open)
    if (open) {
      window.addEventListener('keydown', onKey)
      await nextTick()
      panel.value?.focus()
    } else {
      window.removeEventListener('keydown', onKey)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.body.style.overflow = ''
  document.body.classList.remove('drawer-open')
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-40">
      <div
        class="drawer-scrim absolute inset-0 bg-black/60 backdrop-blur-[6px]"
        @click="emit('close')"
      ></div>
      <section
        ref="panel"
        tabindex="-1"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        class="drawer-panel absolute bottom-3 right-3 top-3 flex w-[520px] max-w-[calc(100vw-24px)] flex-col overflow-hidden rounded-[14px] border border-line bg-raise shadow-float outline-none max-sm:bottom-0 max-sm:right-0 max-sm:top-0 max-sm:max-w-full max-sm:rounded-none max-sm:border-0"
      >
        <header class="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div class="min-w-0">
            <h2 class="text-[17px] font-semibold leading-snug tracking-[-0.02em] text-ink">{{ title }}</h2>
            <p v-if="subtitle" class="mt-1 truncate font-mono text-[10px] text-muted">{{ subtitle }}</p>
          </div>
          <button type="button" class="iconbtn -mr-1" aria-label="关闭详情" @click="emit('close')">
            <Icon name="close" :size="16" />
          </button>
        </header>
        <div class="min-h-0 flex-1 overflow-y-auto">
          <slot />
        </div>
        <footer v-if="$slots.footer" class="border-t border-line bg-raise px-6 py-3.5">
          <slot name="footer" />
        </footer>
      </section>
    </div>
  </Teleport>
</template>
