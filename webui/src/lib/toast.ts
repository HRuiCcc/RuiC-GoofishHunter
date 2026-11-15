import { reactive } from 'vue'

export type ToastTone = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  tone: ToastTone
  message: string
}

const items = reactive<ToastItem[]>([])
const timers = new Map<number, number>()
let seq = 0

export function dismissToast(id: number): void {
  const index = items.findIndex((item) => item.id === id)
  if (index >= 0) items.splice(index, 1)
  const timer = timers.get(id)
  if (timer) {
    window.clearTimeout(timer)
    timers.delete(id)
  }
}

function push(tone: ToastTone, message: string): void {
  const id = ++seq
  items.push({ id, tone, message })
  while (items.length > 4) {
    const oldest = items[0]
    if (!oldest) break
    dismissToast(oldest.id)
  }
  timers.set(
    id,
    window.setTimeout(() => dismissToast(id), 2500),
  )
}

export const toast = {
  success: (message: string) => push('success', message),
  error: (message: string) => push('error', message),
  info: (message: string) => push('info', message),
  dismiss: dismissToast,
}

export const toasts = items
