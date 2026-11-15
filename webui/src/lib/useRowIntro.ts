import { shallowRef } from 'vue'

/**
 * 只给「第一次进入列表」的行打上入场标记，用来做一次盖章式下沉。
 * 列表刷新时已见过的 id 不再动，避免整张表反复抖。
 */
export function useRowIntro() {
  const seen = new Set<string>()
  const fresh = shallowRef<Set<string>>(new Set())

  function sync(ids: string[]): void {
    const next = new Set<string>()
    for (const id of ids) {
      if (seen.has(id)) continue
      seen.add(id)
      next.add(id)
    }
    fresh.value = next
  }

  function reset(): void {
    seen.clear()
    fresh.value = new Set()
  }

  return { fresh, sync, reset }
}
