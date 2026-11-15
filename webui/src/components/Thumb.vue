<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from './Icon.vue'

const props = withDefaults(
  defineProps<{
    src?: string | null
    alt?: string
    sizeClass?: string
    iconSize?: number
  }>(),
  { src: null, alt: '', sizeClass: 'h-14 w-14', iconSize: 16 },
)

const failed = ref(false)
watch(
  () => props.src,
  () => {
    failed.value = false
  },
)
</script>

<template>
  <div
    class="relative flex shrink-0 items-center justify-center overflow-hidden rounded-[10px] border border-line bg-paper-2"
    :class="sizeClass"
  >
    <img
      v-if="src && !failed"
      :src="src"
      :alt="alt"
      loading="lazy"
      referrerpolicy="no-referrer"
      class="h-full w-full object-cover"
      @error="failed = true"
    />
    <Icon v-else name="image" :size="iconSize" class="text-grey" />
  </div>
</template>
