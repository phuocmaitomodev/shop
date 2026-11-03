import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearRememberedOrder, rememberGuestOrder, rememberOrder, useOrderAccess } from '../stores/order-session'
import type { OrderSummary } from '../types/commerce'

const makeOrder = (overrides: Partial<OrderSummary> = {}): OrderSummary => ({
  id: 'order-1',
  order_code: 'DH-001',
  status: 'confirmed',
  recipient_name: 'Nguyễn An',
  phone: '0900000000',
  address_line: '1 Đường Mẫu',
  ward: null,
  district: null,
  province: 'TP. Hồ Chí Minh',
  note: null,
  subtotal: 240000,
  discount_amount: 0,
  shipping_fee: 30000,
  total: 270000,
  currency: 'VND',
  items: [],
  payment: { method: 'cod', status: 'cod_due', amount: 270000, provider: 'demo', is_simulation: true },
  guest_lookup_token: null,
  created_at: '2026-11-03T00:00:00Z',
  ...overrides,
})

describe('order session access context', () => {
  beforeEach(() => {
    clearRememberedOrder()
    vi.restoreAllMocks()
  })

  it('derives guest access atomically from a newly created guest order', () => {
    const order = makeOrder({ guest_lookup_token: 'new-checkout-token' })

    rememberOrder(order)

    expect(useOrderAccess()).toEqual({
      order,
      access: { mode: 'guest', lookup_token: 'new-checkout-token' },
    })
  })

  it('does not reuse a prior guest lookup token for a subsequent authenticated order', () => {
    rememberGuestOrder(makeOrder(), 'stale-lookup-token')
    const authenticatedOrder = makeOrder({ id: 'order-2', order_code: 'DH-002' })

    rememberOrder(authenticatedOrder)

    expect(useOrderAccess()).toEqual({
      order: authenticatedOrder,
      access: { mode: 'authenticated' },
    })
  })

  it('removes both the remembered order and its guest token when cleared', () => {
    rememberGuestOrder(makeOrder(), 'temporary-lookup-token')

    clearRememberedOrder()

    expect(useOrderAccess()).toBeNull()
  })

  it('keeps lookup tokens out of browser persistence, URLs, and logs', () => {
    const storageWrite = vi.spyOn(Storage.prototype, 'setItem')
    const pushState = vi.spyOn(history, 'pushState')
    const replaceState = vi.spyOn(history, 'replaceState')
    const consoleLog = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    const consoleInfo = vi.spyOn(console, 'info').mockImplementation(() => undefined)
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    rememberOrder(makeOrder({ guest_lookup_token: 'memory-only-token' }))
    clearRememberedOrder()

    expect(storageWrite).not.toHaveBeenCalled()
    expect(pushState).not.toHaveBeenCalled()
    expect(replaceState).not.toHaveBeenCalled()
    expect(consoleLog).not.toHaveBeenCalled()
    expect(consoleInfo).not.toHaveBeenCalled()
    expect(consoleWarn).not.toHaveBeenCalled()
    expect(consoleError).not.toHaveBeenCalled()
  })
})
