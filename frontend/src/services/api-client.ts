import type { ApiErrorEnvelope } from '../types/api'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL

if (!apiBaseUrl) {
  throw new Error('Thiếu biến môi trường VITE_API_BASE_URL cho API client.')
}

export class ApiClientError extends Error {
  readonly status: number
  readonly payload: ApiErrorEnvelope | null

  constructor(
    status: number,
    payload: ApiErrorEnvelope | null,
  ) {
    super(payload?.error.message ?? 'Không thể kết nối đến máy chủ.')
    this.name = 'ApiClientError'
    this.status = status
    this.payload = payload
  }
}

export const apiClient = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }
  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`, {
    ...init,
    credentials: 'include',
    headers,
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ApiErrorEnvelope | null
    throw new ApiClientError(response.status, payload)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}
