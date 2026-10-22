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
})
