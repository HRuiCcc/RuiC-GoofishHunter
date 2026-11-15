<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  getAccounts,
  getLoginStatus,
  getSettings,
  importLogin,
  putSettings,
  startLogin,
  type Account,
  type ImportResult,
  type SettingsResult,
} from '../api'
import { errorMessage, useAsyncData } from '../lib/useAsync'
import { accountStatusInfo, fmtStamp } from '../lib/format'
import { toast } from '../lib/toast'
import FormField from '../components/FormField.vue'
import Icon from '../components/Icon.vue'
import InlineNote from '../components/InlineNote.vue'
import PageHeader from '../components/PageHeader.vue'
import SelectField from '../components/SelectField.vue'
import Skeleton from '../components/Skeleton.vue'
import StateBlock from '../components/StateBlock.vue'
import Toggle from '../components/Toggle.vue'

const {
  data: settingsData,
  loading: settingsLoading,
  error: settingsError,
  reload: reloadSettings,
} = useAsyncData<SettingsResult>(() => getSettings())
const {
  data: accountList,
  loading: accountsLoading,
  error: accountsError,
  reload: reloadAccounts,
} = useAsyncData<Account[]>(() => getAccounts())

const form = reactive<Record<string, string>>({})
const channels = ref<string[]>([])
const hasLlmKey = ref(false)
const hasTelegramToken = ref(false)

const loginPhase = reactive<Record<string, { phase: 'idle' | 'waiting' | 'ok' | 'error'; message: string }>>({})
const newAccountName = ref('default')
const importAccount = ref('')
const importPath = ref('')
const importing = ref(false)
const importNote = ref<{ tone: 'ok' | 'error'; text: string } | null>(null)

const timers = new Set<number>()

function later(callback: () => void, delay: number): void {
  const id = window.setTimeout(() => {
    timers.delete(id)
    callback()
  }, delay)
  timers.add(id)
}

const defaults: Record<string, string> = {
  notify_channels: '',
  ntfy_url: '',
  bark_url: '',
  telegram_token: '',
  telegram_chat: '',
  webhook_url: '',
  wecom_url: '',
  quiet_hours: '23:30-08:00',
  llm_enabled: '1',
  llm_base_url: 'https://api.deepseek.com',
  llm_model: 'deepseek-flash',
  llm_top_n: '8',
  min_samples: '4',
}

watch(
  settingsData,
  (value) => {
    if (!value) return
    for (const key of Object.keys(defaults)) {
      const raw = (value as Record<string, unknown>)[key]
      form[key] = typeof raw === 'string' ? raw : defaults[key]
    }
    channels.value = (form.notify_channels || '')
      .split(',')
      .map((name) => name.trim())
      .filter(Boolean)
    hasLlmKey.value = value.has_llm_key === true
    hasTelegramToken.value = value.has_telegram_token === true
    form.llm_api_key = ''
    form.telegram_token = ''
  },
  { immediate: true },
)

watch(
  accountList,
  (list) => {
    if (!list || list.length === 0) {
      importAccount.value = ''
      return
    }
    if (!list.some((account) => account.name === importAccount.value)) {
      importAccount.value = list[0].name
    }
  },
  { immediate: true },
)

const accountOptions = computed(() => {
  const list = accountList.value ?? []
  if (list.length === 0) return [{ value: '', label: '先建一个账号' }]
  return list.map((account) => ({ value: account.name, label: account.name }))
})

const channelDefs = [
  { value: 'ntfy', label: 'ntfy', hint: '推到 ntfy 主题，手机即时收到' },
  { value: 'bark', label: 'Bark', hint: 'iPhone 通知，填 Bark 地址' },
  { value: 'telegram', label: 'Telegram', hint: '机器人 Token + Chat ID' },
  { value: 'wecom', label: '企业微信', hint: '群机器人 webhook 地址' },
  { value: 'webhook', label: 'Webhook', hint: '自定义地址，POST 一条消息' },
]

const noChannel = computed(() => channels.value.length === 0)
const quietHours = computed(() => form.quiet_hours || '23:30-08:00')

function toggleChannel(name: string): void {
  channels.value = channels.value.includes(name)
    ? channels.value.filter((channel) => channel !== name)
    : [...channels.value, name]
}

function chipClass(tone: string): string {
  if (tone === 'jade') return 'border-jade/50 text-jade'
  if (tone === 'red') return 'border-red/50 text-red'
  if (tone === 'ochre') return 'border-ochre/50 text-ochre'
  return 'border-line text-muted'
}

