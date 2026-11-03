import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  lookupGuestOrder: vi.fn(), rememberGuestOrder: vi.fn(), push: vi.fn(),
  getOrder: vi.fn(), getPaymentDemo: vi.fn(), getLatestRefundRequest: vi.fn(),
  createActionConfirmation: vi.fn(), cancelOrder: vi.fn(), createRefundRequest: vi.fn(),
  useOrderAccess: vi.fn(),
}))
vi.mock('../services/commerce', () => ({
  lookupGuestOrder: mocks.lookupGuestOrder, getOrder: mocks.getOrder, getPaymentDemo: mocks.getPaymentDemo,
  getLatestRefundRequest: mocks.getLatestRefundRequest, createActionConfirmation: mocks.createActionConfirmation,
  cancelOrder: mocks.cancelOrder, createRefundRequest: mocks.createRefundRequest,
}))
vi.mock('../stores/order-session', () => ({ rememberGuestOrder: mocks.rememberGuestOrder, useOrderAccess: mocks.useOrderAccess }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }), useRoute: () => ({ params: { orderCode: 'DH-001' } }) }))

import OrderDetailPage from '../pages/OrderDetailPage.vue'
import OrderLookupPage from '../pages/OrderLookupPage.vue'

const order = {
  id: 'order-1', order_code: 'DH-001', status: 'completed', recipient_name: 'Nguyễn An', phone: '0900000000',
  address_line: '1 Đường Mẫu', ward: null, district: null, province: 'TP. Hồ Chí Minh', note: null,
  subtotal: 240000, discount_amount: 0, shipping_fee: 30000, total: 270000, currency: 'VND', items: [],
  payment: { method: 'online_demo', status: 'demo_approved', amount: 270000, provider: 'demo', is_simulation: true },
  guest_lookup_token: null, created_at: '2026-11-03T00:00:00Z',
}

describe('order lookup and detail UI', () => {
  beforeEach(() => vi.clearAllMocks())

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
    expect(mocks.createActionConfirmation).toHaveBeenCalledWith('refund_request', 'DH-001', payload)
    expect(mocks.createRefundRequest).toHaveBeenCalledWith('DH-001', { ...payload, confirmation_token: 'confirmation-token-long' }, expect.stringMatching(/^refund-/), access.access)
  })
})
