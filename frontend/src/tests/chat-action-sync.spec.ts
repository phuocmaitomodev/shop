import { beforeEach, describe, expect, it, vi } from 'vitest'

const commerce = vi.hoisted(() => ({
  getCart: vi.fn(),
  getLatestRefundRequest: vi.fn(),
  getOrder: vi.fn(),
  lookupGuestOrder: vi.fn(),
}))
vi.mock('../services/commerce', () => commerce)

import { refreshChatActionState } from '../services/chat-action-sync'

const cart = { cart_id: 'cart-1', version: 4, item_count: 2 }
const order = { id: 'order-1', order_code: 'DH-001', status: 'cancelled' }
const refund = { id: 'refund-1', order_code: 'DH-001', status: 'requested' }

describe('chat action authoritative synchronization', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each(['cart_add', 'cart_update', 'cart_remove', 'order_create'] as const)(
    'refreshes the cart from the server after %s',
    async (action) => {
      commerce.getCart.mockResolvedValue(cart)

      await expect(refreshChatActionState(action, 'cart-1')).resolves.toEqual({ kind: 'cart', action, cart })
      expect(commerce.getCart).toHaveBeenCalledOnce()
    },
  )

  it('refreshes an authenticated cancelled order by server resource code', async () => {
    commerce.getOrder.mockResolvedValue(order)

    await expect(refreshChatActionState('order_cancel', 'DH-001')).resolves.toEqual({ kind: 'order', order })
    expect(commerce.getOrder).toHaveBeenCalledWith('DH-001')
  })

  it('uses the guest lookup header credential without storing it in synchronized state', async () => {
    commerce.lookupGuestOrder.mockResolvedValue(order)

    const state = await refreshChatActionState('order_cancel', 'DH-001', 'guest-lookup-token-long')

    expect(commerce.lookupGuestOrder).toHaveBeenCalledWith('DH-001', 'guest-lookup-token-long')
    expect(state).toEqual({ kind: 'order', order })
    expect(JSON.stringify(state)).not.toContain('guest-lookup-token-long')
  })

  it('refreshes both the order and latest demo refund after a refund request', async () => {
    commerce.getOrder.mockResolvedValue(order)
    commerce.getLatestRefundRequest.mockResolvedValue(refund)

    await expect(refreshChatActionState('refund_request', 'DH-001')).resolves.toEqual({
      kind: 'refund',
      order,
      refund,
    })
    expect(commerce.getLatestRefundRequest).toHaveBeenCalledWith('DH-001', { mode: 'authenticated' })
  })
})
