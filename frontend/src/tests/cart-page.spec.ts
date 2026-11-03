import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const commerce = vi.hoisted(() => ({
  getCart: vi.fn(),
  updateCartItem: vi.fn(),
  removeCartItem: vi.fn(),
  applyCartCoupon: vi.fn(),
  removeCartCoupon: vi.fn(),
}))
vi.mock('../services/commerce', () => commerce)

import CartPage from '../pages/CartPage.vue'

const cart = {
  cart_id: 'cart-1', version: 3, item_count: 2, coupon_code: null,
  items: [{
    item_id: 'item-1', variant_id: 'variant-1', product_id: 'product-1',
    product_slug: 'ao-thun', product_name: 'Áo thun Mộc', variant_sku: 'AT-D-M',
    color_name: 'Đen', size_code: 'M', quantity: 2, stock_quantity: 3,
    is_available: true, unit_price: 120000, previous_unit_price: 120000,
    price_changed: false, line_total: 240000,
  }],
  subtotal: 240000, discount_amount: 0, shipping_fee: 30000, total: 270000,
  currency: 'VND' as const,
}

describe('CartPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads cart, renders VND totals, and updates quantity with current version', async () => {
    commerce.getCart.mockResolvedValue(cart)
    commerce.updateCartItem.mockResolvedValue({ ...cart, version: 4, total: 150000 })
    const wrapper = mount(CartPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('Áo thun Mộc')
    expect(wrapper.text()).toContain('270.000 ₫')
    await wrapper.get('[aria-label="Số lượng Áo thun Mộc"]').setValue(1)
    await wrapper.get('[data-testid="update-item-item-1"]').trigger('click')
    await flushPromises()

    expect(commerce.updateCartItem).toHaveBeenCalledWith('item-1', { quantity: 1, cart_version: 3 })
  })

  it('blocks stock overflow before the request and explains the boundary', async () => {
    commerce.getCart.mockResolvedValue(cart)
    const wrapper = mount(CartPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    await wrapper.get('[aria-label="Số lượng Áo thun Mộc"]').setValue(4)
    await wrapper.get('[data-testid="update-item-item-1"]').trigger('click')

    expect(commerce.updateCartItem).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('chỉ còn 3 sản phẩm')
  })

  it('reloads fresh server state after an optimistic cart conflict', async () => {
    commerce.getCart.mockResolvedValueOnce(cart).mockResolvedValueOnce({ ...cart, version: 8 })
    commerce.updateCartItem.mockRejectedValue({ payload: { error: { code: 'CART_VERSION_CONFLICT' } } })
    const wrapper = mount(CartPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    await wrapper.get('[data-testid="update-item-item-1"]').trigger('click')
    await flushPromises()

    expect(commerce.getCart).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role="alert"]').text()).toContain('đã thay đổi')
  })
})
