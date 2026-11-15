import type { FeedbackValue, ItemRow, ScoreTone, Watch } from '../api'

const moneyFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })

function pad2(value: number): string {
  return value < 10 ? `0${value}` : String(value)
}

export function toDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const text = value.includes('T') ? value : value.replace(' ', 'T')
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 账本式时间戳：11-15 10:40 */
export function fmtStamp(value: string | null | undefined): string {
  if (!value) return '暂无'
  const date = toDate(value)
  if (!date) return value
  return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

export function fmtClock(value: string | null | undefined): string {
  if (!value) return '暂无'
  const date = toDate(value)
  if (!date) return value
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

export function timeAgo(value: string | null | undefined, now = Date.now()): string {
  const date = toDate(value)
  if (!date) return '暂无'
  const diff = Math.floor((now - date.getTime()) / 1000)
  if (diff < 0) return fmtStamp(value)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
}

export function countdown(target: string | null | undefined, now = Date.now()): { text: string; seconds: number } {
  const date = toDate(target)
  if (!date) return { text: '未排期', seconds: Number.POSITIVE_INFINITY }
  const seconds = Math.round((date.getTime() - now) / 1000)
  if (seconds <= 0) return { text: '即将运行', seconds }
  if (seconds < 60) return { text: `${seconds} 秒后`, seconds }
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const rest = seconds % 60
    return { text: `${minutes} 分 ${rest} 秒后`, seconds }
  }
  if (seconds < 86400) {
    return { text: `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分后`, seconds }
  }
  return { text: `${Math.floor(seconds / 86400)} 天 ${Math.floor((seconds % 86400) / 3600)} 小时后`, seconds }
}

export function fmtDuration(start: string | null | undefined, end: string | null | undefined): string {
  const from = toDate(start)
  const to = toDate(end)
  if (!from || !to) return '进行中'
  const seconds = Math.max(0, Math.round((to.getTime() - from.getTime()) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`
}

export function fmtInterval(seconds: number | null | undefined): string {
  if (!seconds || seconds < 60) return '60 秒'
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`
  if (seconds % 3600 === 0) return `${seconds / 3600} 小时`
  return `${(seconds / 3600).toFixed(1)} 小时`
}

export function fmtMoney(value: number | null | undefined, fallback = '暂无'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback
  return `¥${moneyFormatter.format(Math.round(value))}`
}

export function fmtNumber(value: number | null | undefined, fallback = '暂无'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback
  return new Intl.NumberFormat('zh-CN').format(value)
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '暂无'
  return `${value.toFixed(digits)}%`
}

export function fmtYears(days: number | null | undefined): string {
  if (days === null || days === undefined) return '暂无'
  return `${(days / 365).toFixed(1)} 年`
}

export function fmtRatio(value: number | null | undefined): string {
  if (value === null || value === undefined) return '暂无'
  return `${Math.round(value)}%`
}

// --------------------------------------------------------------------------- 分数与颜色

export function scoreTone(score: number | null | undefined): ScoreTone {
  if (score === null || score === undefined) return 'muted'
  if (score >= 80) return 'red'
  if (score >= 65) return 'jade'
  if (score >= 50) return 'ochre'
  return 'muted'
}

export function toneText(tone: ScoreTone): string {
  return {
    red: 'text-red',
    jade: 'text-jade',
    ochre: 'text-ochre',
    muted: 'text-muted',
  }[tone]
}

export function toneFill(tone: ScoreTone): string {
  return {
    red: '#FF5A3C',
    jade: '#4ED6A8',
    ochre: '#F0B429',
    muted: '#8C8880',
  }[tone]
}

export function verdictFromScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return '未评分'
  if (score >= 80) return '强烈推荐'
  if (score >= 65) return '值得看'
  if (score >= 50) return '观望'
  return '放弃'
}

// --------------------------------------------------------------------------- 状态文案

export function statusInfo(status: string | null | undefined): { label: string; tone: 'jade' | 'ochre' | 'red' | 'muted' } {
  switch (status) {
    case 'running':
      return { label: '进行中', tone: 'ochre' }
    case 'ok':
      return { label: '完成', tone: 'jade' }
    case 'error':
      return { label: '失败', tone: 'red' }
    case 'risk':
      return { label: '风控', tone: 'red' }
    case 'login':
      return { label: '登录失效', tone: 'red' }
    default:
      return { label: status || '未知', tone: 'muted' }
  }
}

export function accountStatusInfo(status: string | null | undefined, loggedIn: boolean): { label: string; tone: 'jade' | 'ochre' | 'red' | 'muted' } {
  if (loggedIn) return { label: '已登录', tone: 'jade' }
  switch (status) {
    case 'expired':
      return { label: '登录态过期', tone: 'red' }
    case 'risk':
      return { label: '触发风控', tone: 'red' }
    case 'ok':
      return { label: '待确认', tone: 'ochre' }
    default:
      return { label: '未登录', tone: 'ochre' }
  }
}

export function sortLabel(sort: string | null | undefined): string {
  return (
    {
      newest: '最新发布',
      price_asc: '价格从低到高',
      price_desc: '价格从高到低',
      default: '综合排序',
    } as Record<string, string>
  )[sort ?? ''] ?? '最新发布'
}

export function feedbackLabel(value: FeedbackValue | null | undefined): string {
  return (
    {
      good: '值得聊',
      bad: '不合适',
      deal: '已成交',
    } as Record<string, string>
  )[value ?? ''] ?? '未标记'
}

/** 正负旗标：风险词用朱砂，利好词用玉色，其余用次墨。 */
export function flagTone(flag: string): 'red' | 'jade' | 'muted' {
  if (/(拆|修|换|进水|暗病|划痕|磕|漏|翻新|非原|保|坏|缺|裂|弯)/.test(flag)) return 'red'
  if (/(包邮|原盒|全套|自用|国行|发票|健康|芝麻|实人)/.test(flag)) return 'jade'
  return 'muted'
}

/** 风险旗标：只留负向标签，正向的「包邮」这类归到商品标签行。 */
export function isRiskFlag(flag: string): boolean {
  if (/(包邮|信用|芝麻|实人|自用|国行|原盒|全套|发票|健康|验货宝)/.test(flag)) return false
  return /(进水|非原装|仿品|有锁|锁机|卡贴|激活锁|主板|拆修|维修|修过|功能异常|仅自提|商家|贩子|工作室|电池.*偏低|未命中|欧版|美版|港版|日版|韩版|台版|海外|国际版|水货|翻新|组装|拆过|换过)/.test(flag)
}

export function riskFlagsOf(item: ItemRow, limit = 3): string[] {
  return (item.flags_json ?? []).filter(isRiskFlag).slice(0, limit)
}

/** 商品标签行：tags_json 与正向 flags 合并去重。 */
export function tagChipsOf(item: ItemRow, limit = 3): string[] {
  const merged = [...(item.tags_json ?? []), ...(item.flags_json ?? []).filter((flag) => !isRiskFlag(flag))]
  return [...new Set(merged.filter(Boolean))].slice(0, limit)
}

export function labelsOf(item: ItemRow): Array<{ label: string; value: string }> {
  const labels = item.labels_json ?? {}
  // 有 spec_key（如 16+512）时不再重复显示存储容量 / 运行内存。
  const order = item.spec_key
    ? ['成色', '拆修和功能']
    : ['成色', '存储容量', '运行内存', '拆修和功能']
  const out: Array<{ label: string; value: string }> = []
  for (const key of order) {
    const value = labels[key]
    if (value) out.push({ label: key, value })
  }
  return out.slice(0, 2)
}

export function tagsOf(item: ItemRow): string[] {
  return tagChipsOf(item, 2)
}

/** 「相对中位价」横条用的比例。 */
export function medianGeometry(price: number | null | undefined, median: number | null | undefined): {
  pricePct: number
  medianPct: number
  below: boolean
  diffPct: number | null
} | null {
  if (price === null || price === undefined || !median || median <= 0) return null
  const domain = Math.max(price, median) * 1.08
  const below = price <= median
  return {
    pricePct: Math.min(100, Math.max(0, (price / domain) * 100)),
    medianPct: Math.min(100, Math.max(0, (median / domain) * 100)),
    below,
    diffPct: ((median - price) / median) * 100,
  }
}

export function relativeText(price: number | null | undefined, median: number | null | undefined): string {
  if (price === null || price === undefined || !median) return '样本不足'
  const diff = ((median - price) / median) * 100
  if (Math.abs(diff) < 0.5) return '与中位持平'
  return diff > 0 ? `低 ${diff.toFixed(1)}%` : `高 ${Math.abs(diff).toFixed(1)}%`
}

/** 关注表的筛选摘要：个人闲置 · 包邮 · ¥2000~4000 · ≥60 分 · 2 页 */
export function watchFilterSummary(watch: Watch): string {
  const parts: string[] = []
  if (watch.personal_only) parts.push('个人闲置')
  if (watch.free_shipping) parts.push('包邮')
  if (watch.min_price !== null && watch.min_price !== undefined && watch.max_price !== null && watch.max_price !== undefined) {
    parts.push(`${fmtMoney(watch.min_price)}~${fmtMoney(watch.max_price)}`)
  } else if (watch.min_price !== null && watch.min_price !== undefined) {
    parts.push(`${fmtMoney(watch.min_price)} 起`)
  } else if (watch.max_price !== null && watch.max_price !== undefined) {
    parts.push(`${fmtMoney(watch.max_price)} 以内`)
  }
  parts.push(`≥${watch.min_score} 分`)
  parts.push(`${watch.pages} 页`)
  return parts.join(' · ')
}

export function scanPerDay(intervalSec: number | null | undefined): string {
  if (!intervalSec || intervalSec <= 0) return '暂无'
  const count = Math.floor(86400 / intervalSec)
  return `每天约 ${count} 轮`
}

export function verdictChip(verdict: string | null | undefined): { label: string; tone: 'jade' | 'ochre' | 'red' | 'muted' } {
  switch (verdict) {
    case 'buy':
      return { label: '值得买', tone: 'jade' }
    case 'watch':
      return { label: '再观察', tone: 'ochre' }
    case 'skip':
      return { label: '放弃', tone: 'red' }
    default:
      return { label: '未复核', tone: 'muted' }
  }
}
