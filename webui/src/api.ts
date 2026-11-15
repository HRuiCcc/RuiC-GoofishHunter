/** 与 hunter/web/app.py 的 JSON 契约一一对应。字段名照抄后端，不另造。 */

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      },
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError('连不上本地服务：确认 hunter 已经在 127.0.0.1:7801 跑起来。', 0)
  }

  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
      else if (body.detail) message = JSON.stringify(body.detail)
    } catch {
      // 响应不是 JSON，保留状态码信息
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { signal })
}

function send<T>(path: string, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// --------------------------------------------------------------------------- 基础类型

export type FeedbackValue = '' | 'good' | 'bad' | 'deal'
export type ScoreTone = 'red' | 'jade' | 'ochre' | 'muted'

export interface RunRow {
  id: number
  watch_id: number | null
  watch_name: string | null
  keyword: string | null
  started_at: string
  finished_at: string | null
  found: number | null
  new_items: number | null
  scored: number | null
  alerted: number | null
  status: string
  error: string | null
  stats?: Record<string, unknown>
}

export interface TrendPoint {
  day: string
  n: number
  avg_price: number | null
  min_price: number | null
}

export interface WatchInput {
  name: string
  keyword: string
  sort: string
  pages: number
  personal_only: boolean
  free_shipping: boolean
  min_price: number | null
  max_price: number | null
  min_score: number
  interval_sec: number
  use_llm: boolean
  notify: boolean
  note: string
}

export interface Watch extends WatchInput {
  id: number
  account_id: number | null
  page_size: number
  enabled: boolean
  created_at: string
  last_run_at: string | null
  next_run_at: string | null
  item_count?: number
  last_run?: RunRow | null
}

export interface LlmResult {
  verdict?: 'buy' | 'watch' | 'skip' | string
  confidence?: number
  condition?: string
  missing_info?: string[]
  risks?: string[]
  ask_seller?: string
  summary?: string
  model?: string
  prompt_version?: string
  error?: string
}

export interface ItemRow {
  item_id: string
  title: string
  price: number | null
  price_display: string | null
  original_price: number | null
  area: string | null
  seller_id: string | null
  seller_nick: string | null
  publish_at: string | null
  first_seen_at: string
  last_seen_at: string | null
  pics_json: string[] | null
  tags_json: string[] | null
  labels_json: Record<string, string> | null
  spec_key: string | null
  want_cnt: number | null
  transport_fee: number | null
  status: string | null
  link: string | null
  feedback: FeedbackValue | null
  feedback_note: string | null
  desc?: string | null
  score?: number | null
  verdict?: string | null
  discount_pct?: number | null
  market_median?: number | null
  market_count?: number | null
  flags_json?: string[] | null
  reasons_json?: string[] | null
  breakdown_json?: Record<string, number> | null
  llm?: LlmResult | null
  score_watch?: number | null
}

export interface ScoreRecord {
  item_id: string
  watch_id: number
  score: number
  verdict: string
  market_median: number | null
  market_p25: number | null
  market_count: number | null
  discount_pct: number | null
  spec_key: string | null
  breakdown_json: Record<string, number> | null
  flags_json: string[] | null
  reasons_json: string[] | null
  llm_json: string | null
  llm: LlmResult | null
  scored_at: string
}

export interface Snapshot {
  price: number
  want_cnt: number | null
  seen_at: string
}

export interface Seller {
  seller_id: string
  nick: string | null
  city: string | null
  reg_days: number | null
  item_count: number | null
  sold_count: number | null
  credit_level: number | null
  credit_text: string | null
  zhima: number | boolean | null
  real_name: number | boolean | null
  reply_ratio: number | null
  good_ratio: number | null
  rate_total: number | null
  tags: string[] | null
  tags_json: string | null
  raw_json: string | null
  fetched_at: string
}

export interface ItemDetailPayload {
  item: ItemRow
  scores: ScoreRecord[]
  snapshots: Snapshot[]
  seller: Seller | null
}

export interface Overview {
  total_items: number
  today_items: number
  today_runs: number
  alerts_today: number
  avg_score: number | null
  active_watches: number
  by_verdict: Record<string, number>
  last_run: { started_at: string; status: string } | null
  best: { title: string; price: number | null; score: number } | null
  trend: TrendPoint[]
  top: ItemRow[]
}

export interface PreviewItem {
  item_id: string
  title: string
  price: number | null
  price_display?: string
  area?: string
  seller_nick?: string
  publish_at?: string | null
  pic?: string
  pics?: string[]
  tags?: string[]
  want_cnt?: number | null
  link?: string
}

export interface PreviewResult {
  count: number
  median: number | null
  minimum: number | null
  maximum: number | null
  filter: string
  items: PreviewItem[]
}

export interface Account {
  id: number
  name: string
  profile_dir: string
  status: string
  last_ok_at: string | null
  last_error: string | null
  created_at: string
  logged_in: boolean
  has_state: boolean
}

export interface LoginStatus {
  pending: boolean
  logged_in?: boolean
  detail?: string
  cookies?: number
}

export interface ImportResult {
  imported: number
  logged_in: boolean
  detail?: string
}

export interface Health {
  ok: boolean
  version: string
  time: string
  data_dir: string
  headless: boolean
  browser: string
}

export interface LogEvent {
  ts: string
  level: 'info' | 'ok' | 'warn' | 'error' | 'score' | string
  msg: string
  watch?: string
  run?: number
  score?: number
  account?: string
}

export type SettingsPayload = Record<string, string>

// --------------------------------------------------------------------------- 接口

export function getHealth(): Promise<Health> {
  return get<Health>('/health')
}

export function getOverview(signal?: AbortSignal): Promise<Overview> {
  return get<Overview>('/overview', signal)
}

export function getWatches(signal?: AbortSignal): Promise<Watch[]> {
  return get<Watch[]>('/watches', signal)
}

export function createWatch(payload: WatchInput): Promise<Watch> {
  return send<Watch>('/watches', 'POST', payload)
}

export function patchWatch(id: number, payload: Partial<WatchInput> & { enabled?: boolean }): Promise<Watch> {
  return send<Watch>(`/watches/${id}`, 'PATCH', payload)
}

export function deleteWatch(id: number): Promise<void> {
  return send<void>(`/watches/${id}`, 'DELETE')
}

export function runWatch(id: number): Promise<{ started: boolean }> {
  return send<{ started: boolean }>(`/watches/${id}/run`, 'POST')
}

export function previewWatch(payload: WatchInput): Promise<PreviewResult> {
  return send<PreviewResult>('/preview', 'POST', payload)
}

export interface ItemsQuery {
  watch_id?: number | null
  min_score?: number
  search?: string
  limit?: number
  offset?: number
  order?: 'score' | 'new' | 'price' | 'discount'
  feedback?: string
}

export function getItems(params: ItemsQuery = {}, signal?: AbortSignal): Promise<{ items: ItemRow[]; total: number }> {
  return get<{ items: ItemRow[]; total: number }>(
    `/items${query({
      watch_id: params.watch_id,
      min_score: params.min_score,
      search: params.search,
      limit: params.limit,
      offset: params.offset,
      order: params.order,
      feedback: params.feedback,
    })}`,
    signal,
  )
}

export function getItem(itemId: string, watchId?: number, signal?: AbortSignal): Promise<ItemDetailPayload> {
  return get<ItemDetailPayload>(`/items/${encodeURIComponent(itemId)}${query({ watch_id: watchId })}`, signal)
}

export function setFeedback(itemId: string, feedback: FeedbackValue, note = ''): Promise<{ ok: boolean }> {
  return send<{ ok: boolean }>(`/items/${encodeURIComponent(itemId)}/feedback`, 'POST', { feedback, note })
}

export function getRuns(limit = 30, signal?: AbortSignal): Promise<RunRow[]> {
  return get<RunRow[]>(`/runs${query({ limit })}`, signal)
}

export function getAccounts(signal?: AbortSignal): Promise<Account[]> {
  return get<Account[]>('/accounts', signal)
}

export function startLogin(name: string): Promise<{ started: boolean; reason?: string }> {
  return send<{ started: boolean; reason?: string }>(`/accounts/${encodeURIComponent(name)}/login`, 'POST')
}

export function getLoginStatus(name: string): Promise<LoginStatus> {
  return get<LoginStatus>(`/accounts/${encodeURIComponent(name)}/status`)
}

export function importLogin(name: string, path: string): Promise<ImportResult> {
  return send<ImportResult>(`/accounts/${encodeURIComponent(name)}/import`, 'POST', { path })
}

export type SettingsResult = SettingsPayload & {
  has_llm_key?: boolean
  has_telegram_token?: boolean
}

export function getSettings(signal?: AbortSignal): Promise<SettingsResult> {
  return get<SettingsResult>('/settings', signal)
}

export function putSettings(values: Record<string, string>): Promise<{ ok: boolean }> {
  return send<{ ok: boolean }>('/settings', 'PUT', { values })
}

export function getLogs(limit = 200): Promise<LogEvent[]> {
  return get<LogEvent[]>(`/logs${query({ limit })}`)
}

export const EVENTS_URL = '/api/events'
