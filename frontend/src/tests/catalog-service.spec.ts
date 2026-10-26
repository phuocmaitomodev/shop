import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiSuccess, PaginatedData } from '../types/api'
import type { ProductCardData, ProductDetail } from '../types/catalog'

const { apiClientMock } = vi.hoisted(() => ({ apiClientMock: vi.fn() }))
vi.mock('../services/api-client', () => ({ apiClient: apiClientMock }))

import {
  buildCatalogQuery,
  getProduct,
  getProducts,
  parseCatalogPrice,
} from '../services/catalog'

const card: ProductCardData = {
  id: 'product-1',
  slug: 'ao-thun-basic',
  sku: 'AT-001',
  name: 'Áo thun basic',
  category: {
    id: 'category-1',
    name: 'Áo thun',
    slug: 'ao-thun',
    description: 'Áo thun nam nữ',
    sort_order: 1,
  },
  image_url: '/media/products/ao-thun-basic.jpg',
  price: 299000,
  sale_price: 249000,
  effective_price: 249000,
  labels: ['Giảm giá'],
  available_sizes: ['M'],
  available_colors: [{ id: 'color-1', name: 'Đen', hex_code: '#000000' }],
  in_stock: true,
}

const detail: ProductDetail = {
  ...card,
  description: 'Áo thun cotton mềm mại.',
  images: [{
    id: 'image-1',
    url: '/media/products/ao-thun-basic.jpg',
    alt_text: 'Áo thun basic màu đen',
    sort_order: 0,
    is_primary: true,
  }],
  variants: [{
    id: 'variant-1',
    sku: 'AT-001-DEN-M',
    color: { id: 'color-1', name: 'Đen', hex_code: '#000000' },
    size: { id: 'size-1', code: 'M', name: 'Medium' },
    stock_quantity: 3,
    is_available: true,
  }],
}

describe('catalog service', () => {
  beforeEach(() => {
    apiClientMock.mockReset()
  })

  it('serializes encoded MVP filters and pagination with contract query keys', async () => {
    apiClientMock.mockResolvedValue({
      data: { items: [], page: 2, page_size: 12, total: 0 },
      meta: { request_id: 'request-1' },
    })

    await getProducts({
      q: '  áo linen & lụa  ',
      category: 'ao sơ mi',
      minPrice: 100000,
      maxPrice: 500000,
      size: ' M/L ',
      color: ' đỏ & đen ',
      page: 2,
      pageSize: 12,
    })

    const path = apiClientMock.mock.calls[0][0] as string
    expect(path).toContain('q=%C3%A1o+linen+%26+l%E1%BB%A5a')
    const query = new URLSearchParams(path.split('?')[1])
    expect(Object.fromEntries(query)).toEqual({
      q: 'áo linen & lụa',
      category: 'ao sơ mi',
      min_price: '100000',
      max_price: '500000',
      size: 'M/L',
      color: 'đỏ & đen',
      page: '2',
      page_size: '12',
    })
  })

  it('omits blank, invalid and out-of-contract query values consistently', () => {
    expect(buildCatalogQuery({
      q: ' ',
      category: '',
      size: ' ',
      color: '   ',
      minPrice: -1,
      maxPrice: 99.5,
      page: 1_000_001,
      pageSize: 101,
    })).toBe('')
  })

  it('treats cleared price fields as absent and accepts integer VND', () => {
    expect(parseCatalogPrice('')).toBeUndefined()
    expect(parseCatalogPrice('   ')).toBeUndefined()
    expect(parseCatalogPrice(null)).toBeUndefined()
    expect(parseCatalogPrice('249000')).toBe(249000)
    expect(parseCatalogPrice('12.5')).toBeUndefined()
    expect(parseCatalogPrice(Number.MAX_SAFE_INTEGER + 1)).toBeUndefined()
  })

  it('unwraps the pagination envelope without inventing product fields', async () => {
    const envelope: ApiSuccess<PaginatedData<ProductCardData>> = {
      data: { items: [card], page: 2, page_size: 12, total: 13 },
      meta: { request_id: 'request-2' },
    }
    apiClientMock.mockResolvedValue(envelope)

    await expect(getProducts({ page: 2, pageSize: 12 })).resolves.toEqual(envelope.data)
    expect(apiClientMock).toHaveBeenCalledWith('/products?page=2&page_size=12')
  })

  it('encodes the slug and preserves variant stock from the detail envelope', async () => {
    const envelope: ApiSuccess<ProductDetail> = {
      data: detail,
      meta: { request_id: 'request-3' },
    }
    apiClientMock.mockResolvedValue(envelope)

    const result = await getProduct('áo/basic')

    expect(apiClientMock).toHaveBeenCalledWith('/products/%C3%A1o%2Fbasic')
    expect(result.variants).toEqual(detail.variants)
    expect(result.variants[0]).toMatchObject({ stock_quantity: 3, is_available: true })
  })

  it('propagates the shared API client error unchanged', async () => {
    const error = {
      name: 'ApiClientError',
      message: 'Không tìm thấy sản phẩm.',
      status: 404,
      payload: { error: { code: 'PRODUCT_NOT_FOUND' } },
    }
    apiClientMock.mockImplementation(() => {
      throw error
    })

    let received: unknown = null
    try {
      await getProduct('khong-ton-tai')
    } catch (caught) {
      received = caught
    }

    expect(received === error).toBe(true)
  })
})