async function saveBlock(label: string, keys: string[], extra: Record<string, string> = {}): Promise<void> {
  const values: Record<string, string> = { ...extra }
  for (const key of keys) {
    const value = form[key] ?? ''
    if (key === 'llm_api_key' && !value.trim()) continue
    if (key === 'telegram_token' && !value.trim()) continue
    values[key] = value
  }
  try {
    await putSettings(values)
    await reloadSettings()
    toast.success(`${label}已保存`)
  } catch (problem) {
    toast.error(errorMessage(problem))
  }
}

function reloadAll(): void {
  void reloadSettings()
  void reloadAccounts()
}

function saveNotify(): Promise<void> {
  return saveBlock('通知设置', ['ntfy_url', 'bark_url', 'telegram_token', 'telegram_chat', 'wecom_url', 'webhook_url', 'quiet_hours'], {
    notify_channels: channels.value.join(','),
  })
}

function saveAi(): Promise<void> {
  return saveBlock('AI 设置', ['llm_enabled', 'llm_base_url', 'llm_model', 'llm_api_key', 'llm_top_n', 'min_samples'])
}

function setLlmEnabled(value: boolean): void {
  form.llm_enabled = value ? '1' : '0'
}

function phaseTone(phase: string): 'ok' | 'error' | 'info' {
  if (phase === 'ok') return 'ok'
  if (phase === 'error') return 'error'
  return 'info'
}

async function startAccountLogin(name: string): Promise<void> {
  const target = name.trim()
  if (!target) return
  loginPhase[target] = { phase: 'waiting', message: '正在打开登录窗口…' }
  try {
    const result = await startLogin(target)
    if (!result.started) {
      loginPhase[target] = { phase: 'waiting', message: result.reason || '已经有一个登录窗口在等扫码' }
    }
    await reloadAccounts()
    await pollLogin(target)
  } catch (problem) {
    loginPhase[target] = { phase: 'error', message: errorMessage(problem) }
  }
}

async function pollLogin(name: string, startedAt = Date.now()): Promise<void> {
  if (Date.now() - startedAt > 5 * 60 * 1000) {
    loginPhase[name] = { phase: 'error', message: '等了 5 分钟没等到登录。关掉浏览器窗口，再点一次「打开登录窗口」。' }
    return
  }
  try {
    const state = await getLoginStatus(name)
    if (state.pending) {
      loginPhase[name] = { phase: 'waiting', message: state.detail || '等待扫码' }
      later(() => void pollLogin(name, startedAt), 2500)
      return
    }
    if (state.logged_in) {
      loginPhase[name] = { phase: 'ok', message: '登录成功，登录态已保存到本机' }
      toast.success(`「${name}」登录成功，登录态已保存`)
      await reloadAccounts()
      return
    }
    loginPhase[name] = { phase: 'idle', message: state.detail || '还没登录，再扫码一次' }
    await reloadAccounts()
  } catch (problem) {
    loginPhase[name] = { phase: 'error', message: errorMessage(problem) }
  }
}

async function doImport(): Promise<void> {
  const name = importAccount.value
  const path = importPath.value.trim()
  if (!name || !path) return
  importing.value = true
  importNote.value = null
  try {
    const result: ImportResult = await importLogin(name, path)
    importNote.value = {
      tone: result.logged_in ? 'ok' : 'error',
      text: result.logged_in
        ? `导入了 ${result.imported} 条 cookie，校验通过`
        : `导入了 ${result.imported} 条 cookie，但校验没过：${result.detail || '仍然不是登录状态'}`,
    }
    if (result.logged_in) toast.success('旧登录态已导入，校验通过')
    else toast.error('登录态导入了，但校验没过')
    await reloadAccounts()
  } catch (problem) {
    importNote.value = { tone: 'error', text: errorMessage(problem) }
  } finally {
    importing.value = false
  }
}

onBeforeUnmount(() => {
  for (const id of timers) window.clearTimeout(id)
  timers.clear()
})
</script>

