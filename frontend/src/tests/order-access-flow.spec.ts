import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getOrder: vi.fn(),
  getPaymentDemo: vi.fn(),
  getLatestRefundRequest: vi.fn(),
  createActionConfirmation: vi.fn(),
  cancelOrder: vi.fn(),
  createRefundRequest: vi.fn(),
}))

vi.mock('../services/commerce', () => ({
  getOrder: mocks.getOrder,
  getPaymentDemo: mocks.getPaymentDemo,
  getLatestRefundRequest: mocks.getLatestRefundRequest,
  createActionConfirmation: mocks.createActionConfirmation,
  cancelOrder: mocks.cancelOrder,
  createRefundRequest: mocks.createRefundRequest,
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { orderCode: 'DH-001' } }) }))

import OrderDetailPage from '../pages/OrderDetailPage.vue'
import { clearRememberedOrder, rememberOrder } from '../stores/order-session'
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
  payment: { method: 'online_demo', status: 'demo_approved', amount: 270000, provider: 'demo', is_simulation: true },
  guest_lookup_token: 'new-checkout-token',
  created_at: '2026-11-03T00:00:00Z',
  ...overrides,
})

describe('guest checkout order access flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearRememberedOrder()
    mocks.getPaymentDemo.mockResolvedValue(makeOrder().payment)
    mocks.getLatestRefundRequest.mockResolvedValue(null)
    mocks.createActionConfirmation.mockResolvedValue({ confirmation_token: 'confirmation-token', expires_at: '2026-11-03T12:00:00Z' })
  })

  it('uses the lookup token returned by checkout for cancellation confirmation', async () => {
    const order = makeOrder()
    rememberOrder(order)
    mocks.cancelOrder.mockResolvedValue({ ...order, status: 'cancelled' })
    const wrapper = mount(OrderDetailPage)
    await flushPromises()

    await wrapper.get('#cancel-reason').setValue('Đổi ý')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const access = { mode: 'guest', lookup_token: 'new-checkout-token' }
    expect(mocks.getPaymentDemo).toHaveBeenCalledWith('DH-001', access)
    expect(mocks.createActionConfirmation).toHaveBeenCalledWith(
      'order_cancel',
      'DH-001',
      { reason: 'Đổi ý' },
      access,
    )
  })

  it('uses the lookup token returned by checkout for refund confirmation', async () => {
    const order = makeOrder({ status: 'completed' })
    rememberOrder(order)
    mocks.createRefundRequest.mockResolvedValue({ status: 'requested', provider: 'demo', is_simulation: true, amount: 270000 })
    const wrapper = mount(OrderDetailPage)
    await flushPromises()

    await wrapper.get('#refund-reason').setValue('manufacturer_fault')
    await wrapper.get('#refund-detail').setValue('Sản phẩm lỗi đường may')
    await wrapper.get('#confirm-refund').setValue(true)
    await wrapper.get('[data-testid="refund-form"]').trigger('submit')
    await flushPromises()

    const access = { mode: 'guest', lookup_token: 'new-checkout-token' }
    expect(mocks.createActionConfirmation).toHaveBeenCalledWith(
      'refund_request',
      'DH-001',
      { reason_code: 'manufacturer_fault', reason_detail: 'Sản phẩm lỗi đường may' },
      access,
    )
  })
})
