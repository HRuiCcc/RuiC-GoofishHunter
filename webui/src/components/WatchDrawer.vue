<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import {
  createWatch,
  patchWatch,
  previewWatch,
  type PreviewItem,
  type PreviewResult,
  type Watch,
  type WatchInput,
} from '../api'
import { errorMessage } from '../lib/useAsync'
import { fmtMoney, scanPerDay, sortLabel } from '../lib/format'
import Drawer from './Drawer.vue'
import FormField from './FormField.vue'
import Icon from './Icon.vue'
import InlineNote from './InlineNote.vue'
import SelectField from './SelectField.vue'
import Skeleton from './Skeleton.vue'
import Thumb from './Thumb.vue'
import Toggle from './Toggle.vue'

const props = defineProps<{ open: boolean; watch: Watch | null }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'saved', watch: Watch): void }>()

const form = reactive({
  name: '',
  keyword: '',
  sort: 'newest',
  pages: '2',
  min_price: '',
  max_price: '',
  min_score: '60',
  interval_min: '5',
  personal_only: true,
  free_shipping: true,
  use_llm: true,
  notify: true,
  note: '',
})

const errors = ref<Record<string, string>>({})
const saving = ref(false)
const saveError = ref<string | null>(null)

const preview = ref<PreviewResult | null>(null)
const previewing = ref(false)
const previewError = ref<string | null>(null)
const previewKeyword = ref('')
const previewSection = ref<HTMLElement | null>(null)

const title = computed(() => (props.watch ? '编辑关注' : '新建关注'))
const subtitle = computed(() =>
  props.watch ? props.watch.keyword : '先试抓一次，看看能不能捡到东西，再决定要不要存',
)

const sortOptions = [
  { value: 'newest', label: '最新发布' },
  { value: 'price_asc', label: '价格从低到高' },
  { value: 'price_desc', label: '价格从高到低' },
  { value: 'default', label: '综合排序' },
]

const intervalPreview = computed(() => scanPerDay((Number(form.interval_min) || 0) * 60))

const stalePreview = computed(
  () => preview.value !== null && previewKeyword.value !== form.keyword.trim(),
)

function resetForm(): void {
  const watch = props.watch
  form.name = watch?.name ?? ''
  form.keyword = watch?.keyword ?? ''
  form.sort = watch?.sort ?? 'newest'
  form.pages = String(watch?.pages ?? 2)
  form.min_price = watch?.min_price !== null && watch?.min_price !== undefined ? String(watch.min_price) : ''
  form.max_price = watch?.max_price !== null && watch?.max_price !== undefined ? String(watch.max_price) : ''
  form.min_score = String(watch?.min_score ?? 60)
  form.interval_min = String(Math.round((watch?.interval_sec ?? 300) / 60))
  form.personal_only = watch?.personal_only ?? true
  form.free_shipping = watch?.free_shipping ?? true
  form.use_llm = watch?.use_llm ?? true
  form.notify = watch?.notify ?? true
  form.note = watch?.note ?? ''
  errors.value = {}
  saveError.value = null
  preview.value = null
  previewError.value = null
  previewKeyword.value = ''
  previewing.value = false
}

watch(
  () => [props.open, props.watch] as const,
  ([open]) => {
    if (open) resetForm()
  },
  { immediate: true },
)

function numeric(text: string): number | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

function buildPayload(): WatchInput {
  const pages = Math.min(10, Math.max(1, Math.round(numeric(form.pages) ?? 2)))
  const intervalMin = Math.min(1440, Math.max(1, numeric(form.interval_min) ?? 5))
  return {
    name: form.name.trim(),
    keyword: form.keyword.trim(),
    sort: form.sort,
    pages,
    personal_only: form.personal_only,
    free_shipping: form.free_shipping,
    min_price: numeric(form.min_price),
    max_price: numeric(form.max_price),
    min_score: Math.min(100, Math.max(0, Math.round(numeric(form.min_score) ?? 60))),
    interval_sec: Math.round(intervalMin * 60),
    use_llm: form.use_llm,
    notify: form.notify,
    note: form.note.trim(),
  }
}