<template>
  <div class="max-w-[1040px]">
    <PageHeader title="设置" subtitle="账号、通知、AI 与阈值。所有内容都只写进本机数据库。">
      <template #actions>
        <button type="button" class="btn btn-ghost" @click="reloadAll">
          <Icon name="refresh" :size="13" /> 重新读取
        </button>
      </template>
    </PageHeader>

    <div v-if="settingsLoading && !settingsData" class="mt-6 space-y-5">
      <div v-for="index in 3" :key="index" class="space-y-3 border-b border-line pb-6">
        <Skeleton width="8rem" height="1rem" />
        <Skeleton width="60%" height="0.7rem" />
        <Skeleton width="100%" height="2.25rem" />
        <Skeleton width="70%" height="0.7rem" />
      </div>
    </div>

    <StateBlock
      v-else-if="settingsError && !settingsData"
      kind="error"
      title="设置没读出来"
      :description="settingsError"
      class="mt-5"
    >
      <button type="button" class="btn btn-ghost" @click="reloadSettings()">重试</button>
    </StateBlock>

    <template v-else>
      <section class="surface-card mt-4 p-5 lg:p-6">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="font-display text-[17px] font-semibold text-ink">闲鱼账号</h2>
            <p class="mt-1 text-[11.5px] leading-relaxed text-ink-2">
              扫码一次，登录态存在本机的 profile 目录里。失效了再点一次就行。
            </p>
          </div>
        </div>

        <div v-if="accountsLoading && !accountList" class="mt-4 space-y-3">
          <Skeleton width="100%" height="3rem" />
          <Skeleton width="100%" height="3rem" />
        </div>

        <StateBlock
          v-else-if="accountsError && !accountList"
          kind="error"
          title="账号列表没读出来"
          :description="accountsError"
          class="mt-4"
        >
          <button type="button" class="btn btn-ghost" @click="reloadAccounts()">重试</button>
        </StateBlock>

        <div v-else-if="(accountList ?? []).length === 0" class="mt-4">
          <StateBlock
            title="还没有闲鱼账号"
            description="填一个账号名（只是本地标签，比如 default），点「打开登录窗口」，在弹出的浏览器里扫码。登录成功后账号会出现在下面。"
          >
            <input v-model="newAccountName" class="field w-[180px]" placeholder="default" aria-label="新账号名" />
            <button
              type="button"
              class="btn btn-primary"
              :disabled="loginPhase[newAccountName]?.phase === 'waiting'"
              @click="startAccountLogin(newAccountName)"
            >
              <Icon v-if="loginPhase[newAccountName]?.phase === 'waiting'" name="loader" :size="13" class="spin" />
              <Icon v-else-if="loginPhase[newAccountName]?.phase === 'ok'" name="check" :size="13" />
              <Icon v-else name="scan" :size="13" />
              {{
                loginPhase[newAccountName]?.phase === 'waiting'
                  ? '等待扫码…'
                  : loginPhase[newAccountName]?.phase === 'ok'
                    ? '已登录'
                    : '打开登录窗口'
              }}
            </button>
          </StateBlock>
          <div v-if="loginPhase[newAccountName]" class="mt-3">
            <InlineNote :tone="phaseTone(loginPhase[newAccountName]?.phase ?? 'idle')">
              {{ loginPhase[newAccountName]?.message }}
            </InlineNote>
          </div>
        </div>

        <template v-else>
          <div class="mt-3 border-t border-line">
            <div
              v-for="account in accountList ?? []"
              :key="account.id"
              class="flex flex-wrap items-start justify-between gap-3 border-b border-line/70 py-3.5"
            >
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-[13px] text-ink">{{ account.name }}</span>
                  <span
                    class="rounded-full border px-2 py-[2px] text-[10px] leading-none"
                    :class="chipClass(accountStatusInfo(account.status, account.logged_in).tone)"
                  >
                    {{ accountStatusInfo(account.status, account.logged_in).label }}
                  </span>
                  <span v-if="account.has_state" class="text-[10px] text-muted">登录态文件已存</span>
                </div>
                <p class="mt-1 text-[10.5px] leading-relaxed text-muted">
                  {{ account.last_ok_at ? `上次成功登录 ${fmtStamp(account.last_ok_at)}` : '还没成功登录过' }}
                  <span v-if="account.last_error" class="text-red"> · {{ account.last_error }}</span>
                </p>
                <div v-if="loginPhase[account.name]" class="mt-2">
                  <InlineNote :tone="phaseTone(loginPhase[account.name]?.phase ?? 'idle')">
                    {{ loginPhase[account.name]?.message }}
                  </InlineNote>
                </div>
              </div>
              <button
                type="button"
                class="btn btn-ghost btn-sm h-8"
                :disabled="loginPhase[account.name]?.phase === 'waiting'"
                @click="startAccountLogin(account.name)"
              >
                <Icon v-if="loginPhase[account.name]?.phase === 'waiting'" name="loader" :size="12" class="spin" />
                <Icon v-else-if="loginPhase[account.name]?.phase === 'ok'" name="check" :size="12" class="text-jade" />
                <Icon v-else name="scan" :size="12" />
                {{
                  loginPhase[account.name]?.phase === 'waiting'
                    ? '等待扫码…'
                    : loginPhase[account.name]?.phase === 'ok'
                      ? '已登录'
                      : '打开登录窗口'
                }}
              </button>
            </div>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2">
            <span class="text-[11px] text-ink-2">再加一个账号：</span>
            <input v-model="newAccountName" class="field h-8 w-[160px]" placeholder="账号名" aria-label="新账号名" />
            <button
              type="button"
              class="btn btn-ghost btn-sm h-8"
              :disabled="loginPhase[newAccountName]?.phase === 'waiting'"
              @click="startAccountLogin(newAccountName)"
            >
              <Icon name="plus" :size="12" /> 打开登录窗口
            </button>
          </div>

          <div class="mt-6 border-t border-line pt-4">
            <h3 class="text-[12px] text-ink">导入旧登录态</h3>
            <p class="mt-1 text-[11px] leading-relaxed text-ink-2">
              从浏览器插件导出的 JSON 快照；导入后会立刻校验一次。
            </p>
            <div class="mt-2.5 flex flex-wrap items-center gap-2">
              <div class="w-[150px]">
                <SelectField v-model="importAccount" :options="accountOptions" small aria-label="导入到哪个账号" />
              </div>
              <input
                v-model="importPath"
                class="field h-8 min-w-[240px] flex-1 font-mono text-[11.5px]"
                placeholder="/Users/you/states/default.json"
                aria-label="旧登录态文件路径"
              />
              <button
                type="button"
                class="btn btn-ghost btn-sm h-8"
                :disabled="importing || !importAccount || !importPath.trim()"
                @click="doImport"
              >
                <Icon name="download" :size="12" /> {{ importing ? '导入中…' : '导入' }}
              </button>
            </div>
            <div v-if="importNote" class="mt-2">
              <InlineNote :tone="importNote.tone">{{ importNote.text }}</InlineNote>
            </div>
          </div>
        </template>
      </section>

      <section class="surface-card mt-4 p-5 lg:p-6">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="font-display text-[17px] font-semibold text-ink">通知</h2>
            <p class="mt-1 text-[11.5px] leading-relaxed text-ink-2">
              只有过线的商品才推。静默时段内只落站内账本，不推手机。
            </p>
          </div>
        </div>

        <div class="mt-4 grid gap-2 sm:grid-cols-2">
          <button
            v-for="channel in channelDefs"
            :key="channel.value"
            type="button"
            role="checkbox"
            :aria-checked="channels.includes(channel.value)"
            class="flex items-start gap-2.5 rounded-[10px] border border-line px-3 py-3 text-left transition-colors duration-150 hover:bg-paper-2"
            :class="channels.includes(channel.value) ? 'bg-paper-2/60' : ''"
            @click="toggleChannel(channel.value)"
          >
            <span
              class="mt-[1px] flex h-[16px] w-[16px] shrink-0 items-center justify-center rounded-[5px] border"
              :class="
                channels.includes(channel.value)
                  ? 'border-ink bg-ink text-paper'
                  : 'border-line text-transparent'
              "
            >
              <Icon name="check" :size="10" />
            </span>
            <span class="min-w-0">
              <span class="block text-[12px] leading-none text-ink">{{ channel.label }}</span>
              <span class="mt-1 block text-[10.5px] leading-snug text-muted">{{ channel.hint }}</span>
            </span>
          </button>
        </div>

        <p v-if="noChannel" class="mt-2.5">
          <InlineNote tone="muted">一个渠道都没勾：过线的商品只会落在本站账本里，不会推手机。</InlineNote>
        </p>

        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <FormField v-if="channels.includes('ntfy')" label="ntfy 地址">
            <input v-model="form.ntfy_url" class="field font-mono text-[12px]" placeholder="https://ntfy.sh/your-topic" />
          </FormField>
          <FormField v-if="channels.includes('bark')" label="Bark 地址">
            <input v-model="form.bark_url" class="field font-mono text-[12px]" placeholder="https://api.day.app/your-key" />
          </FormField>
          <FormField v-if="channels.includes('wecom')" label="企业微信 webhook" class="sm:col-span-2">
            <input v-model="form.wecom_url" class="field font-mono text-[12px]" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
          </FormField>
          <FormField v-if="channels.includes('webhook')" label="Webhook 地址" class="sm:col-span-2">
            <input v-model="form.webhook_url" class="field font-mono text-[12px]" placeholder="https://example.com/hook" />
          </FormField>

          <template v-if="channels.includes('telegram')">
            <FormField label="Bot Token" :help="hasTelegramToken ? '已保存；留空表示不改' : 'BotFather 给的那串 Token'">
              <input
                v-model="form.telegram_token"
                type="password"
                class="field font-mono text-[12px]"
                :placeholder="hasTelegramToken ? '已保存（留空不改）' : '123456:ABC...'"
                autocomplete="off"
              />
            </FormField>
            <FormField label="Chat ID">
              <input v-model="form.telegram_chat" class="field font-mono text-[12px]" placeholder="123456789" />
            </FormField>
          </template>

          <FormField
            label="静默时段"
            hint="只收不发"
            help="格式 23:30-08:00，可以跨午夜；留空表示不静默"
            class="sm:col-span-2 sm:max-w-[320px]"
          >
            <input v-model="form.quiet_hours" class="field num" placeholder="23:30-08:00" />
          </FormField>
        </div>

        <div class="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
          <p class="text-[10.5px] leading-relaxed text-muted">
            当前静默：<span class="num">{{ quietHours }}</span>；这段时间里过线的商品只进账本，不打扰你。
          </p>
          <div class="flex items-center gap-3">
            <button type="button" class="btn btn-primary btn-sm h-8" @click="saveNotify">保存通知</button>
          </div>
        </div>
      </section>

      <section class="surface-card mt-3 p-5 lg:p-6">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="font-display text-[17px] font-semibold text-ink">AI 与阈值</h2>
            <p class="mt-1 text-[11.5px] leading-relaxed text-ink-2">
              AI 只对过线候选复核，失败不影响采集；阈值决定市场统计多可信才算数。
            </p>
          </div>
        </div>

        <div class="mt-4 flex items-center justify-between gap-4 border-b border-line pb-3.5">
          <div>
            <p class="text-[12.5px] text-ink">AI 复核</p>
            <p class="mt-0.5 text-[10.5px] text-muted">关掉后只跑规则分，节省接口调用</p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-[10.5px]" :class="form.llm_enabled === '1' ? 'text-jade' : 'text-muted'">
              {{ form.llm_enabled === '1' ? '开' : '关' }}
            </span>
            <Toggle
              :model-value="form.llm_enabled === '1'"
              label="AI 复核开关"
              @update:model-value="setLlmEnabled"
            />
          </div>
        </div>

        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <FormField label="Base URL" help="兼容 /chat/completions 的地址" class="sm:col-span-2">
            <input v-model="form.llm_base_url" class="field font-mono text-[12px]" placeholder="https://api.deepseek.com" />
          </FormField>
          <FormField label="模型">
            <input v-model="form.llm_model" class="field font-mono text-[12px]" placeholder="deepseek-flash" />
          </FormField>
          <FormField label="API Key" :help="hasLlmKey ? '已保存；留空表示不改' : '还没保存过 Key'">
            <input
              v-model="form.llm_api_key"
              type="password"
              class="field font-mono text-[12px]"
              :placeholder="hasLlmKey ? '已保存（留空不改）' : 'sk-...'"
              autocomplete="off"
            />
          </FormField>
          <FormField label="每轮复核条数" help="按分数取前 N 条送 AI">
            <input v-model="form.llm_top_n" type="number" min="0" class="field num" />
          </FormField>
          <FormField label="最少样本数" help="市场样本少于这个数就不比价">
            <input v-model="form.min_samples" type="number" min="1" class="field num" />
          </FormField>
        </div>

        <div class="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
          <p class="max-w-[62ch] text-[10.5px] leading-relaxed text-muted">
            密钥不会回传前端：保存后输入框永远是空的，留空即保持原值。所有数据存在
            <span class="font-mono">~/.ruic-goofish-hunter</span>。
          </p>
          <div class="flex items-center gap-3">
            <button type="button" class="btn btn-primary btn-sm h-8" @click="saveAi">保存 AI 设置</button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
