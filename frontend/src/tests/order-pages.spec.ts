import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  lookupGuestOrder: vi.fn(), rememberGuestOrder: vi.fn(), push: vi.fn(),
  getOrder: vi.fn(), getPaymentDemo: vi.fn(), getLatestRefundRequest: vi.fn(),
  createActionConfirmation: vi.fn(), cancelOrder: vi.fn(), createRefundRequest: vi.fn(),
  useOrderAccess: vi.fn(), requestChatAction: vi.fn(),
}))
vi.mock('../services/commerce', () => ({
  lookupGuestOrder: mocks.lookupGuestOrder, getOrder: mocks.getOrder, getPaymentDemo: mocks.getPaymentDemo,
  getLatestRefundRequest: mocks.getLatestRefundRequest, createActionConfirmation: mocks.createActionConfirmation,
  cancelOrder: mocks.cancelOrder, createRefundRequest: mocks.createRefundRequest,
}))
vi.mock('../stores/order-session', () => ({ rememberGuestOrder: mocks.rememberGuestOrder, useOrderAccess: mocks.useOrderAccess }))
vi.mock('../stores/chat-action', async (importOriginal) => ({
  ...await importOriginal<typeof import('../stores/chat-action')>(),
  requestChatAction: mocks.requestChatAction,
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }), useRoute: () => ({ params: { orderCode: 'DH-001' } }) }))

import OrderDetailPage from '../pages/OrderDetailPage.vue'
import OrderLookupPage from '../pages/OrderLookupPage.vue'
import { lastChatAuthoritativeState, publishChatAuthoritativeState } from '../stores/chat-action'

const order = {
  id: 'order-1', order_code: 'DH-001', status: 'completed', recipient_name: 'Nguyễn An', phone: '0900000000',
  address_line: '1 Đường Mẫu', ward: null, district: null, province: 'TP. Hồ Chí Minh', note: null,
  subtotal: 240000, discount_amount: 0, shipping_fee: 30000, total: 270000, currency: 'VND', items: [],
  payment: { method: 'online_demo', status: 'demo_approved', amount: 270000, provider: 'demo', is_simulation: true },
  guest_lookup_token: null, created_at: '2026-11-03T00:00:00Z',
}