function validate(): Record<string, string> {
  const found: Record<string, string> = {}
  if (!form.name.trim()) found.name = '给这条关注起个名字，回看时好认'
  if (!form.keyword.trim()) found.keyword = '关键词不能为空，照闲鱼搜索框里那样写'
  const pages = numeric(form.pages)
  if (pages === null || pages < 1 || pages > 10) found.pages = '页数填 1 到 10'
  const interval = numeric(form.interval_min)
  if (interval === null || interval < 1 || interval > 1440) found.interval_min = '间隔填 1 到 1440 分钟'
  const score = numeric(form.min_score)
  if (score === null || score < 0 || score > 100) found.min_score = '门槛填 0 到 100'
  const minPrice = numeric(form.min_price)
  const maxPrice = numeric(form.max_price)
  if (minPrice !== null && minPrice < 0) found.min_price = '价格不能是负数'
  if (maxPrice !== null && maxPrice < 0) found.max_price = '价格不能是负数'
  if (minPrice !== null && maxPrice !== null && minPrice >= maxPrice) found.max_price = '最高价要大于最低价'
  return found
}

async function runPreview(): Promise<void> {
  const keyword = form.keyword.trim()
  if (!keyword) {
    errors.value = { ...errors.value, keyword: '先填关键词，才能试抓' }
    return
  }
  previewing.value = true
  previewError.value = null
  try {
    const payload = buildPayload()
    preview.value = await previewWatch({ ...payload, name: payload.name || keyword, pages: 1 })
    previewKeyword.value = keyword
    await nextTick()
    previewSection.value?.scrollIntoView({ block: 'start' })
  } catch (problem) {
    preview.value = null
    previewError.value = errorMessage(problem)
  } finally {
    previewing.value = false
  }
}

async function save(): Promise<void> {
  const found = validate()
  errors.value = found
  if (Object.keys(found).length > 0) return
  saving.value = true
  saveError.value = null
  try {
    const payload = buildPayload()
    const saved = props.watch ? await patchWatch(props.watch.id, payload) : await createWatch(payload)
    emit('saved', saved)
  } catch (problem) {
    saveError.value = errorMessage(problem)
  } finally {
    saving.value = false
  }
}

function samplePic(sample: PreviewItem): string {
  return sample.pic || sample.pics?.[0] || ''
}

const scorePresets = [50, 60, 70, 80]
</script>

