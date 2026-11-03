import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getCart: vi.fn(), createActionConfirmation: vi.fn(), createOrder: vi.fn(), rememberOrder: vi.fn(), push: vi.fn(),
}))
vi.mock('../services/commerce', () => ({ getCart: mocks.getCart, createActionConfirmation: mocks.createActionConfirmation, createOrder: mocks.createOrder }))
vi.mock('../stores/order-session', () => ({ rememberOrder: mocks.rememberOrder }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))

import CheckoutPage from '../pages/CheckoutPage.vue'

const cart = { cart_id: 'cart-1', version: 3, item_count: 1, coupon_code: null, items: [{}], subtotal: 240000, discount_amount: 0, shipping_fee: 30000, total: 270000, currency: 'VND' }

describe('CheckoutPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the six checkout steps and labels online payment as simulation only', async () => {
    mocks.getCart.mockResolvedValue(cart)
    const wrapper = mount(CheckoutPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.findAll('[data-testid="checkout-step"]')).toHaveLength(6)
    await wrapper.get('input[value="online_demo"]').setValue()
    expect(wrapper.get('[aria-label="Thông báo thanh toán mô phỏng"]').text()).toContain('không phát sinh giao dịch thật')
  })

  it('gets a bound confirmation before creating an order with one idempotency key', async () => {
    mocks.getCart.mockResolvedValue(cart)
    mocks.createActionConfirmation.mockResolvedValue({ confirmation_token: 'confirmation-token-long', expires_at: '2026-11-03T12:00:00Z' })
    const order = { order_code: 'DH-001', guest_lookup_token: 'lookup-token-long' }
    mocks.createOrder.mockResolvedValue(order)
    const wrapper = mount(CheckoutPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    const values: Record<string, string> = {
      '#recipient-name': 'Nguyễn An', '#phone': '0900000000', '#address-line': '1 Đường Mẫu',
      '#ward': 'Phường 1', '#district': 'Quận 1', '#province': 'TP. Hồ Chí Minh',
    }
    for (const [selector, value] of Object.entries(values)) await wrapper.get(selector).setValue(value)
    await wrapper.get('#confirm-order').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const expectedPayload = expect.objectContaining({ cart_id: 'cart-1', cart_version: 3, recipient_name: 'Nguyễn An', payment_method: 'cod' })
    expect(mocks.createActionConfirmation).toHaveBeenCalledWith('order_create', 'cart-1', expectedPayload)
    expect(mocks.createOrder).toHaveBeenCalledWith({ ...mocks.createActionConfirmation.mock.calls[0][2], confirmation_token: 'confirmation-token-long' }, expect.stringMatching(/^order-/))
    expect(mocks.rememberOrder).toHaveBeenCalledWith(order)
    expect(mocks.push).toHaveBeenCalledWith({ name: 'order-success' })
  })
})
