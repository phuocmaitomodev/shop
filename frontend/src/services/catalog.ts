import { apiClient } from './api-client'
import type { ApiSuccess, PaginatedData } from '../types/api'
import type { CatalogQuery, ProductCardData, ProductDetail } from '../types/catalog'

const MAX_PAGE = 1_000_000
const MAX_PAGE_SIZE = 100

export const parseCatalogPrice = (value: unknown): number | undefined => {
  if (value === null || value === undefined || (typeof value === 'string' && !value.trim())) {
    return undefined
  }

  const parsed = Number(value)
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : undefined
}

const isIntegerInRange = (value: number | undefined, max: number) => (
  value !== undefined && Number.isInteger(value) && value >= 1 && value <= max
)

export const buildCatalogQuery = (query: CatalogQuery): string => {
  const params = new URLSearchParams()
  const keyword = query.q?.trim()
  const category = query.category?.trim()
  const color = query.color?.trim()
  const size = query.size?.trim()
  const minPrice = parseCatalogPrice(query.minPrice)
  const maxPrice = parseCatalogPrice(query.maxPrice)

  if (keyword) params.set('q', keyword)
  if (category) params.set('category', category)
  if (minPrice !== undefined) params.set('min_price', String(minPrice))
  if (maxPrice !== undefined) params.set('max_price', String(maxPrice))
  if (color) params.set('color', color)
  if (size) params.set('size', size)
  if (isIntegerInRange(query.page, MAX_PAGE)) params.set('page', String(query.page))
  if (isIntegerInRange(query.pageSize, MAX_PAGE_SIZE)) params.set('page_size', String(query.pageSize))

  return params.toString()
}

const withQuery = (path: string, query: CatalogQuery) => {
  const encodedQuery = buildCatalogQuery(query)
  return encodedQuery ? `${path}?${encodedQuery}` : path
}

export const getProducts = async (query: CatalogQuery = {}): Promise<PaginatedData<ProductCardData>> => {
  const response = await apiClient<ApiSuccess<PaginatedData<ProductCardData>>>(
    withQuery('/products', query),
  )
  return response.data
}

export const getProduct = async (slug: string): Promise<ProductDetail> => {
  const response = await apiClient<ApiSuccess<ProductDetail>>(
    `/products/${encodeURIComponent(slug)}`,
  )
  return response.data
}
