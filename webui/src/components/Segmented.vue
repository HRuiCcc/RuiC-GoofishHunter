<script setup lang="ts">
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps<{
  modelValue: string
  options: Array<{ value: string; label: string; icon?: string }>
  ariaLabel?: string
}>()

const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()

const index = computed(() => Math.max(0, props.options.findIndex((option) => option.value === props.modelValue)))
</script>

<template>
  <div
    class="relative inline-flex rounded-full border border-line bg-paper-2 p-1"
    role="group"
    :aria-label="ariaLabel"
  >
    <span
      class="absolute bottom-1 top-1 rounded-full bg-surface shadow-card transition-transform duration-[220ms] ease-[cubic-bezier(.2,.8,.2,1)]"
      :style="{
        left: '4px',
        width: `calc((100% - 8px) / ${options.length})`,
        transform: `translateX(${index * 100}%)`,
      }"
      aria-hidden="true"
    ></span>
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="relative z-10 flex h-7 min-w-[62px] items-center justify-center gap-1.5 rounded-full px-3 text-[11.5px] transition-colors duration-200"
      :class="modelValue === option.value ? 'text-ink' : 'text-muted hover:text-ink-2'"
      :aria-pressed="modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
    >
      <Icon v-if="option.icon" :name="option.icon" :size="13" />
      {{ option.label }}
    </button>
  </div>
</template>
