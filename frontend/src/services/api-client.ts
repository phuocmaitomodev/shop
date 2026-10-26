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

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)

const isStringRecord = (value: unknown): value is Record<string, string> => (
  isRecord(value) && Object.values(value).every((item) => typeof item === 'string')
)

const isApiErrorEnvelope = (value: unknown): value is ApiErrorEnvelope => {
  if (!isRecord(value) || !isRecord(value.error) || !isRecord(value.meta)) return false

  return (
    typeof value.error.code === 'string'
    && typeof value.error.message === 'string'
    && isStringRecord(value.error.fields)
    && isRecord(value.error.details)
    && typeof value.meta.request_id === 'string'
  )
}

export const apiClient = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }
  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`, {
      ...init,
      credentials: 'include',
      headers,
    })
  } catch {
    throw new ApiClientError(0, null)
  }

  if (!response.ok) {
    const responseBody: unknown = await response.json().catch(() => null)
    const payload = isApiErrorEnvelope(responseBody) ? responseBody : null
    throw new ApiClientError(response.status, payload)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}
