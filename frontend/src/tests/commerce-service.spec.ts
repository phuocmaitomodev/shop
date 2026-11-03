import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiClientMock } = vi.hoisted(() => ({ apiClientMock: vi.fn() }))
vi.mock('../services/api-client', () => ({ apiClient: apiClientMock }))

import {
  addCartItem,
  applyCartCoupon,
  cancelOrder,
  createActionConfirmation,
  createOrder,
  createRefundRequest,
  getCart,
  getOrder,
  getLatestRefundRequest,
  getPaymentDemo,
  lookupGuestOrder,
  removeCartCoupon,
  removeCartItem,
  updateCartItem,
} from '../services/commerce'
import type { OrderSummary } from '../types/commerce'

const cartFixture = {
  cart_id: 'cart-1',
  version: 3,
  items: [],
  subtotal: 249000,
  discount_amount: 0,
  shipping_fee: 30000,
  total: 279000,
  currency: 'VND' as const,
}

describe('commerce service contract', () => {
  beforeEach(() => {
    apiClientMock.mockReset()
  })

  it('keeps the snake_case cart fixture and integer VND totals', async () => {
    apiClientMock.mockResolvedValue({ data: cartFixture, meta: { request_id: 'request-cart' } })

    await expect(getCart()).resolves.toEqual(cartFixture)
    expect(apiClientMock).toHaveBeenCalledWith('/cart')
    expect(Number.isSafeInteger(cartFixture.total)).toBe(true)
    expect(cartFixture.currency).toBe('VND')
  })

  it('sends checkout confirmation and idempotency fields without client totals', async () => {
    const order = {
      id: 'order-1',
      order_code: 'DH-2026-0001',
      status: 'pending_confirmation' as const,
      recipient_name: 'Nguyễn An',
      phone: '0900000000',
      address_line: '1 Đường Mẫu',
      ward: 'Phường 1',
      district: 'Quận 1',
      province: 'TP. Hồ Chí Minh',
      note: null,
      subtotal: 249000,
      discount_amount: 0,
      shipping_fee: 30000,
      total: 279000,
      currency: 'VND' as const,
      items: [],
      payment: { method: 'online_demo' as const, status: 'demo_processing' as const, amount: 279000, provider: 'demo' as const, is_simulation: true as const },
      guest_lookup_token: 'guest-lookup-token',
      created_at: '2026-11-03T00:00:00Z',
    } satisfies OrderSummary
    apiClientMock.mockResolvedValue({ data: order, meta: { request_id: 'request-order' } })
    const request = {
      cart_id: 'cart-1',
      cart_version: 3,
      recipient_name: 'Nguyễn An',
      phone: '0900000000',
      address_line: '1 Đường Mẫu',
      ward: 'Phường 1',
      district: 'Quận 1',
      province: 'TP. Hồ Chí Minh',
      note: null,
      payment_method: 'online_demo' as const,
      confirmation_token: 'confirmation-token',
    }

    await expect(createOrder(request, 'order-key-1')).resolves.toEqual(order)
    expect(apiClientMock).toHaveBeenCalledWith('/orders', {
      method: 'POST',
      headers: { 'Idempotency-Key': 'order-key-1' },
      body: JSON.stringify(request),
    })
    expect(JSON.parse(apiClientMock.mock.calls[0][1].body)).not.toHaveProperty('total')
  })

  it('keeps the guest lookup token in the ownership header instead of the URL', async () => {
    apiClientMock.mockResolvedValue({
      data: { order_code: 'DH-2026-0001' },
      meta: { request_id: 'request-lookup' },
    })

    await lookupGuestOrder('DH-2026/0001', 'lookup-secret')

    expect(apiClientMock).toHaveBeenCalledWith('/orders/lookup?order_code=DH-2026%2F0001', {
      headers: { 'X-Order-Lookup-Token': 'lookup-secret' },
    })
    expect(apiClientMock.mock.calls[0][0]).not.toContain('lookup-secret')
  })

  it('serializes cart mutations with snake_case version fields', async () => {
    apiClientMock.mockResolvedValue({ data: cartFixture, meta: { request_id: 'request-cart-write' } })

    await addCartItem({ variant_id: 'variant-1', quantity: 2 })
    await updateCartItem('item/1', { quantity: 3, cart_version: 3 })
    await removeCartItem('item/1', 4)

    expect(apiClientMock.mock.calls).toEqual([
      ['/cart/items', { method: 'POST', body: JSON.stringify({ variant_id: 'variant-1', quantity: 2 }) }],
      ['/cart/items/item%2F1', { method: 'PATCH', body: JSON.stringify({ quantity: 3, cart_version: 3 }) }],
      ['/cart/items/item%2F1', { method: 'DELETE', body: JSON.stringify({ cart_version: 4 }) }],
    ])
  })

  it('uses guest ownership headers and confirmation for payment and refund demo APIs', async () => {
    const guestAccess = { mode: 'guest' as const, lookup_token: 'lookup-secret' }
    apiClientMock
      .mockResolvedValueOnce({ data: { provider: 'demo', amount: 279000 }, meta: { request_id: 'payment' } })
      .mockResolvedValueOnce({ data: null, meta: { request_id: 'refund-read' } })
      .mockResolvedValueOnce({ data: { status: 'requested' }, meta: { request_id: 'refund-create' } })

    await getPaymentDemo('DH/001', guestAccess)
    await getLatestRefundRequest('DH/001', guestAccess)
    await createRefundRequest('DH/001', {
      reason_code: 'damaged_item',
      reason_detail: 'Sản phẩm bị lỗi đường may.',
      confirmation_token: 'confirmation-token',
    }, 'refund-key-1', guestAccess)

    const ownershipHeaders = { 'X-Order-Lookup-Token': 'lookup-secret' }
    expect(apiClientMock.mock.calls).toEqual([
      ['/orders/DH%2F001/payment', { headers: ownershipHeaders }],
      ['/orders/DH%2F001/refund-requests/latest', { headers: ownershipHeaders }],
      ['/orders/DH%2F001/refund-requests', {
        method: 'POST',
        headers: { ...ownershipHeaders, 'Idempotency-Key': 'refund-key-1' },
        body: JSON.stringify({
          reason_code: 'damaged_item',
          reason_detail: 'Sản phẩm bị lỗi đường may.',
          confirmation_token: 'confirmation-token',
        }),
      }],
    ])
  })

  it('uses cookie ownership for authenticated order reads and confirmed cancellation', async () => {
    apiClientMock.mockResolvedValue({ data: { order_code: 'DH-001' }, meta: { request_id: 'order' } })

    await getOrder('DH/001')
    await cancelOrder('DH/001', 'confirmation-token', 'cancel-key-1')

    expect(apiClientMock.mock.calls).toEqual([
      ['/orders/DH%2F001'],
      ['/orders/DH%2F001/cancel', {
        method: 'POST',
        headers: { 'Idempotency-Key': 'cancel-key-1' },
        body: JSON.stringify({ reason: null, confirmation_token: 'confirmation-token' }),
      }],
    ])
  })

  it('sends the lookup header when a guest confirms order cancellation', async () => {
    apiClientMock.mockResolvedValue({ data: { order_code: 'DH-001' }, meta: { request_id: 'cancel' } })

    await cancelOrder(
      'DH/001',
      'confirmation-token',
      'cancel-key-1',
      { mode: 'guest', lookup_token: 'lookup-secret' },
    )

    expect(apiClientMock).toHaveBeenCalledWith('/orders/DH%2F001/cancel', {
      method: 'POST',
      headers: {
        'X-Order-Lookup-Token': 'lookup-secret',
        'Idempotency-Key': 'cancel-key-1',
      },
      body: JSON.stringify({ reason: null, confirmation_token: 'confirmation-token' }),
    })
  })

  it('keeps checkout pricing server-owned and serializes coupon versions', async () => {
    apiClientMock
      .mockResolvedValueOnce({ data: cartFixture, meta: { request_id: 'coupon' } })
      .mockResolvedValueOnce({ data: cartFixture, meta: { request_id: 'coupon-remove' } })

    await applyCartCoupon(' GIAM10 ', 3)
    await removeCartCoupon(4)

    expect(apiClientMock.mock.calls).toEqual([
      ['/cart/coupon', { method: 'POST', body: JSON.stringify({ code: 'GIAM10', cart_version: 3 }) }],
      ['/cart/coupon', { method: 'DELETE', body: JSON.stringify({ cart_version: 4 }) }],
    ])
  })

  it('sends guest ownership when requesting a server-bound cancellation confirmation', async () => {
    apiClientMock.mockResolvedValue({ data: { confirmation_token: 'secret', expires_at: '2026-11-03T12:00:00Z' }, meta: { request_id: 'confirmation' } })
    const payload = { reason: null }
    await createActionConfirmation('order_cancel', 'DH-001', payload, {
      mode: 'guest',
      lookup_token: 'lookup-secret',
    })
    expect(apiClientMock).toHaveBeenCalledWith('/action-confirmations', {
      method: 'POST',
      headers: { 'X-Order-Lookup-Token': 'lookup-secret' },
      body: JSON.stringify({ action: 'order_cancel', resource_key: 'DH-001', payload }),
    })
  })

  it('omits guest ownership when requesting a checkout confirmation', async () => {
    apiClientMock.mockResolvedValue({ data: { confirmation_token: 'secret', expires_at: '2026-11-03T12:00:00Z' }, meta: { request_id: 'confirmation' } })
    const payload = { cart_version: 3 }

    await createActionConfirmation('order_create', 'cart-1', payload)

    expect(apiClientMock).toHaveBeenCalledWith('/action-confirmations', {
      method: 'POST',
      body: JSON.stringify({ action: 'order_create', resource_key: 'cart-1', payload }),
    })
  })

  it('omits guest ownership for an authenticated cancellation confirmation', async () => {
    apiClientMock.mockResolvedValue({ data: { confirmation_token: 'secret', expires_at: '2026-11-03T12:00:00Z' }, meta: { request_id: 'confirmation' } })
    const payload = { reason: null }

    await createActionConfirmation('order_cancel', 'DH-001', payload, { mode: 'authenticated' })

    expect(apiClientMock).toHaveBeenCalledWith('/action-confirmations', {
      method: 'POST',
      body: JSON.stringify({ action: 'order_cancel', resource_key: 'DH-001', payload }),
    })
  })
})
