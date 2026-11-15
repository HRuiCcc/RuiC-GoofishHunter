import { ref, shallowRef, type Ref } from 'vue'
import { ApiError } from '../api'

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return '出了点问题，稍后再试。'
}

export interface AsyncData<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  reload: () => Promise<void>
}

/** 一次请求的 loading / error / data 三件套，带「过期响应丢弃」。 */
export function useAsyncData<T>(loader: () => Promise<T>, options: { immediate?: boolean } = {}): AsyncData<T> {
  const data = shallowRef<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref<string | null>(null)
  let latest = 0

  async function reload(): Promise<void> {
    const token = ++latest
    loading.value = true
    error.value = null
    try {
      const value = await loader()
      if (token === latest) data.value = value
    } catch (problem) {
      if (token === latest) error.value = errorMessage(problem)
    } finally {
      if (token === latest) loading.value = false
    }
  }

  if (options.immediate !== false) void reload()
  return { data, loading, error, reload }
}