describe('order lookup and detail UI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    lastChatAuthoritativeState.value = null
  })

  it('keeps the guest token out of navigation and delegates it to the header-only service', async () => {
    mocks.lookupGuestOrder.mockResolvedValue(order)
    const wrapper = mount(OrderLookupPage)
    await wrapper.get('#order-code').setValue('DH-001')
    await wrapper.get('#lookup-token').setValue('secret-token-long-enough')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.lookupGuestOrder).toHaveBeenCalledWith('DH-001', 'secret-token-long-enough')
    expect(mocks.rememberGuestOrder).toHaveBeenCalledWith(order, 'secret-token-long-enough')
    expect(mocks.push).toHaveBeenCalledWith({ name: 'order-detail', params: { orderCode: 'DH-001' } })
    expect(JSON.stringify(mocks.push.mock.calls)).not.toContain('secret-token')
  })

  it('requires explicit confirmation then creates a simulated refund with a bound token', async () => {
    const access = { order, access: { mode: 'guest', lookup_token: 'secret-token-long-enough' } }
    mocks.useOrderAccess.mockReturnValue(access)
    mocks.getPaymentDemo.mockResolvedValue(order.payment)
    mocks.getLatestRefundRequest.mockResolvedValue(null)
    mocks.createActionConfirmation.mockResolvedValue({ confirmation_token: 'confirmation-token-long', expires_at: '2026-11-03T12:00:00Z' })
    mocks.createRefundRequest.mockResolvedValue({ status: 'requested', provider: 'demo', is_simulation: true, amount: 270000 })
    const wrapper = mount(OrderDetailPage)
    await flushPromises()

    expect(wrapper.text()).toContain('hoàn tiền mô phỏng')
    await wrapper.get('#refund-reason').setValue('manufacturer_fault')
    await wrapper.get('#refund-detail').setValue('Sản phẩm lỗi đường may')
    await wrapper.get('#confirm-refund').setValue(true)
    await wrapper.get('[data-testid="refund-form"]').trigger('submit')
    await flushPromises()

    const payload = { reason_code: 'manufacturer_fault', reason_detail: 'Sản phẩm lỗi đường may' }
    expect(mocks.createActionConfirmation).toHaveBeenCalledWith('refund_request', 'DH-001', payload, access.access)
    expect(mocks.createRefundRequest).toHaveBeenCalledWith('DH-001', { ...payload, confirmation_token: 'confirmation-token-long' }, expect.stringMatching(/^refund-/), access.access)
  })

  it('uses guest ownership when requesting a cancellation confirmation', async () => {
    const cancellableOrder = { ...order, status: 'confirmed' }
    const access = { order: cancellableOrder, access: { mode: 'guest', lookup_token: 'secret-token-long-enough' } }
    mocks.useOrderAccess.mockReturnValue(access)
    mocks.getPaymentDemo.mockResolvedValue(order.payment)
    mocks.getLatestRefundRequest.mockResolvedValue(null)
    mocks.createActionConfirmation.mockResolvedValue({ confirmation_token: 'confirmation-token-long', expires_at: '2026-11-03T12:00:00Z' })
    mocks.cancelOrder.mockResolvedValue({ ...cancellableOrder, status: 'cancelled' })
    const wrapper = mount(OrderDetailPage)
    await flushPromises()

    await wrapper.get('#cancel-reason').setValue('Đổi ý')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.createActionConfirmation).toHaveBeenCalledWith(
      'order_cancel',
      'DH-001',
      { reason: 'Đổi ý' },
      access.access,
    )
  })

  it('stages a typed refund context from trusted order state for the chat widget', async () => {
    const access = { order, access: { mode: 'guest', lookup_token: 'secret-token-long-enough' } }
    mocks.useOrderAccess.mockReturnValue(access)
    mocks.getPaymentDemo.mockResolvedValue(order.payment)
    mocks.getLatestRefundRequest.mockResolvedValue(null)
    const wrapper = mount(OrderDetailPage)
    await flushPromises()

    await wrapper.get('#refund-reason').setValue('transit_damage')
    await wrapper.get('#refund-detail').setValue('Hộp bị móp khi giao')
    await wrapper.get('[data-testid="chat-refund-request"]').trigger('click')

    expect(mocks.requestChatAction).toHaveBeenCalledWith({
      actionContext: {
        action: 'refund_request',
        order_id: 'order-1',
        order_code: 'DH-001',
        reason_code: 'transit_damage',
        reason_detail: 'Hộp bị móp khi giao',
      },
      lookupToken: 'secret-token-long-enough',
      prompt: 'Tạo yêu cầu hoàn tiền mô phỏng cho đơn DH-001',
    })
  })

  it('replaces order and refund status with authoritative state after chat confirmation', async () => {
    mocks.useOrderAccess.mockReturnValue({ order, access: { mode: 'authenticated' } })
    mocks.getPaymentDemo.mockResolvedValue(order.payment)
    mocks.getLatestRefundRequest.mockResolvedValue(null)
    const wrapper = mount(OrderDetailPage)
    await flushPromises()
    const refreshedRefund = {
      id: 'refund-1', order_code: 'DH-001', reason_code: 'wrong_item', reason_detail: null,
      amount: 270000, status: 'demo_reviewing', provider: 'demo', is_simulation: true,
      created_at: '2026-11-03T01:00:00Z',
    }

    publishChatAuthoritativeState({
      kind: 'refund',
      order: { ...order, status: 'completed' },
      refund: refreshedRefund,
    } as never)
    await flushPromises()

    expect(wrapper.text()).toContain('Trạng thái: demo_reviewing')
    expect(wrapper.find('[data-testid="refund-form"]').exists()).toBe(false)
  })

  it('synchronizes the cancelled demo payment from the authoritative order refresh', async () => {
    const cancellableOrder = { ...order, status: 'confirmed' }
    mocks.useOrderAccess.mockReturnValue({ order: cancellableOrder, access: { mode: 'authenticated' } })
    mocks.getPaymentDemo.mockResolvedValue(order.payment)
    mocks.getLatestRefundRequest.mockResolvedValue(null)
    const wrapper = mount(OrderDetailPage)
    await flushPromises()

    publishChatAuthoritativeState({
      kind: 'order',
      order: {
        ...cancellableOrder,
        status: 'cancelled',
        payment: { ...order.payment, status: 'cancelled' },
      },
    } as never)
    await flushPromises()

    expect(wrapper.text()).toContain('Trạng thái đơn: cancelled')
    expect(wrapper.text()).toContain('Trạng thái: cancelled')
  })
})
