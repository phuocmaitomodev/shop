import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiClientMock } = vi.hoisted(() => ({ apiClientMock: vi.fn() }))
vi.mock('../services/api-client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/api-client')>(),
  apiClient: apiClientMock,
}))

import {
  accountErrorMessage,
  getAccountProfile,
  login,
  logout,
  updateAccountProfile,
} from '../services/auth-account'
import { ApiClientError } from '../services/api-client'

const customer = {
  id: 'customer-1',
  email: 'an@example.com',
  full_name: 'Nguyễn An',
  phone: '0900000000',
  role: 'customer' as const,
  is_active: true,
}

describe('auth and account service contract', () => {
  beforeEach(() => apiClientMock.mockReset())

  it('logs in with email and password through the cookie-based API client', async () => {
    apiClientMock.mockResolvedValue({ data: customer, meta: { request_id: 'login-1' } })

    await expect(login({ email: ' an@example.com ', password: 'secret123' })).resolves.toEqual(customer)
    expect(apiClientMock).toHaveBeenCalledWith('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: 'an@example.com', password: 'secret123' }),
    })
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('loads and updates only the editable account profile fields', async () => {
    apiClientMock
      .mockResolvedValueOnce({ data: customer, meta: { request_id: 'profile-1' } })
      .mockResolvedValueOnce({ data: { ...customer, phone: null }, meta: { request_id: 'profile-2' } })

    await expect(getAccountProfile()).resolves.toEqual(customer)
    await expect(updateAccountProfile({ full_name: ' Nguyễn An ', phone: '  ' })).resolves.toEqual({
      ...customer,
      phone: null,
    })

    expect(apiClientMock.mock.calls).toEqual([
      ['/account/profile'],
      ['/account/profile', {
        method: 'PATCH',
        body: JSON.stringify({ full_name: 'Nguyễn An', phone: null }),
      }],
    ])
  })

  it('logs out without persisting or returning a client token', async () => {
    apiClientMock.mockResolvedValue({ data: { status: 'logged_out' }, meta: { request_id: 'logout-1' } })

    await expect(logout()).resolves.toBeUndefined()
    expect(apiClientMock).toHaveBeenCalledWith('/auth/logout', { method: 'POST' })
  })

  it.each([
    [new ApiClientError(401, { error: { code: 'INVALID_CREDENTIALS', message: 'server text', fields: {}, details: {} }, meta: { request_id: '1' } }), 'Email hoặc mật khẩu không đúng.'],
    [new ApiClientError(429, { error: { code: 'RATE_LIMITED', message: 'server text', fields: {}, details: {} }, meta: { request_id: '2' } }), 'Bạn thao tác quá nhanh. Vui lòng thử lại sau.'],
    [new ApiClientError(0, null), 'Không thể kết nối đến máy chủ. Vui lòng thử lại.'],
    [new Error('unexpected'), 'Đã có lỗi xảy ra. Vui lòng thử lại.'],
  ])('maps API failures to stable Vietnamese messages', (error, expected) => {
    expect(accountErrorMessage(error)).toBe(expected)
  })
})
