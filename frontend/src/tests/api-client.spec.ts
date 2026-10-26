import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchMock = vi.fn()

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('VITE_API_BASE_URL', 'http://api.test/api/v1')
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('api client', () => {
  it('preserves Headers input and lets the browser set multipart content type', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ data: { ok: true } }), { status: 200 }))
    const { apiClient } = await import('../services/api-client')
    const body = new FormData()
    body.append('image', new Blob(['image']), 'image.png')

    await apiClient('/admin/media/images', {
      method: 'POST',
      body,
      headers: new Headers({ 'X-Request-Source': 'admin' }),
    })

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(request.headers)
    expect(headers.get('Accept')).toBe('application/json')
    expect(headers.get('X-Request-Source')).toBe('admin')
    expect(headers.has('Content-Type')).toBe(false)
  })

  it('sets JSON content type for a serialized JSON body unless overridden', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    const { apiClient } = await import('../services/api-client')

    await apiClient('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: 'demo@example.com' }),
      headers: [['X-Request-Source', 'storefront']],
    })

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(request.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('X-Request-Source')).toBe('storefront')
  })

  it('keeps the stable API error code and status from an error envelope', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      error: {
        code: 'PRODUCT_NOT_FOUND',
        message: 'Không tìm thấy sản phẩm.',
        fields: {},
        details: {},
      },
      meta: { request_id: 'request-1' },
    }), { status: 404, headers: { 'Content-Type': 'application/json' } }))
    const { apiClient, ApiClientError } = await import('../services/api-client')

    const request = apiClient('/products/khong-ton-tai')
    await expect(request).rejects.toBeInstanceOf(ApiClientError)
    await expect(request).rejects.toMatchObject({
      status: 404,
      message: 'Không tìm thấy sản phẩm.',
      payload: { error: { code: 'PRODUCT_NOT_FOUND' } },
    })
  })

  it('normalizes network failures to the shared API client error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const { apiClient, ApiClientError } = await import('../services/api-client')

    await expect(apiClient('/products')).rejects.toMatchObject({
      name: ApiClientError.name,
      status: 0,
      payload: null,
      message: 'Không thể kết nối đến máy chủ.',
    })
  })

  it('does not trust an HTTP error body outside the project error envelope', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    }))
    const { apiClient, ApiClientError } = await import('../services/api-client')

    await expect(apiClient('/products')).rejects.toMatchObject({
      name: ApiClientError.name,
      status: 500,
      payload: null,
      message: 'Không thể kết nối đến máy chủ.',
    })
  })
})