<template>
  <Drawer :open="open" :title="title" :subtitle="subtitle" @close="emit('close')">
    <div class="px-6 py-5">
      <InlineNote v-if="saveError" tone="error" class="mb-4">{{ saveError }}</InlineNote>

      <div class="grid grid-cols-2 gap-x-4 gap-y-4">
        <div class="col-span-2">
          <FormField label="名称" :error="errors.name">
            <input v-model="form.name" class="field" placeholder="比如：vivo X200 Pro 16+512" />
          </FormField>
        </div>

        <div class="col-span-2">
          <FormField label="关键词" hint="照闲鱼搜索框里那样写" :error="errors.keyword">
            <input
              v-model="form.keyword"
              class="field font-mono"
              placeholder="vivo x200 pro"
              autocomplete="off"
            />
          </FormField>
        </div>

        <FormField label="排序">
          <SelectField v-model="form.sort" :options="sortOptions" aria-label="搜索排序" />
        </FormField>

        <FormField label="抓几页" hint="每页 30 条" :error="errors.pages">
          <input v-model="form.pages" type="number" min="1" max="10" class="field num" />
        </FormField>

        <FormField label="最低价" hint="留空不限">
          <input v-model="form.min_price" type="number" min="0" class="field num" placeholder="不限" />
        </FormField>

        <FormField label="最高价" :error="errors.max_price">
          <input v-model="form.max_price" type="number" min="0" class="field num" placeholder="不限" />
        </FormField>

        <FormField label="间隔（分钟）" :help="intervalPreview" :error="errors.interval_min">
          <input v-model="form.interval_min" type="number" min="1" max="1440" class="field num" />
        </FormField>

        <div>
          <span class="mb-1.5 flex items-baseline justify-between gap-2">
            <span class="text-[11.5px] leading-none text-ink-2">推送门槛</span>
            <span class="text-[10px] leading-none text-muted">低于这个分不推</span>
          </span>
          <input v-model="form.min_score" type="number" min="0" max="100" class="field num" />
          <div class="mt-1.5 flex gap-1">
            <button
              v-for="preset in scorePresets"
              :key="preset"
              type="button"
              class="num border px-1.5 py-0.5 text-[10px] leading-none"
              :class="
                form.min_score === String(preset)
                  ? 'border-ink bg-ink text-paper'
                  : 'border-line text-ink-2 hover:bg-paper-2'
              "
              @click="form.min_score = String(preset)"
            >
              {{ preset }}
            </button>
          </div>
          <span v-if="errors.min_score" class="mt-1 block text-[11px] text-red">{{ errors.min_score }}</span>
        </div>

        <div class="col-span-2 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line pt-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-[12px] text-ink">只看个人闲置</p>
              <p class="mt-0.5 text-[10.5px] text-muted">挡掉商家和批量货</p>
            </div>
            <Toggle v-model="form.personal_only" label="只看个人闲置" />
          </div>
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-[12px] text-ink">只看包邮</p>
              <p class="mt-0.5 text-[10.5px] text-muted">省一笔运费</p>
            </div>
            <Toggle v-model="form.free_shipping" label="只看包邮" />
          </div>
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-[12px] text-ink">AI 复核</p>
              <p class="mt-0.5 text-[10.5px] text-muted">过线的再让 AI 看一眼坑</p>
            </div>
            <Toggle v-model="form.use_llm" label="AI 复核" />
          </div>
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-[12px] text-ink">推送通知</p>
              <p class="mt-0.5 text-[10.5px] text-muted">过线后发到手机</p>
            </div>
            <Toggle v-model="form.notify" label="推送通知" />
          </div>
        </div>

        <div class="col-span-2">
          <FormField label="备注" hint="可留空">
            <textarea
              v-model="form.note"
              class="field field-area"
              rows="2"
              placeholder="比如：只收 512G、不要拆修的"
            ></textarea>
          </FormField>
        </div>
      </div>

      <section ref="previewSection" class="mt-6 border-t border-line pt-5">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-[14.5px] font-semibold tracking-[-0.01em] text-ink">试抓 · 先尝后买</h3>
            <p class="mt-1 text-[11.5px] leading-relaxed text-ink-2">
              抓第 1 页的真实结果，看条数、中位价和 6 条样例，不写进商品库。
            </p>
          </div>
          <button type="button" class="btn btn-ghost shrink-0" :disabled="previewing" @click="runPreview">
            <Icon :name="previewing ? 'clock' : 'search'" :size="13" />
            {{ previewing ? '正在抓…' : preview ? '再试一次' : '试抓一次' }}
          </button>
        </div>

        <div v-if="previewing" class="mt-4 rounded-[10px] border border-line bg-paper-2 p-4">
          <div class="grid grid-cols-4 gap-3">
            <Skeleton v-for="index in 4" :key="index" height="2.2rem" />
          </div>
          <div class="mt-4 space-y-3">
            <div v-for="index in 3" :key="index" class="flex items-center gap-3">
              <Skeleton width="2.25rem" height="2.25rem" />
              <div class="flex-1 space-y-1.5">
                <Skeleton width="80%" height="0.7rem" />
                <Skeleton width="40%" height="0.6rem" />
              </div>
            </div>
          </div>
          <p class="mt-4 text-[10.5px] text-muted">正在打开闲鱼搜索页，通常要 10 到 30 秒。</p>
        </div>

        <div v-else-if="previewError" class="mt-4">
          <InlineNote tone="error">{{ previewError }}</InlineNote>
          <button type="button" class="btn btn-ghost btn-sm mt-2" @click="runPreview">
            <Icon name="refresh" :size="12" /> 重试
          </button>
        </div>

        <div v-else-if="preview" class="mt-4 overflow-hidden rounded-[10px] border border-line bg-paper-2">
          <div class="grid grid-cols-4 divide-x divide-line border-b border-line">
            <div class="px-3 py-2.5">
              <p class="text-[10px] text-muted">抓到</p>
              <p class="num mt-1 text-[17px] leading-none text-ink">
                {{ preview.count }}<span class="ml-0.5 text-[10px] text-muted">条</span>
              </p>
            </div>
            <div class="px-3 py-2.5">
              <p class="text-[10px] text-muted">中位价</p>
              <p class="num mt-1 text-[17px] leading-none text-ink">{{ fmtMoney(preview.median) }}</p>
            </div>
            <div class="px-3 py-2.5">
              <p class="text-[10px] text-muted">最低</p>
              <p class="num mt-1 text-[17px] leading-none text-jade">{{ fmtMoney(preview.minimum) }}</p>
            </div>
            <div class="px-3 py-2.5">
              <p class="text-[10px] text-muted">最高</p>
              <p class="num mt-1 text-[17px] leading-none text-ink">{{ fmtMoney(preview.maximum) }}</p>
            </div>
          </div>

          <p class="truncate border-b border-line px-3 py-2 font-mono text-[10px] text-muted" :title="preview.filter">
            筛选 {{ preview.filter || '无额外筛选' }}
          </p>

          <ul v-if="preview.items.length" class="divide-y divide-line">
            <li
              v-for="sample in preview.items.slice(0, 6)"
              :key="sample.item_id"
              class="flex items-center gap-3 px-3 py-2"
            >
              <Thumb :src="samplePic(sample)" size-class="h-9 w-9" :icon-size="12" />
              <div class="min-w-0 flex-1">
                <p class="truncate text-[12px] leading-snug text-ink">{{ sample.title }}</p>
                <p class="mt-0.5 truncate text-[10px] text-muted">
                  {{ sample.area || '地区未知' }}
                  <span v-if="sample.seller_nick"> · {{ sample.seller_nick }}</span>
                </p>
              </div>
              <span class="num shrink-0 text-[12px] text-ink">{{ fmtMoney(sample.price) }}</span>
            </li>
          </ul>

          <p v-else class="px-4 py-6 text-[12px] leading-relaxed text-ink-2">
            这一组词没抓到东西：把词改短一点，只留型号；或者关掉「个人闲置 / 包邮」再试。
          </p>

          <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2">
            <span class="text-[10px] text-muted">样例为第 1 页真实结果，未写入商品库。</span>
            <span class="num text-[10px] text-muted">{{ sortLabel(form.sort) }}</span>
          </div>
        </div>

        <p v-else class="mt-3 text-[11.5px] leading-relaxed text-muted">
          还没有试抓。填好关键词，点「试抓一次」：先看中位价和 6 条样例，觉得词对了再保存。
        </p>

        <div v-if="stalePreview" class="mt-2">
          <InlineNote tone="info">关键词改过了，上面还是上一次的样例。再试抓一次更准。</InlineNote>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="flex items-center justify-between gap-3">
        <button type="button" class="btn btn-quiet" @click="emit('close')">取消</button>
        <button type="button" class="btn btn-primary" :disabled="saving" @click="save">
          <Icon name="check" :size="13" />
          {{ saving ? '保存中…' : props.watch ? '保存修改' : '建好，开始盯' }}
        </button>
      </div>
    </template>
  </Drawer>
</template>
