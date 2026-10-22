export interface ApiMeta {
  request_id: string
}

export interface ApiSuccess<T> {
  data: T
  meta: ApiMeta
}

export interface ApiErrorBody {
  code: string
  message: string
  fields?: Record<string, string>
  details?: Record<string, unknown>
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody
  meta: ApiMeta
}

export interface PaginatedData<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}
