<script setup lang="ts">
const props = defineProps<{ modelValue: boolean; disabled?: boolean; label?: string }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: boolean): void }>()

function toggle(): void {
  if (props.disabled) return
  emit('update:modelValue', !props.modelValue)
}
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="label"
    :disabled="disabled"
    class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors duration-200 disabled:opacity-40"
    :class="modelValue ? 'border-jade/50 bg-jade/90' : 'border-line bg-[#ded7ca]'"
    @click="toggle"
  >
    <span
      class="block h-3.5 w-3.5 rounded-full transition-transform duration-[180ms] ease-[cubic-bezier(.2,.8,.2,1)]"
      :class="
        modelValue
          ? 'translate-x-[18px] bg-white'
          : 'translate-x-[3px] bg-white'
      "
    ></span>
  </button>
</template>
