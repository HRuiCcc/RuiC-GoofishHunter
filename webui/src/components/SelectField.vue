<script setup lang="ts">
import Icon from './Icon.vue'

withDefaults(
  defineProps<{
    modelValue: string
    options: Array<{ value: string; label: string }>
    ariaLabel?: string
    disabled?: boolean
    small?: boolean
  }>(),
  { ariaLabel: '', disabled: false, small: false },
)

const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()

function onChange(event: Event): void {
  emit('update:modelValue', (event.target as HTMLSelectElement).value)
}
</script>

<template>
  <span class="relative block">
    <select
      :value="modelValue"
      :aria-label="ariaLabel || undefined"
      :disabled="disabled"
      class="field appearance-none pr-8"
      :class="small ? 'h-8 text-[12px]' : ''"
      @change="onChange"
    >
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
    <Icon
      name="chevronDown"
      :size="13"
      class="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
    />
  </span>
</template>
