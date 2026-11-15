<script setup lang="ts">
import { computed } from 'vue'

export interface ChartPoint {
  label: string
  value: number | null
  volume?: number | null
}

const props = withDefaults(
  defineProps<{
    points: ChartPoint[]
    height?: number
    showAxis?: boolean
    showVolume?: boolean
    ariaLabel?: string
    lineColor?: string
    areaColor?: string
    gridColor?: string
    textColor?: string
    dotColor?: string
    accentColor?: string
    volumeColor?: string
  }>(),
  {
    height: 140,
    showAxis: true,
    showVolume: false,
    ariaLabel: '价格走势',
    lineColor: '#F2F0EC',
    areaColor: 'rgba(242,240,236,0.05)',
    gridColor: '#E5DFD3',
    textColor: '#8C8880',
    dotColor: '#F7F5F0',
    accentColor: '#FF5A3C',
    volumeColor: 'rgba(242,240,236,0.16)',
  },
)

const W = 320

const padL = computed(() => (props.showAxis ? 36 : 3))
const padT = 8
const padB = computed(() => (props.showAxis ? 16 : 3) + (props.showVolume ? 9 : 0))
const plotH = computed(() => Math.max(10, props.height - padT - padB.value))

const bounds = computed(() => {
  const values = props.points
    .map((point) => point.value)
    .filter((value): value is number => value !== null && Number.isFinite(value))
  if (values.length === 0) return { min: 0, max: 1 }
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (max === min) {
    const pad = Math.max(1, min * 0.02)
    max = min + pad
    min = Math.max(0, min - pad)
  }
  return { min, max }
})

const hasData = computed(() =>
  props.points.some((point) => point.value !== null && Number.isFinite(point.value)),
)

const stepX = computed(() => {
  const n = props.points.length
  if (n <= 1) return 0
  return (W - padL.value - 6) / (n - 1)
})

function xAt(index: number): number {
  if (props.points.length <= 1) return padL.value + (W - padL.value - 6) / 2
  return padL.value + index * stepX.value
}

function yAt(value: number): number {
  const { min, max } = bounds.value
  return padT + (1 - (value - min) / (max - min)) * plotH.value
}

const coords = computed(() =>
  props.points.map((point, index) => ({
    label: point.label,
    value: point.value,
    volume: point.volume ?? 0,
    x: xAt(index),
    y: point.value === null || !Number.isFinite(point.value) ? null : yAt(point.value),
  })),
)

const solidPoints = computed(() =>
  coords.value.flatMap((point) => (point.y === null ? [] : [{ ...point, y: point.y }])),
)

const linePath = computed(() =>
  solidPoints.value
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(' '),
)

const areaPath = computed(() => {
  const points = solidPoints.value
  if (points.length < 2) return ''
  const baseline = (props.height - padB.value).toFixed(1)
  const first = points[0]
  const last = points[points.length - 1]
  return `${linePath.value} L${last.x.toFixed(1)},${baseline} L${first.x.toFixed(1)},${baseline} Z`
})

function axisNumber(value: number): string {
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(1)}万`
  return String(Math.round(value))
}

const yTicks = computed(() => {
  if (!props.showAxis || solidPoints.value.length === 0) return []
  const { min, max } = bounds.value
  return [max, (max + min) / 2, min].map((value) => ({ y: yAt(value), label: axisNumber(value) }))
})

const xLabels = computed(() => {
  if (!props.showAxis || props.points.length < 2) return []
  const last = props.points.length - 1
  const middle = Math.floor(last / 2)
  return [...new Set([0, middle, last])].map((index) => ({
    x: xAt(index),
    label: props.points[index].label,
    anchor: index === 0 ? 'start' : index === last ? 'end' : 'middle',
  }))
})

const volumeBars = computed(() => {
  if (!props.showVolume) return []
  const maxVolume = Math.max(1, ...props.points.map((point) => point.volume ?? 0))
  const base = props.height - padB.value
  return coords.value.map((point) => {
    const height = ((point.volume ?? 0) / maxVolume) * 8
    return { x: point.x, y: base - height, height }
  })
})

const lastPoint = computed(() => solidPoints.value[solidPoints.value.length - 1] ?? null)
</script>

<template>
  <svg
    :viewBox="`0 0 ${W} ${height}`"
    class="block w-full overflow-visible"
    role="img"
    :aria-label="ariaLabel"
  >
    <g v-if="hasData">
      <g aria-hidden="true">
        <line
          v-for="tick in yTicks"
          :key="`g-${tick.y}`"
          :x1="padL"
          :x2="W - 6"
          :y1="tick.y"
          :y2="tick.y"
          :stroke="gridColor"
          stroke-width="0.75"
        />
        <line
          :x1="padL"
          :x2="W - 6"
          :y1="height - padB"
          :y2="height - padB"
          :stroke="gridColor"
          stroke-width="0.75"
        />
      </g>

      <rect
        v-for="(bar, index) in volumeBars"
        :key="`v-${index}`"
        :x="bar.x - 1.5"
        :y="bar.y"
        width="3"
        :height="bar.height"
        :fill="volumeColor"
      />

      <path v-if="areaPath" :d="areaPath" :fill="areaColor" />
      <path
        :d="linePath"
        fill="none"
        :stroke="lineColor"
        stroke-width="1.5"
        stroke-linejoin="round"
        stroke-linecap="round"
      />

      <circle
        v-for="(point, index) in solidPoints"
        :key="`p-${index}`"
        :cx="point.x"
        :cy="point.y"
        r="1.6"
        :fill="dotColor"
        :stroke="lineColor"
        stroke-width="1"
        opacity="0.7"
      />

      <circle
        v-if="lastPoint"
        :cx="lastPoint.x"
        :cy="lastPoint.y"
        r="2.6"
        :fill="accentColor"
        :stroke="dotColor"
        stroke-width="1"
      />

      <text
        v-for="tick in yTicks"
        :key="`t-${tick.y}`"
        class="num"
        :x="padL - 5"
        :y="tick.y + 2.5"
        text-anchor="end"
        :fill="textColor"
        font-size="8"
      >
        {{ tick.label }}
      </text>

      <text
        v-for="(label, index) in xLabels"
        :key="`x-${index}`"
        class="num"
        :x="label.x"
        :y="height - 3"
        :text-anchor="label.anchor"
        :fill="textColor"
        font-size="8"
      >
        {{ label.label }}
      </text>
    </g>
  </svg>
</template>
