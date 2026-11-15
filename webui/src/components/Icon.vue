<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })

/** 全部手写，统一 stroke 1.5，不引图标库。 */
const paths: Record<string, string> = {
  ledger:
    '<path d="M7 4h12v16H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M7 4v16"/><path d="M10 8h6M10 12h6M10 16h4"/>',
  target:
    '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  box:
    '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9Z"/><path d="m3 7.5 9 4.5 9-4.5"/><path d="M12 12v9"/>',
  pulse: '<path d="M3 12h4l2.5-6 5 12L17 12h4"/>',
  sliders:
    '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  refresh: '<path d="M20 6v5h-5"/><path d="M20 11a8 8 0 1 0-2.4 6"/>',
  play: '<path d="M8 5.5v13l11-6.5-11-6.5Z"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="m13 7 4 4"/>',
  external:
    '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m4.5 12.5 5 5L20 6.5"/>',
  alert: '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5"/><path d="M12 17.2v.2"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.2l3.2 2"/>',
  scan:
    '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M20 8V5.5A1.5 1.5 0 0 0 18.5 4H16M4 16v2.5A1.5 1.5 0 0 0 5.5 20H8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16"/><path d="M8 12h8"/>',
  key: '<circle cx="8" cy="8" r="4"/><path d="m11 11 9 9M17 17l2-2M14.5 14.5l2-2"/>',
  download:
    '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/>',
  image:
    '<rect x="3.5" y="4.5" width="17" height="15" rx="1"/><circle cx="9" cy="10" r="1.6"/><path d="m5 17 5-5 4 4 2.5-2.5 2.5 2.5"/>',
  bell: '<path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  link:
    '<path d="M10 14a4 4 0 0 0 5.7 0l2.3-2.3a4 4 0 1 0-5.7-5.7L11 7.3"/><path d="M14 10a4 4 0 0 0-5.7 0L6 12.3a4 4 0 1 0 5.7 5.7l1.3-1.3"/>',
  arrowDown: '<path d="M12 4v16"/><path d="m6 14 6 6 6-6"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="1"/><path d="M15 5H5a1 1 0 0 0-1 1v10"/>',
  terminal: '<path d="M4 5h16v14H4z"/><path d="m8 10 2.5 2.5L8 15M13 15h4"/>',
  ban: '<circle cx="12" cy="12" r="8.5"/><path d="m6 6 12 12"/>',
  rows: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M9 4.5v15"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  loader: '<path d="M12 3a9 9 0 1 1-6.36 2.64"/>',
  arrowRight: '<path d="M4 12h15"/><path d="m13 6 6 6-6 6"/>',
  dot: '<circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/>',
}
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
    v-html="paths[name] ?? ''"
  />
</template>
